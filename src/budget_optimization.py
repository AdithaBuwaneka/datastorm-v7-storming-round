"""Western Province trade-spend allocation under a fixed LKR 5M budget.

Concave diminishing-returns allocation:

    maximise   sum_i  kappa_i * sqrt(x_i)
    subject to sum_i  x_i  <=  B           # B = LKR 5,000,000
               0 <=  x_i  <=  x_max        # per-outlet cap
               i in Western Province

with kappa_i = uplift_i * cooler_priority_i * (1 + spatial_lift_i)
              / (1 + competitive_drag_i).

The square-root utility is a standard marketing-mix-model response shape
(Hanssens, Parsons & Schultz 2001; Jin et al 2017) and admits a closed-form
water-filling solution.

Outputs:
    outputs/DataX_budget_allocations.csv (Outlet_ID, Trade_Spend_LKR)
    outputs/audit/budget_allocation_by_distributor.csv
    outputs/audit/budget_allocation_by_segment.csv
    outputs/audit/budget_allocation_top50.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config


BUDGET_LKR = 5_000_000.0
WESTERN_PROVINCE = "Western"
MAX_SPEND_PER_OUTLET_LKR = 5_000.0   # caps concentration; ~0.1% of budget
MIN_SPEND_PER_OUTLET_LKR = 0.0
EPSILON = 1e-9


def compute_kappa(feats: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    """Build kappa_i (response coefficient per outlet)."""
    df = feats[feats["Province"] == WESTERN_PROVINCE].copy()
    df = df.merge(predictions, on="Outlet_ID", how="left")

    # Recent observed monthly volume (use mean of unconstrained months as proxy)
    df["observed_recent"] = df["monthly_volume_mean"].fillna(0.0).clip(lower=0.0)
    df["pred_jan_2026"] = df["Maximum_Monthly_Liters"].fillna(0.0).clip(lower=0.0)

    # Uplift: predicted potential minus current monthly average
    df["uplift_potential"] = (df["pred_jan_2026"] - df["observed_recent"]).clip(lower=0.0)

    # Cooler priority: no-cooler outlets benefit most from trade spend
    # because they have suppressed demand from infrastructure constraint
    df["cooler_priority"] = np.where(df["Cooler_Count"] == 0, 1.5,
                              np.where(df["Cooler_Count"] == 1, 1.2, 1.0))

    # Spatial signal lift: high spatial demand → spend more effective
    spatial = df.get("spatial_demand_score", pd.Series(0.0, index=df.index)).fillna(0.0).clip(0.0, 1.0)
    df["spatial_lift"] = 1.0 + 0.4 * spatial

    # Competitive drag: high competition reduces spend efficiency
    comp = df.get("competitor_density_norm", pd.Series(0.0, index=df.index)).fillna(0.0).clip(lower=0.0)
    df["competitive_drag"] = 1.0 + 0.3 * comp

    df["kappa"] = (
        df["uplift_potential"]
        * df["cooler_priority"]
        * df["spatial_lift"]
        / df["competitive_drag"]
    ).clip(lower=0.0)

    return df


def _channel_weights(row) -> tuple[float, float, float]:
    """Return (discount_w, merchandising_w, promotional_w) summing to 1.0.

    Heuristic rules:
      * No cooler today  -> overweight merchandising (in-store visibility)
      * High type-weighted competition pressure (above median ~10)
                          -> overweight discount + merchandising (defend share)
      * Low spatial demand (rural / quiet area)
                          -> overweight promotional (drive trial)
      * Otherwise         -> balanced merchandising-heavy default
    """
    no_cooler = int(row.get("Cooler_Count", 1) or 0) == 0
    pressure = float(row.get("type_weighted_pressure", 0.0) or 0.0)
    spatial  = float(row.get("spatial_demand_score", 0.0) or 0.0)

    if no_cooler:
        d, m, p = 0.20, 0.55, 0.25
    elif pressure >= 10.0:
        d, m, p = 0.40, 0.40, 0.20
    elif spatial <= 0.10:
        d, m, p = 0.20, 0.30, 0.50
    else:
        d, m, p = 0.30, 0.45, 0.25
    return d, m, p


def _split_by_channel(df: pd.DataFrame) -> pd.DataFrame:
    weights = df.apply(_channel_weights, axis=1, result_type="expand")
    weights.columns = ["w_discount", "w_merchandising", "w_promotional"]
    df = df.join(weights)
    df["Discount_LKR"]      = (df["Trade_Spend_LKR"] * df["w_discount"]).round(2)
    df["Merchandising_LKR"] = (df["Trade_Spend_LKR"] * df["w_merchandising"]).round(2)
    df["Promotional_LKR"]   = (df["Trade_Spend_LKR"] * df["w_promotional"]).round(2)
    # Rebalance rounding drift so the three columns sum exactly to allocated
    drift = df["Trade_Spend_LKR"] - (df["Discount_LKR"]
                                      + df["Merchandising_LKR"]
                                      + df["Promotional_LKR"])
    df["Merchandising_LKR"] = (df["Merchandising_LKR"] + drift).round(2)
    return df


def water_fill(kappa: np.ndarray, budget: float, x_max: float,
               max_iter: int = 100, tol: float = 1e-4) -> np.ndarray:
    """Iterative water-filling for max sum(kappa_i sqrt(x_i)) s.t. sum x_i <= B,
    0 <= x_i <= x_max.

    Lagrangian: x_i = (kappa_i / 2 lambda)^2, but capped at x_max.
    Find lambda such that sum(x_i) == budget using bisection.
    """
    n = len(kappa)
    if budget <= 0 or n == 0:
        return np.zeros(n)

    pos = kappa > EPSILON
    if not pos.any():
        # No positive kappa — equal allocation
        return np.full(n, budget / n)

    k = kappa.copy()

    # Bisection on lambda
    # lambda_low corresponds to assigning everyone x_max (budget too small if lam->0)
    # lambda_high corresponds to nobody being above 0 (budget too large if lam->inf)
    lam_low = max(k.max() / (2 * np.sqrt(x_max + EPSILON)), EPSILON)
    lam_high = lam_low

    def total_spend(lam):
        x = (k / (2 * lam)) ** 2
        x = np.clip(x, 0, x_max)
        return x.sum(), x

    # Find lam_high such that total_spend(lam_high) <= budget
    while True:
        s, _ = total_spend(lam_high)
        if s <= budget:
            break
        lam_high *= 2
        if lam_high > 1e18:
            break

    # Find lam_low such that total_spend(lam_low) >= budget
    while True:
        s, _ = total_spend(lam_low)
        if s >= budget:
            break
        lam_low /= 2
        if lam_low < 1e-18:
            break

    for _ in range(max_iter):
        lam_mid = 0.5 * (lam_low + lam_high)
        s, x = total_spend(lam_mid)
        if abs(s - budget) < tol * budget:
            break
        if s > budget:
            lam_low = lam_mid
        else:
            lam_high = lam_mid

    s, x = total_spend(0.5 * (lam_low + lam_high))
    # Final safety: if floating-point convergence still exceeds budget, scale
    # down proportionally. Concave objective => uniform scale-down preserves
    # near-optimality and guarantees feasibility.
    if s > budget:
        x = x * (budget / s)
    return x


def allocate(feats: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    """Run the full LKR 5M allocation."""
    print("\n== Budget optimisation (LKR 5M, Western Province) ==")
    df = compute_kappa(feats, predictions)
    print(f"  Western outlets: {len(df):,}")
    print(f"  Median uplift_potential: {df['uplift_potential'].median():.1f} L/month")
    print(f"  Median kappa:            {df['kappa'].median():.2f}")
    print(f"  Kappa zero outlets:      {(df['kappa'] == 0).sum():,}")

    spend = water_fill(df["kappa"].to_numpy(), BUDGET_LKR, MAX_SPEND_PER_OUTLET_LKR)
    # Floor to 2 decimals to guarantee we never overshoot the budget after rounding
    spend = np.floor(spend * 100.0) / 100.0
    df["Trade_Spend_LKR"] = spend

    # --- Channel-modality split -----------------------------------------
    # Each outlet's allocated spend is divided across three promotional
    # channels using outlet-attribute heuristics. Weights below come from
    # the marketing-mix-modelling literature (lower elasticity for
    # off-invoice discounts vs visibility/sampling).
    df = _split_by_channel(df)

    total = df["Trade_Spend_LKR"].sum()
    print(f"  Total allocated: LKR {total:,.2f} (budget LKR {BUDGET_LKR:,.0f})")
    assert total <= BUDGET_LKR + 0.01, f"Budget overflow: {total:,.2f} > {BUDGET_LKR:,.2f}"

    # Objective-value score (dimensionless; sum of kappa * sqrt(spend)).
    # NOT raw liters — we have no historical campaign data to calibrate a
    # liters-per-LKR response, so we report the relative response score and
    # let downstream consumers ground it against a chosen elasticity.
    response_score = (df["kappa"] * np.sqrt(df["Trade_Spend_LKR"].clip(lower=0.0))).sum()
    print(f"  Aggregate response score (objective): {response_score:,.0f}")
    print(f"  Outlets receiving > 0:       {(df['Trade_Spend_LKR'] > 0).sum():,}")
    print(f"  Outlets at cap (LKR {MAX_SPEND_PER_OUTLET_LKR:,.0f}): "
          f"{(df['Trade_Spend_LKR'] >= MAX_SPEND_PER_OUTLET_LKR - 0.01).sum():,}")

    return df


def write_outputs(df: pd.DataFrame) -> None:
    """Persist the deliverable + audit artifacts."""
    config.OUTPUTS.mkdir(parents=True, exist_ok=True)
    config.AUDIT.mkdir(parents=True, exist_ok=True)

    # Output CSV: Outlet_ID + Trade_Spend_LKR (the submission deliverable)
    out = df[["Outlet_ID", "Trade_Spend_LKR"]].sort_values("Outlet_ID")
    out_path = config.OUTPUTS / f"{config.TEAM_NAME}_budget_allocations.csv"
    out.to_csv(out_path, index=False)
    print(f"  Output: {out_path}  shape={out.shape}")

    # Audit: the same allocation split across promotional channels
    channel_cols = ["Outlet_ID", "Distributor_ID", "Outlet_Type", "Cooler_Count",
                    "Trade_Spend_LKR",
                    "Discount_LKR", "Merchandising_LKR", "Promotional_LKR",
                    "w_discount", "w_merchandising", "w_promotional"]
    channel_cols = [c for c in channel_cols if c in df.columns]
    channels = df[channel_cols].sort_values("Outlet_ID")
    channels_path = config.AUDIT / "budget_allocation_by_channel.csv"
    channels.to_csv(channels_path, index=False)
    print(f"  Audit (by channel): {channels_path}")
    print(f"    Discount total:      LKR {df['Discount_LKR'].sum():>13,.0f}")
    print(f"    Merchandising total: LKR {df['Merchandising_LKR'].sum():>13,.0f}")
    print(f"    Promotional total:   LKR {df['Promotional_LKR'].sum():>13,.0f}")

    # Audit: per-distributor summary
    by_dist = df.groupby("Distributor_ID").agg(
        n_outlets=("Outlet_ID", "count"),
        total_spend_LKR=("Trade_Spend_LKR", "sum"),
        median_spend_LKR=("Trade_Spend_LKR", "median"),
        n_funded=("Trade_Spend_LKR", lambda x: (x > 0).sum()),
        response_score=("kappa", lambda k: (k.values *
                            np.sqrt(df.loc[k.index, "Trade_Spend_LKR"].clip(lower=0.0).values)).sum()),
    ).reset_index()
    by_dist["pct_of_budget"] = (100 * by_dist["total_spend_LKR"] / BUDGET_LKR).round(2)
    audit_dist = config.AUDIT / "budget_allocation_by_distributor.csv"
    by_dist.to_csv(audit_dist, index=False)
    print(f"  Audit (by distributor): {audit_dist}")
    print(by_dist.to_string(index=False))

    # Audit: per-cooler-segment summary
    df["cooler_segment"] = df["Cooler_Count"].apply(
        lambda c: "no_cooler" if c == 0 else ("low_cooler_1-2" if c <= 2 else "high_cooler_3+")
    )
    by_seg = df.groupby("cooler_segment").agg(
        n_outlets=("Outlet_ID", "count"),
        total_spend_LKR=("Trade_Spend_LKR", "sum"),
        median_spend_LKR=("Trade_Spend_LKR", "median"),
        n_funded=("Trade_Spend_LKR", lambda x: (x > 0).sum()),
    ).reset_index()
    audit_seg = config.AUDIT / "budget_allocation_by_segment.csv"
    by_seg.to_csv(audit_seg, index=False)
    print(f"  Audit (by cooler segment): {audit_seg}")

    # Audit: top-50 outlets
    top50 = df.nlargest(50, "Trade_Spend_LKR")[
        ["Outlet_ID", "Distributor_ID", "Outlet_Type", "Outlet_Size",
         "Cooler_Count", "uplift_potential", "kappa", "Trade_Spend_LKR"]
    ]
    audit_top50 = config.AUDIT / "budget_allocation_top50.csv"
    top50.to_csv(audit_top50, index=False)
    print(f"  Audit (top 50 outlets): {audit_top50}")

    # Audit: elasticity sensitivity. We do not have campaign data to estimate
    # the absolute liters-per-LKR conversion, so we report expected uplift
    # under a range of beta scalars applied to the raw objective value:
    #     expected_uplift_L = beta * sum_i kappa_i * sqrt(x_i)
    # A modeller / business owner can pick the beta they consider defensible
    # given their own past campaign data.
    response_score = float((df["kappa"] *
                            np.sqrt(df["Trade_Spend_LKR"].clip(lower=0.0))).sum())
    betas = [0.001, 0.005, 0.010, 0.025, 0.050, 0.100]
    sens = pd.DataFrame({
        "beta": betas,
        "expected_uplift_L": [round(b * response_score, 1) for b in betas],
        "expected_uplift_per_outlet_L": [
            round(b * response_score / max(int((df["Trade_Spend_LKR"] > 0).sum()), 1), 2)
            for b in betas
        ],
        "implied_L_per_LKR_at_median_spend": [
            round(b * df["kappa"].median() / max(np.sqrt(df.loc[df["Trade_Spend_LKR"] > 0, "Trade_Spend_LKR"].median()), 1.0), 4)
            for b in betas
        ],
    })
    audit_sens = config.AUDIT / "budget_sensitivity.csv"
    sens.to_csv(audit_sens, index=False)
    print(f"  Audit (sensitivity sweep): {audit_sens}")
    print(sens.to_string(index=False))


def main() -> None:
    print("\n" + "="*70)
    print("Western Province trade-spend allocation (LKR 5M)")
    print("="*70)

    feats = pd.read_parquet(config.GOLD / "outlet_features.parquet")
    predictions = pd.read_csv(config.OUTPUTS / f"{config.TEAM_NAME}_predictions.csv")

    df = allocate(feats, predictions)
    write_outputs(df)
    print("\nBudget optimisation: OK")


if __name__ == "__main__":
    main()
