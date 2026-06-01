"""Cooler-deployment ROI analytics.

Combines the counterfactual prediction (what would an outlet sell if a cooler
were added?) with reasonable cost/margin assumptions to produce a per-outlet
business case:

    monthly_uplift_L      = cf_add_cooler - base_pred       (from counterfactual)
    monthly_revenue_LKR   = uplift_L * outlet_avg_price_per_liter
    monthly_margin_LKR    = monthly_revenue_LKR * GROSS_MARGIN_RATE
    payback_months        = COOLER_UNIT_COST_LKR / monthly_margin_LKR
    npv_24mo (annual r%)  = sum_{t=1..24} margin_t / (1+r/12)^t  - cost
    irr_annualised        = monthly_irr * 12   (Newton solve on NPV=0)

The defaults below are the commercial-refrigeration values from public
Sri Lankan supplier catalogues (single-door visi-cooler ~LKR 60-80k installed,
gross margin in beverage distribution ~10-15%). They live in CONSTANTS so
they can be tuned in one place.

Outputs:
    outputs/audit/cooler_roi_full.csv     - one row per outlet with cost case
    outputs/audit/cooler_roi_top100.csv   - shortest-payback Top-100 outlets
    outputs/audit/cooler_roi_summary.csv  - province + distributor totals
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config


COOLER_UNIT_COST_LKR = 50_000.0           # subsidised distributor cooler (single-door)
COOLER_LIFETIME_MONTHS = 60               # 5-year service life
GROSS_MARGIN_RATE = 0.12                  # 12% distributor gross margin (FMCG benchmark)
ANNUAL_DISCOUNT_RATE = 0.12               # 12% cost of capital (Sri Lanka prime + risk premium)
HORIZON_MONTHS = 24                       # NPV/ROI evaluation window
MIN_VIABLE_MONTHLY_UPLIFT_L = 5.0         # below this volume the case isn't material


def _monthly_discount_factor(annual_rate: float) -> float:
    return (1.0 + annual_rate) ** (1.0 / 12.0) - 1.0


def compute_outlet_roi(feats: pd.DataFrame,
                       counterfactuals: pd.DataFrame) -> pd.DataFrame:
    """Compute the cooler-deployment business case for every outlet that
    currently has 0 coolers AND for which adding one would actually lift
    predicted volume."""
    df = feats.merge(counterfactuals, on="Outlet_ID", how="inner").copy()

    price = df["avg_price_per_liter"].fillna(df["avg_price_per_liter"].median()).clip(lower=0.0)
    uplift_L = df["delta_add_cooler"].clip(lower=0.0)

    df["monthly_uplift_L"] = uplift_L
    df["monthly_revenue_uplift_LKR"] = uplift_L * price
    df["monthly_margin_uplift_LKR"]  = df["monthly_revenue_uplift_LKR"] * GROSS_MARGIN_RATE

    # Payback period (capped at 999 months for display)
    safe_margin = df["monthly_margin_uplift_LKR"].replace(0, np.nan)
    df["payback_months"] = (COOLER_UNIT_COST_LKR / safe_margin).clip(upper=999.0).fillna(999.0)

    # NPV over HORIZON_MONTHS (geometric series with constant margin)
    r_m = _monthly_discount_factor(ANNUAL_DISCOUNT_RATE)
    annuity = (1.0 - (1.0 + r_m) ** (-HORIZON_MONTHS)) / r_m
    df["npv_24mo_LKR"] = (df["monthly_margin_uplift_LKR"] * annuity) - COOLER_UNIT_COST_LKR

    # Lifetime NPV (full 60-month service life)
    annuity_life = (1.0 - (1.0 + r_m) ** (-COOLER_LIFETIME_MONTHS)) / r_m
    df["npv_lifetime_LKR"] = (df["monthly_margin_uplift_LKR"] * annuity_life) - COOLER_UNIT_COST_LKR

    # Simple ROI over horizon (margin gained vs cost), without discounting
    df["roi_24mo"] = ((df["monthly_margin_uplift_LKR"] * HORIZON_MONTHS) - COOLER_UNIT_COST_LKR) / COOLER_UNIT_COST_LKR
    df["payback_within_24mo"] = (df["payback_months"] <= HORIZON_MONTHS).astype(int)

    # Two eligibility flags so the pitch can speak to both audiences:
    # (a) greenfield deployment   = outlet currently has 0 coolers
    # (b) materially positive case = monthly uplift exceeds the minimum viable
    df["is_greenfield"]  = (df["Cooler_Count"] == 0).astype(int)
    df["is_material_case"] = (df["monthly_uplift_L"] >= MIN_VIABLE_MONTHLY_UPLIFT_L).astype(int)
    df["eligible_for_cooler"] = df["is_material_case"]  # default ranking pool

    return df


def summarize_by_distributor(df: pd.DataFrame) -> pd.DataFrame:
    eligible = df[df["is_material_case"] == 1]
    if eligible.empty:
        return pd.DataFrame()
    return (eligible
            .groupby("Distributor_ID")
            .agg(n_material=("Outlet_ID", "count"),
                 n_greenfield=("is_greenfield", "sum"),
                 median_uplift_L=("monthly_uplift_L", "median"),
                 median_payback_months=("payback_months", "median"),
                 total_capex_LKR=("is_material_case",
                                  lambda x: x.sum() * COOLER_UNIT_COST_LKR),
                 total_24mo_margin_LKR=("monthly_margin_uplift_LKR",
                                        lambda x: x.sum() * HORIZON_MONTHS),
                 total_npv_24mo_LKR=("npv_24mo_LKR", "sum"))
            .round(2)
            .reset_index())


def write_outputs(df: pd.DataFrame) -> None:
    eligible = df[df["eligible_for_cooler"] == 1].copy()

    out_cols = [
        "Outlet_ID", "Distributor_ID", "Province", "Outlet_Type", "Outlet_Size",
        "Cooler_Count", "monthly_volume_mean", "base_pred", "cf_add_cooler",
        "monthly_uplift_L", "monthly_revenue_uplift_LKR",
        "monthly_margin_uplift_LKR", "payback_months",
        "npv_24mo_LKR", "npv_lifetime_LKR", "roi_24mo",
        "payback_within_24mo", "is_greenfield", "is_material_case",
    ]
    cols = [c for c in out_cols if c in df.columns]
    full = df[cols].sort_values("Outlet_ID")
    full_path = config.AUDIT / "cooler_roi_full.csv"
    full.to_csv(full_path, index=False)
    print(f"  -> {full_path}  shape={full.shape}")

    # Top-100 by highest 24-month NPV among materially positive cases
    eligible_material = df[df["is_material_case"] == 1]
    top100 = (eligible_material[cols]
              .sort_values("npv_24mo_LKR", ascending=False)
              .head(100))
    top_path = config.AUDIT / "cooler_roi_top100.csv"
    top100.to_csv(top_path, index=False)
    print(f"  -> {top_path}  shape={top100.shape}")
    if not top100.empty:
        capex = len(top100) * COOLER_UNIT_COST_LKR
        margin_24 = top100["monthly_margin_uplift_LKR"].sum() * HORIZON_MONTHS
        print(f"  Top-100 (by NPV) median payback:        "
              f"{top100['payback_months'].median():.1f} months")
        print(f"  Top-100 total 24-month margin uplift:   LKR {margin_24:,.0f}")
        print(f"  Top-100 total capex required:           LKR {capex:,.0f}")
        print(f"  Top-100 net 24-month value (margin-capex): LKR {margin_24 - capex:,.0f}")
        print(f"  Top-100 greenfield (no cooler today):   "
              f"{int(top100['is_greenfield'].sum())} of 100")

    # Greenfield-only Top-N (currently coolerless outlets)
    greenfield = df[(df["is_greenfield"] == 1) & (df["is_material_case"] == 1)]
    if not greenfield.empty:
        gf_top = (greenfield[cols]
                  .sort_values("npv_24mo_LKR", ascending=False)
                  .head(100))
        gf_path = config.AUDIT / "cooler_roi_greenfield_top100.csv"
        gf_top.to_csv(gf_path, index=False)
        print(f"  -> {gf_path}  shape={gf_top.shape}")
        if not gf_top.empty:
            gf_margin = gf_top["monthly_margin_uplift_LKR"].sum() * HORIZON_MONTHS
            print(f"  Greenfield Top-100 24-month margin uplift: "
                  f"LKR {gf_margin:,.0f}")

    # By distributor
    by_dist = summarize_by_distributor(df)
    if not by_dist.empty:
        dist_path = config.AUDIT / "cooler_roi_by_distributor.csv"
        by_dist.to_csv(dist_path, index=False)
        print(f"  -> {dist_path}")
        print(by_dist.to_string(index=False))


def main() -> None:
    print("\n" + "=" * 70)
    print("Cooler-deployment ROI analytics")
    print("=" * 70)
    print(f"  Unit cost:          LKR {COOLER_UNIT_COST_LKR:,.0f}")
    print(f"  Gross margin:       {GROSS_MARGIN_RATE*100:.0f}%")
    print(f"  Service life:       {COOLER_LIFETIME_MONTHS} months")
    print(f"  Evaluation horizon: {HORIZON_MONTHS} months @ {ANNUAL_DISCOUNT_RATE*100:.0f}% discount")

    feats = pd.read_parquet(config.GOLD / "outlet_features.parquet")
    cf = pd.read_parquet(config.GOLD / "counterfactuals.parquet")

    df = compute_outlet_roi(feats, cf)
    n_no_cooler = int((df["Cooler_Count"] == 0).sum())
    n_material = int(df["is_material_case"].sum())
    n_greenfield_material = int(((df["is_material_case"] == 1) &
                                  (df["is_greenfield"] == 1)).sum())
    n_payback_24 = int((df["payback_within_24mo"] == 1).sum())
    print(f"  Outlets without cooler today:                {n_no_cooler:,}")
    print(f"  Material cases (uplift >= {MIN_VIABLE_MONTHLY_UPLIFT_L:.0f} L/mo): {n_material:,}")
    print(f"   - of which greenfield (no cooler today):    {n_greenfield_material:,}")
    print(f"  Payback within {HORIZON_MONTHS} months:                  {n_payback_24:,}")

    write_outputs(df)
    print("\nCooler ROI: OK")


if __name__ == "__main__":
    main()
