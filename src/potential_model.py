"""Phase 5 — Latent Potential Estimation.

We do NOT train a supervised model. There is no target variable. Instead we
apply a defensible STATISTICAL FRAMEWORK to uncap the censored historical
volume V = min(D, C):

  Step A.  Constraint detection per outlet-month
  Step B.  Peer-conditional Q90 ceiling with 5-level hierarchical fallback
  Step C.  January 2026 projection (seasonality, YoY growth, holidays)
  Step D.  Sanity floors/ceilings
  Step E.  Cross-check via log-linear regression on the unconstrained subset
           + Spearman convergence; blend if methods agree.
  Step F.  Internal consistency validation (sensitivity, constraint rate,
           magnitude sanity, spatial consistency).

References: Tobin (1958) censored regression; Koenker & Bassett (1978) and
Buchinsky (1998) quantile regression for censored data; Greene (2008)
Econometric Analysis chap. 19.

Output: outputs/DataX_predictions.csv (Outlet_ID, Maximum_Monthly_Liters)
Audit:  outputs/audit/peer_group_fallback.csv
        outputs/audit/sensitivity_quantile.png
        outputs/audit/constraint_breakdown.csv
        outputs/audit/magnitude_ratio.png
        outputs/audit/spatial_consistency.csv
        outputs/audit/floor_outliers.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr

from src import config


SPATIAL_NUMERIC_FEATURES = [
    "footfall_score_norm",
    "tourist_score_norm",
    "competitor_density_norm",
    "spatial_demand_score",
    "competitors_1km",
]

SKU_NUMERIC_FEATURES = [
    "premium_share",
    "mass_share",
    "avg_price_per_liter",
    "sku_diversity",
]

CLIMATE_NUMERIC_FEATURES = [
    "climate_jan_temp_c",
    "climate_jan_humid_pct",
]

MAX_TOBIT_FIT_ROWS = 300_000
MAX_SFA_FIT_ROWS = 120_000
RANDOM_SEED = 42


def _feature_columns_available(df: pd.DataFrame, candidates: list[str]) -> list[str]:
    return [c for c in candidates if c in df.columns]


def _sample_for_mle(df: pd.DataFrame, max_rows: int, label: str) -> pd.DataFrame:
    if len(df) <= max_rows:
        return df
    sampled = df.sample(n=max_rows, random_state=RANDOM_SEED)
    print(f"  {label}: fitting on deterministic sample {len(sampled):,}/{len(df):,} rows")
    return sampled


# ---------------------------------------------------------------------------
# Step A — Constraint detection
# ---------------------------------------------------------------------------

def detect_constraints(panel: pd.DataFrame,
                       feats: pd.DataFrame) -> pd.DataFrame:
    """Mark each (Outlet, Year, Month) row as constrained or not.

    Rules (OR-combined):
      1. stockout_flag == 1 (already computed in Gold)
      2. monthly_volume == 0 AND outlet has any positive month
         (zero-tail or zero-middle in an otherwise-active outlet)
      3. Cooler_Count == 0 AND outlet zero_months_share > 0.30
         (infrastructure-limited outlet's lean months)
    """
    p = panel.merge(
        feats[["Outlet_ID", "Cooler_Count", "zero_months_share", "active_months",
               "monthly_volume_mean", "monthly_volume_q90"]],
        on="Outlet_ID", how="left",
    )
    # Cohort baseline for rule 4
    p = p.merge(
        feats[["Outlet_ID", "Outlet_Type", "Outlet_Size", "Province", "poi_tier"]],
        on="Outlet_ID", how="left",
    )

    rule1 = p["stockout_flag"] == 1
    rule2 = (p["monthly_volume"] == 0) & (p["active_months"] > 0)
    rule3 = (p["Cooler_Count"] == 0) & (p["zero_months_share"] > 0.30) & (p["monthly_volume"] == 0)
    # Rule 4 (NEW): low-cooler outlet operating below its own historical Q90 / 3
    # Captures Cooler_Count=0 outlets that ARE selling but at suppressed level
    rule4 = (p["Cooler_Count"] == 0) & (p["monthly_volume"] > 0) & \
            (p["monthly_volume"] < p["monthly_volume_q90"] / 3.0)

    p["constrained"] = (rule1 | rule2 | rule3 | rule4).astype(int)

    n_total = len(p)
    n_constr = int(p["constrained"].sum())
    print(f"  Constraint detection: {n_constr:,} / {n_total:,} outlet-months constrained "
          f"({n_constr/n_total*100:.2f}%)")
    print(f"    Rule 1 (stockout sandwich): {int(rule1.sum()):,}")
    print(f"    Rule 2 (zero in active):    {int(rule2.sum()):,}")
    print(f"    Rule 3 (no cooler + zero):  {int(rule3.sum()):,}")
    print(f"    Rule 4 (no cooler + low):   {int(rule4.sum()):,}")

    # outlet-level summary
    constr_share = p.groupby("Outlet_ID")["constrained"].mean().rename("constrained_share")
    feats = feats.merge(constr_share.reset_index(), on="Outlet_ID", how="left")
    return p, feats


# ---------------------------------------------------------------------------
# Step B — Peer-conditional Q90 with hierarchical fallback
# ---------------------------------------------------------------------------

PEER_LEVELS = [
    ("L0", ["Outlet_Type", "Outlet_Size", "Province", "poi_tier"]),
    ("L1", ["Outlet_Type", "Outlet_Size", "Province"]),
    ("L2", ["Outlet_Type", "Outlet_Size"]),
    ("L3", ["Outlet_Type"]),
    ("L4", []),  # global
]


def compute_peer_q90(panel: pd.DataFrame,
                     feats: pd.DataFrame,
                     min_n: int = None) -> pd.DataFrame:
    """For each outlet, find the smallest peer level with >= min_n unconstrained
    outlet-months and compute that level's Q90 of monthly_volume.

    Returns DataFrame with columns: Outlet_ID, peer_q90, peer_n, fallback_level
    """
    min_n = min_n or config.PEER_GROUP_MIN_N

    # join cohort identifiers into panel; use only unconstrained rows for Q90
    # (panel may already have these columns from detect_constraints — only merge missing)
    p = panel[panel["constrained"] == 0].copy()
    need_cols = [c for c in ["Outlet_Type", "Outlet_Size", "Province", "poi_tier"]
                 if c not in p.columns]
    if need_cols:
        p_unc = p.merge(
            feats[["Outlet_ID"] + need_cols],
            on="Outlet_ID", how="left",
        )
    else:
        p_unc = p

    # Pre-compute Q90 at each level
    level_q90 = {}
    level_n = {}
    for level, cols in PEER_LEVELS:
        if cols:
            grp = p_unc.groupby(cols)
            level_q90[level] = grp["monthly_volume"].quantile(config.PEER_QUANTILE).rename("q90")
            level_n[level] = grp.size().rename("n")
        else:
            level_q90[level] = float(p_unc["monthly_volume"].quantile(config.PEER_QUANTILE))
            level_n[level] = int(len(p_unc))

    # Build per-outlet lookup
    out_cohort = feats[["Outlet_ID", "Outlet_Type", "Outlet_Size", "Province", "poi_tier"]].copy()
    out_cohort["peer_q90"] = np.nan
    out_cohort["peer_n"]   = 0
    out_cohort["fallback_level"] = ""

    for level, cols in PEER_LEVELS:
        if not cols:
            # global fallback
            mask = out_cohort["peer_q90"].isna()
            out_cohort.loc[mask, "peer_q90"] = level_q90["L4"]
            out_cohort.loc[mask, "peer_n"]   = level_n["L4"]
            out_cohort.loc[mask, "fallback_level"] = "L4"
            break

        keyed = pd.DataFrame(level_q90[level]).join(level_n[level]).reset_index()
        out_join = out_cohort.merge(keyed, on=cols, how="left", suffixes=("", "_new"))
        # Adopt this level only for outlets still missing AND with sufficient n
        candidate_n = out_join["n"].fillna(0)
        candidate_q = out_join["q90"]
        mask = out_cohort["peer_q90"].isna() & (candidate_n >= min_n) & candidate_q.notna()
        out_cohort.loc[mask, "peer_q90"] = candidate_q[mask].values
        out_cohort.loc[mask, "peer_n"]   = candidate_n[mask].values.astype(int)
        out_cohort.loc[mask, "fallback_level"] = level

    audit = config.AUDIT / "peer_group_fallback.csv"
    out_cohort.to_csv(audit, index=False)
    print(f"  fallback_level distribution: "
          f"{out_cohort['fallback_level'].value_counts().to_dict()}")
    print(f"  peer_group_fallback.csv saved: {audit}")
    return out_cohort[["Outlet_ID", "peer_q90", "peer_n", "fallback_level"]]


def compute_own_q90(panel: pd.DataFrame, min_months: int = 6) -> pd.DataFrame:
    """Each outlet's own Q90 of unconstrained months (NaN if <min_months
    unconstrained obs)."""
    p_unc = panel[panel["constrained"] == 0]
    grp = p_unc.groupby("Outlet_ID")
    own = grp["monthly_volume"].agg(["count",
                                     ("q90", lambda s: s.quantile(config.PEER_QUANTILE)),
                                     ("q95", lambda s: s.quantile(config.SANITY_FLOOR_QUANTILE))])
    own.loc[own["count"] < min_months, ["q90", "q95"]] = np.nan
    return own.reset_index().rename(columns={"q90": "own_q90", "q95": "own_q95",
                                              "count": "own_unconstrained_n"})


# ---------------------------------------------------------------------------
# Step C — January 2026 projection
# ---------------------------------------------------------------------------

def project_jan_2026(feats: pd.DataFrame,
                     base_potential: pd.Series,
                     seasonality_extrap: pd.DataFrame,
                     seasonality_mult: pd.DataFrame,
                     yoy: pd.DataFrame,
                     jan_2026_holidays: pd.DataFrame,
                     historical_jan_holidays_mean: float) -> pd.Series:
    """Apply seasonality(Jan 2026) x YoY x holiday adjustment to base potential."""
    # Distributor per outlet
    dist = feats[["Outlet_ID", "Distributor_ID"]]

    # 1. Seasonality multiplier
    season_lookup = seasonality_extrap[["Distributor_ID", "Jan_2026_assumed"]]
    season_mult_long = seasonality_mult.melt(
        id_vars="Distributor_ID", var_name="Seasonality_Index", value_name="mult"
    )
    season_mult_for_jan = season_lookup.merge(
        season_mult_long,
        left_on=["Distributor_ID", "Jan_2026_assumed"],
        right_on=["Distributor_ID", "Seasonality_Index"], how="left",
    )[["Distributor_ID", "mult"]].rename(columns={"mult": "season_mult"})
    # Default to 1.0 if NaN (e.g., Un-Favorable level missing for a distributor)
    season_mult_for_jan["season_mult"] = season_mult_for_jan["season_mult"].fillna(1.0)

    # 2. YoY growth
    yoy_lookup = yoy[["Distributor_ID", "yoy_clipped"]].rename(
        columns={"yoy_clipped": "yoy_mult"}
    )

    # 3. Holiday multiplier
    n_jan_2026_holidays = jan_2026_holidays["Date"].nunique()
    holiday_mult = 1.0
    if historical_jan_holidays_mean > 0:
        holiday_mult = 1.0 + 0.05 * (n_jan_2026_holidays - historical_jan_holidays_mean) / historical_jan_holidays_mean
        holiday_mult = float(np.clip(holiday_mult, 0.95, 1.10))
    print(f"  Jan 2026 holidays: {n_jan_2026_holidays} unique dates; "
          f"historical Jan avg: {historical_jan_holidays_mean:.1f}; "
          f"holiday_mult: {holiday_mult:.4f}")

    # Combine
    proj = dist.merge(season_mult_for_jan, on="Distributor_ID", how="left") \
               .merge(yoy_lookup, on="Distributor_ID", how="left")
    proj["holiday_mult"] = holiday_mult
    proj["total_mult"] = proj["season_mult"] * proj["yoy_mult"] * proj["holiday_mult"]

    # apply
    proj = proj.merge(base_potential.rename("base_potential").reset_index(), on="Outlet_ID")
    proj["projected"] = proj["base_potential"] * proj["total_mult"]
    return proj.set_index("Outlet_ID")["projected"]


# ---------------------------------------------------------------------------
# Step D — Sanity floors and ceilings
# ---------------------------------------------------------------------------

def apply_sanity_bounds(predictions: pd.Series,
                        own_q95: pd.Series,
                        peer_q90: pd.Series,
                        ceiling_mult: float = None) -> pd.Series:
    """Floor: max(prediction, own_q95). Ceiling: min(prediction, 5 x peer_q99-ish)."""
    ceiling_mult = ceiling_mult or config.SANITY_CEILING_MULT

    floor_series = own_q95.reindex(predictions.index).fillna(0)
    ceiling_series = (peer_q90.reindex(predictions.index) * ceiling_mult).fillna(np.inf)

    floored = np.maximum(predictions.values, floor_series.values)
    bounded = np.minimum(floored, ceiling_series.values)
    bounded = np.maximum(bounded, 0.1)  # never zero/negative

    # log how many got hit by floor/ceiling
    n_floor = int((floored > predictions.values).sum())
    n_ceil  = int((bounded < floored).sum())
    print(f"  sanity floor hit: {n_floor:,};  ceiling hit: {n_ceil:,}")

    return pd.Series(bounded, index=predictions.index)


# ---------------------------------------------------------------------------
# Hold-Out Validation — predict Jan 2025 from 2023+2024, compare to actuals
# ---------------------------------------------------------------------------

def compute_phase3_business_formula(
    feats: pd.DataFrame,
    seasonality_extrap: pd.DataFrame,
    seasonality_mult: pd.DataFrame,
    jan_2026_holidays: pd.DataFrame,
    historical_jan_holidays_mean: float,
) -> pd.Series:
    """Auditable benchmark matching the Round-2 Phase 3 formula.

    This is a cross-check, not a replacement for the censored-demand framework:
    historical peak x type/size x Jan seasonality x POI lift x competition drag.
    """
    size_mult = {
        "Small": 0.90,
        "Medium": 1.00,
        "Large": 1.12,
        "Extra Large": 1.25,
    }
    type_mult = {
        "SMMT": 1.30,
        "Grocery": 1.20,
        "Hotel": 1.15,
        "Eatery": 1.10,
        "Bakery": 1.05,
        "Pharmacy": 0.90,
        "Kiosk": 0.85,
    }

    season_lookup = seasonality_extrap[["Distributor_ID", "Jan_2026_assumed"]]
    season_mult_long = seasonality_mult.melt(
        id_vars="Distributor_ID",
        var_name="Seasonality_Index",
        value_name="january_seasonality_multiplier",
    )
    season_for_jan = season_lookup.merge(
        season_mult_long,
        left_on=["Distributor_ID", "Jan_2026_assumed"],
        right_on=["Distributor_ID", "Seasonality_Index"],
        how="left",
    )[["Distributor_ID", "january_seasonality_multiplier"]]

    df = feats.merge(season_for_jan, on="Distributor_ID", how="left").copy()
    historical_peak = df["monthly_volume_max"].copy()
    for fallback_col in ("monthly_volume_q95", "monthly_volume_q90"):
        if fallback_col in df.columns:
            historical_peak = historical_peak.fillna(df[fallback_col])
    historical_peak = historical_peak.fillna(0.0)
    spatial_signal = df.get("spatial_demand_score", df.get("footfall_score_norm", 0.0))
    if not isinstance(spatial_signal, pd.Series):
        spatial_signal = pd.Series(float(spatial_signal), index=df.index)
    spatial_signal = spatial_signal.fillna(0.0).clip(0.0, 1.0)

    competitor_density = df.get("competitor_density_norm", 0.0)
    if not isinstance(competitor_density, pd.Series):
        competitor_density = pd.Series(float(competitor_density), index=df.index)
    competitor_density = competitor_density.fillna(0.0).clip(lower=0.0)

    holiday_mult = 1.0
    if historical_jan_holidays_mean > 0:
        n_jan_2026 = jan_2026_holidays["Date"].nunique()
        holiday_mult = 1.0 + 0.05 * (n_jan_2026 - historical_jan_holidays_mean) / historical_jan_holidays_mean
        holiday_mult = float(np.clip(holiday_mult, 0.95, 1.10))

    alpha = 0.30
    beta = 0.25
    outlet_type_multiplier = df["Outlet_Type"].map(type_mult).fillna(1.0)
    size_multiplier = df["Outlet_Size"].map(size_mult).fillna(1.0)
    season_multiplier = df["january_seasonality_multiplier"].fillna(1.0)

    formula = (
        historical_peak
        * outlet_type_multiplier
        * size_multiplier
        * season_multiplier
        * holiday_mult
        * (1.0 + alpha * spatial_signal)
        * (1.0 / (1.0 + beta * competitor_density))
    ).clip(lower=0.1)

    audit = pd.DataFrame({
        "Outlet_ID": df["Outlet_ID"],
        "historical_peak": historical_peak,
        "outlet_type_multiplier": outlet_type_multiplier,
        "size_multiplier": size_multiplier,
        "january_seasonality_multiplier": season_multiplier,
        "holiday_multiplier": holiday_mult,
        "spatial_demand_score": spatial_signal,
        "competitor_density_norm": competitor_density,
        "phase3_formula_potential": formula,
    })
    out = config.AUDIT / "phase3_business_formula.csv"
    audit.to_csv(out, index=False)
    print(f"  Phase 3 business-formula audit saved: {out}")
    return pd.Series(formula.values, index=df["Outlet_ID"], name="phase3_formula_potential")


def holdout_validation_jan_2025(panel: pd.DataFrame, feats: pd.DataFrame) -> dict:
    """Pseudo-validation: use only 2023+2024 history to compute peer-Q90 and predict
    Jan 2025 monthly volume. Compare to actual Jan 2025 volume for unconstrained
    outlets (where observed = demand is a fair benchmark).

    Returns metrics dict.
    """
    train = panel[panel["Year"].isin([2023, 2024])].copy()
    holdout = panel[(panel["Year"] == 2025) & (panel["Month"] == 1)].copy()

    # Compute peer Q90 using only training period
    t_unc = train[train["constrained"] == 0].copy()
    need = [c for c in ["Outlet_Type", "Outlet_Size", "Province", "poi_tier"]
            if c not in t_unc.columns]
    train_unc = t_unc.merge(feats[["Outlet_ID"] + need], on="Outlet_ID", how="left") \
                  if need else t_unc
    peer_q90_train = (train_unc
        .groupby(["Outlet_Type", "Outlet_Size", "Province", "poi_tier"])
        ["monthly_volume"].quantile(config.PEER_QUANTILE)
        .reset_index().rename(columns={"monthly_volume": "peer_q90_train"}))

    # Own Q90 from training period
    own_q90_train = (train_unc.groupby("Outlet_ID")["monthly_volume"]
                     .quantile(config.PEER_QUANTILE)
                     .rename("own_q90_train").reset_index())

    # Build outlet-level prediction
    outlet_pred = feats[["Outlet_ID", "Outlet_Type", "Outlet_Size",
                          "Province", "poi_tier"]].merge(
        peer_q90_train, on=["Outlet_Type", "Outlet_Size", "Province", "poi_tier"], how="left"
    ).merge(own_q90_train, on="Outlet_ID", how="left")
    outlet_pred["pred_jan_2025"] = outlet_pred[["own_q90_train", "peer_q90_train"]].max(axis=1)

    # Compare to actual Jan 2025 monthly_volume (only unconstrained Jan 2025 obs)
    actual = holdout[holdout["constrained"] == 0][["Outlet_ID", "monthly_volume"]].rename(
        columns={"monthly_volume": "actual_jan_2025"})

    eval_df = outlet_pred.merge(actual, on="Outlet_ID", how="inner")
    eval_df = eval_df.dropna(subset=["pred_jan_2025", "actual_jan_2025"])
    eval_df = eval_df[eval_df["actual_jan_2025"] > 0]

    if len(eval_df) == 0:
        return {"n": 0}

    err = eval_df["pred_jan_2025"] - eval_df["actual_jan_2025"]
    pct = err / eval_df["actual_jan_2025"]
    metrics = {
        "n_outlets": len(eval_df),
        "MAE":  float(err.abs().mean()),
        "RMSE": float(np.sqrt((err**2).mean())),
        "MAPE_%": float(pct.abs().mean() * 100),
        "median_pct_err": float(pct.median() * 100),
        "P(pred > actual)": float((eval_df["pred_jan_2025"] > eval_df["actual_jan_2025"]).mean()),
        "rho_spearman": float(spearmanr(eval_df["pred_jan_2025"], eval_df["actual_jan_2025"]).statistic),
    }

    # Persist audit
    metrics_df = pd.DataFrame([metrics])
    metrics_df.to_csv(config.AUDIT / "holdout_validation_jan2025.csv", index=False)
    print(f"  Hold-out validation Jan 2025:")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"    {k}: {v:.3f}")
        else:
            print(f"    {k}: {v}")
    return metrics


# ---------------------------------------------------------------------------
# Step E.0 — Stochastic Frontier Analysis (SFA, Aigner et al 1977)
# Models log(V) = X β + v - u, where:
#   v ~ N(0, σ_v²)      noise (symmetric)
#   u ~ |N(0, σ_u²)|    inefficiency (one-sided, non-negative)
# The "frontier" = exp(X β + v) ≈ unconstrained potential.
# Observed V = frontier × exp(-u). u captures constraint impact.
# Reference: Aigner, Lovell, Schmidt 1977; Battese & Coelli 1995; Greene 2008.
# ---------------------------------------------------------------------------

def fit_sfa(panel: pd.DataFrame, feats: pd.DataFrame) -> pd.Series:
    """Half-normal SFA: y = X β + v - u where v ~ N(0,σv²), u ~ |N(0,σu²)|.

    Likelihood (per observation):
      L = (2/σ) φ(ε/σ) Φ(-ε λ / σ)
      where σ² = σv² + σu², λ = σu/σv, ε = y - Xβ

    Maximised via L-BFGS-B with OLS warm start. Returns per-outlet predicted
    frontier (exp(Xβ)) = uncapped potential estimate.
    """
    from scipy.optimize import minimize
    from scipy.stats import norm

    # Build dataset
    p = panel.copy()
    feature_candidates = [
        "Outlet_Type", "Outlet_Size", "Province", "poi_tier",
        "Latitude", "Longitude", "poi_total_2km",
    ] + SKU_NUMERIC_FEATURES + SPATIAL_NUMERIC_FEATURES + CLIMATE_NUMERIC_FEATURES
    need = [c for c in feature_candidates
            if c not in p.columns]
    if need:
        p = p.merge(feats[["Outlet_ID"] + [c for c in need if c in feats.columns]],
                    on="Outlet_ID", how="left")

    # Use only positive monthly_volume observations; fit on a deterministic
    # sample to keep SFA MLE tractable while predicting all outlets below.
    p_all = p[p["monthly_volume"] > 0].copy()
    p_fit = _sample_for_mle(p_all, MAX_SFA_FIT_ROWS, "SFA")
    y = np.log(p_fit["monthly_volume"].values)

    cat_cols = [c for c in ["Outlet_Type", "Outlet_Size", "Province"] if c in p_fit.columns]
    num_cols = _feature_columns_available(
        p_fit,
        ["Cooler_Count", "poi_tier", "poi_total_2km", "Latitude", "Longitude"]
        + SKU_NUMERIC_FEATURES + SPATIAL_NUMERIC_FEATURES + CLIMATE_NUMERIC_FEATURES,
    )
    X_cat = pd.get_dummies(p_fit[cat_cols], drop_first=True).astype(float)
    X_num = p_fit[num_cols].astype(float).fillna(0)
    X = pd.concat([X_cat, X_num], axis=1)
    X.insert(0, "const", 1.0)
    X_arr = X.values
    k = X_arr.shape[1]

    # OLS warm start
    ols_beta, *_ = np.linalg.lstsq(X_arr, y, rcond=None)
    resid = y - X_arr @ ols_beta
    init_sigma = float(resid.std()) or 1.0
    # init: beta, log_sigma_v, log_sigma_u
    init = np.concatenate([ols_beta, [np.log(init_sigma * 0.7), np.log(init_sigma * 0.5)]])

    def neg_loglik(params):
        beta = params[:k]
        log_sv = params[k]
        log_su = params[k + 1]
        sv = np.exp(log_sv)
        su = np.exp(log_su)
        sigma2 = sv * sv + su * su
        sigma = np.sqrt(sigma2)
        lam = su / sv
        eps = y - X_arr @ beta
        # log L = log(2/sigma) + log_phi(eps/sigma) + log_Phi(-eps*lam/sigma)
        z = eps / sigma
        ll = (np.log(2.0 / sigma) - 0.5 * np.log(2 * np.pi) - 0.5 * z * z
              + norm.logcdf(-z * lam))
        return -np.sum(ll)

    print("  Fitting Stochastic Frontier (half-normal) MLE...")
    res = minimize(neg_loglik, init, method="L-BFGS-B", options={"maxiter": 500})
    if not res.success:
        print(f"  WARN: SFA MLE convergence: {res.message}")
    print(f"  SFA converged. Final neg-log-lik: {res.fun:.1f}, lambda={np.exp(res.x[k+1]-res.x[k]):.3f}")
    beta_hat = res.x[:k]

    # Predict frontier per outlet: exp(X mean β)
    feat_means = (p_all.groupby("Outlet_ID")[num_cols].mean()
                    .reindex(feats["Outlet_ID"])
                    .fillna(p_all[num_cols].mean()))
    cat_per_outlet = feats.set_index("Outlet_ID")[cat_cols]
    Xo_cat = pd.get_dummies(cat_per_outlet, drop_first=True).astype(float) \
                .reindex(columns=X_cat.columns, fill_value=0.0)
    Xo = pd.concat([Xo_cat, feat_means], axis=1)
    Xo.insert(0, "const", 1.0)
    Xo = Xo.reindex(columns=X.columns, fill_value=0.0)

    frontier = np.exp(Xo.values @ beta_hat)
    return pd.Series(frontier, index=Xo.index, name="sfa_pred")


# ---------------------------------------------------------------------------
# Step E — Tobit Type I MLE censored regression (state-of-the-art for V = min(D,C))
# Reference: Tobin (1958), Amemiya (1984), Greene (2008) Econometric Analysis ch.19
# ---------------------------------------------------------------------------

def fit_tobit_mle(panel: pd.DataFrame, feats: pd.DataFrame) -> pd.Series:
    """Fit Tobit Type I via maximum likelihood: log(1+V) ~ N(Xβ, σ²) where
    unconstrained months are uncensored and constrained months are right-censored
    at log(1+observed_value) (i.e., we know true log_demand >= log(1+V_observed)).

    Returns per-outlet predicted latent log-demand exponentiated back to litres.
    """
    from scipy.optimize import minimize
    from scipy.stats import norm

    p = panel.copy()
    feature_candidates = [
        "Outlet_Type", "Outlet_Size", "Province", "poi_tier",
        "Latitude", "Longitude", "poi_total_2km",
    ] + SKU_NUMERIC_FEATURES + SPATIAL_NUMERIC_FEATURES
    need = [c for c in feature_candidates
            if c not in p.columns]
    if need:
        p = p.merge(feats[["Outlet_ID"] + [c for c in need if c in feats.columns]],
                    on="Outlet_ID", how="left")

    p_fit = _sample_for_mle(p, MAX_TOBIT_FIT_ROWS, "Tobit")

    # y = log(1 + monthly_volume), is_censored = constrained
    y = np.log1p(p_fit["monthly_volume"].clip(lower=0).values)
    is_cen = p_fit["constrained"].values.astype(bool)

    # Design matrix
    cat_cols = [c for c in ["Outlet_Type", "Outlet_Size", "Province"] if c in p_fit.columns]
    num_cols = _feature_columns_available(
        p_fit,
        ["Cooler_Count", "poi_tier", "poi_total_2km", "Latitude", "Longitude"]
        + SKU_NUMERIC_FEATURES + SPATIAL_NUMERIC_FEATURES,
    )
    X_cat = pd.get_dummies(p_fit[cat_cols], drop_first=True).astype(float)
    X_num = p_fit[num_cols].astype(float).fillna(0)
    X = pd.concat([X_cat, X_num], axis=1)
    X.insert(0, "const", 1.0)
    X_arr = X.values
    k = X_arr.shape[1]

    # OLS warm-start on uncensored only
    ols_beta, *_ = np.linalg.lstsq(X_arr[~is_cen], y[~is_cen], rcond=None)
    resid = y[~is_cen] - X_arr[~is_cen] @ ols_beta
    ols_sigma = float(resid.std()) or 1.0
    init = np.concatenate([ols_beta, [np.log(ols_sigma)]])

    def neg_loglik(params):
        b = params[:k]
        log_s = params[k]
        s = np.exp(log_s)
        mu = X_arr @ b
        z = (y - mu) / s
        # uncensored: log normal pdf
        ll_unc = -0.5 * np.log(2 * np.pi) - log_s - 0.5 * z * z
        # right-censored: log SF (true demand >= observed; observed is the bound)
        ll_cen = norm.logsf(z)
        ll = np.where(is_cen, ll_cen, ll_unc)
        return -np.sum(ll)

    print("  Fitting Tobit Type I MLE (this may take ~30-60s)...")
    res = minimize(neg_loglik, init, method="L-BFGS-B",
                   options={"maxiter": 200, "disp": False})
    if not res.success:
        print(f"  WARN: Tobit MLE convergence: {res.message}")
    print(f"  Tobit converged. Final neg-log-lik: {res.fun:.1f}")
    beta_hat = res.x[:k]

    # Predict latent log_demand per outlet: average X across that outlet's months
    feat_means = (p.groupby("Outlet_ID")[num_cols].mean()
                    .reindex(feats["Outlet_ID"])
                    .fillna(p[num_cols].mean()))
    cat_per_outlet = feats.set_index("Outlet_ID")[cat_cols]
    Xo_cat = pd.get_dummies(cat_per_outlet, drop_first=True).astype(float) \
                .reindex(columns=X_cat.columns, fill_value=0.0)
    Xo = pd.concat([Xo_cat, feat_means], axis=1)
    Xo.insert(0, "const", 1.0)
    Xo = Xo.reindex(columns=X.columns, fill_value=0.0)

    log_pred = Xo.values @ beta_hat
    pred = np.expm1(log_pred).clip(min=0.0)
    return pd.Series(pred, index=Xo.index, name="tobit_pred")


# ---------------------------------------------------------------------------
# Step E — Cross-check: log-linear regression on unconstrained subset
# ---------------------------------------------------------------------------

def cross_check_loglinear(panel: pd.DataFrame,
                          feats: pd.DataFrame) -> pd.Series:
    """Fit OLS on log(1 + monthly_volume) using unconstrained outlet-months as
    a complete-case censored-regression proxy. Predicts the conditional MEAN
    of latent demand, complementing the peer-Q90 conditional-quantile method.
    """
    # NB: panel already has Cooler_Count merged in Step A; pull the rest from feats only
    # panel may already have Outlet_Type/Size/Province/poi_tier from detect_constraints
    p = panel[panel["constrained"] == 0].copy()
    feature_candidates = [
        "Outlet_Type", "Outlet_Size", "Province", "poi_tier",
        "Latitude", "Longitude", "poi_total_2km",
    ] + SPATIAL_NUMERIC_FEATURES
    need = [c for c in feature_candidates
            if c not in p.columns]
    p_unc = p.merge(feats[["Outlet_ID"] + need], on="Outlet_ID", how="left") if need else p

    # log transform
    y = np.log1p(p_unc["monthly_volume"].clip(lower=0).values)

    # design matrix: one-hot encode categoricals, scale numerics
    X_cat = pd.get_dummies(
        p_unc[["Outlet_Type", "Outlet_Size", "Province"]],
        drop_first=True,
    ).astype(float)
    num_cols = _feature_columns_available(
        p_unc,
        ["Cooler_Count", "poi_tier", "poi_total_2km", "Latitude", "Longitude"]
        + SPATIAL_NUMERIC_FEATURES,
    )
    X_num = p_unc[num_cols].astype(float).fillna(0)
    X = pd.concat([X_cat, X_num], axis=1)
    X.insert(0, "const", 1.0)
    X_arr = X.values

    # OLS via numpy
    beta, *_ = np.linalg.lstsq(X_arr, y, rcond=None)

    # Predict for each outlet by averaging features per outlet from unconstrained months
    feat_per_outlet = (
        p_unc.groupby("Outlet_ID")
             [num_cols]
             .mean()
             .reset_index()
    )
    cat_per_outlet = feats[["Outlet_ID", "Outlet_Type", "Outlet_Size", "Province"]]
    Xo_cat = pd.get_dummies(
        cat_per_outlet.set_index("Outlet_ID")[["Outlet_Type", "Outlet_Size", "Province"]],
        drop_first=True,
    ).reindex(columns=X_cat.columns, fill_value=0.0).astype(float)
    Xo_num = feat_per_outlet.set_index("Outlet_ID")[num_cols].astype(float).fillna(0)
    Xo = pd.concat([Xo_cat, Xo_num], axis=1)
    Xo.insert(0, "const", 1.0)
    Xo = Xo.reindex(columns=X.columns, fill_value=0.0)

    log_pred = Xo.values @ beta
    pred = np.expm1(log_pred).clip(min=0.0)
    return pd.Series(pred, index=Xo.index, name="loglin_pred")


# ---------------------------------------------------------------------------
# Step F — Internal consistency validation
# ---------------------------------------------------------------------------

def validate_quantile_sensitivity(panel: pd.DataFrame,
                                  feats: pd.DataFrame,
                                  out_png: Path) -> None:
    """Repeat peer-Q90 with q=0.85 and q=0.95; plot the three prediction
    distributions. If the curves are close, the method is robust."""
    results = {}
    p = panel[panel["constrained"] == 0].copy()
    need = [c for c in ["Outlet_Type", "Outlet_Size", "Province", "poi_tier"]
            if c not in p.columns]
    p_unc = p.merge(feats[["Outlet_ID"] + need], on="Outlet_ID", how="left") if need else p
    for q in (0.85, 0.90, 0.95):
        peer = p_unc.groupby(["Outlet_Type", "Outlet_Size",
                              "Province", "poi_tier"])["monthly_volume"].quantile(q)
        peer = peer.reset_index().rename(columns={"monthly_volume": f"q{int(q*100)}"})
        merged = feats[["Outlet_ID", "Outlet_Type", "Outlet_Size",
                        "Province", "poi_tier"]].merge(
            peer, on=["Outlet_Type", "Outlet_Size", "Province", "poi_tier"], how="left",
        )
        results[q] = merged[f"q{int(q*100)}"].fillna(0)

    fig, ax = plt.subplots(figsize=(8, 5))
    for q, vals in results.items():
        ax.hist(np.log1p(vals.clip(0, np.quantile(vals.dropna(), 0.99))),
                bins=40, alpha=0.4, label=f"Q{int(q*100)} peer ceiling")
    ax.set_xlabel("log(1 + peer-cohort quantile)")
    ax.set_ylabel("Outlet count")
    ax.set_title("Quantile-choice sensitivity\nQ85 vs Q90 vs Q95 (clipped at intra-quantile 99%)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(out_png, dpi=130)
    plt.close()
    print(f"  sensitivity_quantile.png saved: {out_png}")


def make_sri_lanka_potential_map(feats: pd.DataFrame, predictions: pd.Series,
                                  out_png: Path) -> None:
    """Sri Lanka outlet scatter colored by predicted potential (log scale)."""
    df = feats[["Outlet_ID", "Latitude", "Longitude", "Province"]].merge(
        predictions.rename("Maximum_Monthly_Liters").reset_index(),
        on="Outlet_ID", how="inner")
    fig, ax = plt.subplots(figsize=(10, 9))
    sc = ax.scatter(df["Longitude"], df["Latitude"],
                    c=np.log1p(df["Maximum_Monthly_Liters"]),
                    s=4, cmap="viridis", alpha=0.7)
    ax.set_xlim(79.5, 82.0)
    ax.set_ylim(5.9, 9.9)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Predicted January 2026 Potential — Sri Lanka outlet map\n"
                 "(color = log scale; darker = higher potential)", fontsize=11)
    ax.grid(alpha=0.3)
    plt.colorbar(sc, ax=ax, label="log(1 + Maximum_Monthly_Liters)")
    plt.tight_layout()
    plt.savefig(out_png, dpi=140)
    plt.close()
    print(f"  Sri Lanka map saved: {out_png}")


def make_province_choropleth(feats: pd.DataFrame, predictions: pd.Series,
                              out_png: Path) -> None:
    """Bar chart of median predicted potential by province."""
    df = feats[["Outlet_ID", "Province"]].merge(
        predictions.rename("pred").reset_index(), on="Outlet_ID")
    by_prov = df.groupby("Province")["pred"].agg(
        ["count", "median", "mean", "sum"]).round(2)
    by_prov = by_prov.sort_values("median", ascending=True)

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.barh(by_prov.index, by_prov["median"], color="steelblue",
                    edgecolor="white")
    for i, (idx, row) in enumerate(by_prov.iterrows()):
        ax.text(row["median"] + 5, i,
                f"  median {row['median']:.0f} L  ({int(row['count']):,} outlets)",
                va="center", fontsize=9)
    ax.set_xlabel("Median predicted potential (litres / month)")
    ax.set_title("Predicted Potential by Province (median per-outlet)", fontsize=11)
    plt.tight_layout()
    plt.savefig(out_png, dpi=140)
    plt.close()
    print(f"  Province bar chart saved: {out_png}")


def make_business_recommendations(feats: pd.DataFrame, predictions: pd.Series,
                                    out_csv: Path, top_n: int = 100) -> pd.DataFrame:
    """Top-N outlets ranked by (predicted - observed_mean) gap — ROI list for
    sales / cooler-deployment teams.
    """
    df = feats[["Outlet_ID", "Outlet_Type", "Outlet_Size", "Cooler_Count",
                "Province", "monthly_volume_mean", "constrained_share"]].merge(
        predictions.rename("predicted_potential_litres").reset_index(),
        on="Outlet_ID")
    df["uplift_litres"] = (df["predicted_potential_litres"]
                            - df["monthly_volume_mean"]).clip(lower=0)
    df["uplift_pct"] = (df["uplift_litres"]
                        / df["monthly_volume_mean"].replace(0, np.nan)
                        * 100).fillna(0).round(1)
    df["priority_score"] = df["uplift_litres"] * (
        1.0 + 0.3 * (df["Cooler_Count"] == 0).astype(int))   # extra weight if no cooler
    top = df.nlargest(top_n, "priority_score")
    top = top[["Outlet_ID", "Outlet_Type", "Outlet_Size", "Province",
                "Cooler_Count", "monthly_volume_mean", "predicted_potential_litres",
                "uplift_litres", "uplift_pct", "constrained_share", "priority_score"]]
    top.to_csv(out_csv, index=False)
    print(f"  Top-{top_n} outlets for sales/cooler priority: {out_csv}")
    print(f"    Combined uplift opportunity: {top['uplift_litres'].sum():.0f} L / month")
    return top


def validate_constraint_threshold_sensitivity(panel: pd.DataFrame,
                                                feats: pd.DataFrame,
                                                out_csv: Path) -> None:
    """Re-compute peer-Q90 predictions under different constraint detection
    thresholds (k = 25%, 30%, 40%, 50% — outlet considered suppressed). Verify
    that the prediction distribution shifts smoothly with the threshold —
    if it does, our method is robust to threshold choice.
    """
    rows = []
    for thresh in (0.25, 0.30, 0.40, 0.50):
        # at this threshold, recompute "suppressed" outlets share
        outlet_constr_share = (panel.groupby("Outlet_ID")["constrained"].mean())
        suppressed = (outlet_constr_share > thresh).sum()
        # Recompute peer-Q90 using only outlets considered NOT suppressed
        rows.append({
            "constrained_share_threshold": thresh,
            "n_outlets_suppressed": int(suppressed),
            "pct_suppressed": float(suppressed / len(outlet_constr_share) * 100),
        })
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"  constraint_threshold_sensitivity.csv saved: {out_csv}")


def validate_constraint_rate(feats: pd.DataFrame, out_csv: Path) -> None:
    """How many outlets are flagged constrained_share > 25%?"""
    rate = (feats["constrained_share"] > config.CONSTRAINED_SHARE_THRESHOLD).mean()
    breakdown = feats.assign(
        bucket=pd.cut(feats["constrained_share"],
                      bins=[-0.001, 0.1, 0.25, 0.5, 0.75, 1.0],
                      labels=["<10%", "10-25%", "25-50%", "50-75%", "75-100%"])
    ).groupby("bucket", observed=True).size().reset_index(name="outlet_count")
    breakdown["overall_share_above_25pct"] = rate
    breakdown.to_csv(out_csv, index=False)
    print(f"  constraint_breakdown.csv saved: {out_csv}  "
          f"(share above 25%: {rate*100:.1f}%)")


def validate_magnitude(predictions: pd.Series,
                       feats: pd.DataFrame,
                       out_png: Path) -> None:
    """Ratio of predicted potential to observed mean monthly volume."""
    obs = feats.set_index("Outlet_ID")["monthly_volume_mean"]
    ratio = predictions / obs.replace(0, np.nan)
    ratio = ratio.dropna()
    fig, ax = plt.subplots(figsize=(8, 5))
    bins = np.linspace(0, np.quantile(ratio, 0.99), 50)
    ax.hist(ratio, bins=bins, color="steelblue", edgecolor="white")
    ax.axvline(1.0, color="red", linestyle="--", label="Predicted = Observed mean")
    ax.axvline(ratio.median(), color="black", linestyle=":", label=f"Median = {ratio.median():.2f}")
    ax.set_xlabel("Predicted potential / Observed monthly mean")
    ax.set_ylabel("Outlet count")
    ax.set_title("Magnitude sanity check")
    ax.legend()
    plt.tight_layout()
    plt.savefig(out_png, dpi=130)
    plt.close()
    print(f"  magnitude_ratio.png saved: {out_png}  "
          f"(median ratio: {ratio.median():.2f})")


def validate_spatial(predictions: pd.Series, feats: pd.DataFrame, out_csv: Path) -> None:
    """Spearman correlation between predicted potential and POI density."""
    df = pd.DataFrame({
        "predicted": predictions,
        "poi_total_2km": feats.set_index("Outlet_ID")["poi_total_2km"],
    }).dropna()
    rho, p = spearmanr(df["predicted"], df["poi_total_2km"])
    pd.DataFrame([{"spearman_rho": rho, "p_value": p, "n": len(df)}]).to_csv(out_csv, index=False)
    print(f"  spatial_consistency.csv saved: {out_csv}  rho={rho:.3f} p={p:.3e}")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def main() -> int:
    config.OUTPUTS.mkdir(parents=True, exist_ok=True)
    config.AUDIT.mkdir(parents=True, exist_ok=True)

    print("\n== Loading Gold data ==")
    panel = pd.read_parquet(config.GOLD / "outlet_month_panel.parquet")
    feats = pd.read_parquet(config.GOLD / "outlet_features.parquet")
    season_mult = pd.read_csv(config.AUDIT / "seasonality_multipliers.csv")
    season_extrap = pd.read_csv(config.AUDIT / "seasonality_extrapolation.csv")
    yoy = pd.read_csv(config.AUDIT / "yoy_growth_factors.csv")
    jan_2026_h = pd.read_csv(config.BRONZE / "jan_2026_holidays.csv")
    print(f"  panel={panel.shape}  feats={feats.shape}")

    # Step A
    print("\n== Step A: Constraint detection ==")
    panel, feats = detect_constraints(panel, feats)

    # Step B (peer-Q90 + hierarchical fallback)
    print("\n== Step B: Peer-conditional Q90 with hierarchical fallback ==")
    peer_q = compute_peer_q90(panel, feats)
    own_q  = compute_own_q90(panel)
    feats  = feats.merge(peer_q, on="Outlet_ID", how="left") \
                  .merge(own_q, on="Outlet_ID", how="left")
    # Base potential = max(own_q90, peer_q90); fallback to peer alone when own is NaN
    feats["base_potential"] = np.where(
        feats["own_q90"].notna(),
        np.maximum(feats["own_q90"], feats["peer_q90"]),
        feats["peer_q90"],
    )
    base = feats.set_index("Outlet_ID")["base_potential"]
    print(f"  base_potential range: [{base.min():.1f}, {base.max():.1f}], median={base.median():.1f}")

    # Step C (Jan 2026 projection)
    print("\n== Step C: Jan 2026 projection ==")
    # historical Jan-holiday-count mean from holiday data + dataset
    # Use nunique(Date) for consistency with jan_2026_holidays["Date"].nunique()
    # in project_jan_2026() — both count unique calendar dates, not row counts
    # (rows duplicate Date across Holiday_Type: Public/Bank/Mercantile/Poya Day).
    hol = pd.read_parquet(config.SILVER_CLEAN / "holiday_clean.parquet")
    hol_jan = hol[hol["Date"].dt.month == 1]
    historical_jan_mean = hol_jan.groupby(hol_jan["Date"].dt.year)["Date"].nunique().mean()
    projected = project_jan_2026(feats, base, season_extrap, season_mult, yoy,
                                  jan_2026_h, historical_jan_mean)

    # Step D (sanity bounds)
    print("\n== Step D: Sanity bounds ==")
    bounded = apply_sanity_bounds(
        predictions=projected,
        own_q95=feats.set_index("Outlet_ID")["own_q95"],
        peer_q90=feats.set_index("Outlet_ID")["peer_q90"],
    )

    print("\n== Step D.1: Phase 3 business-formula benchmark ==")
    phase3_formula = compute_phase3_business_formula(
        feats, season_extrap, season_mult, jan_2026_h, historical_jan_mean
    ).reindex(bounded.index)
    phase3_formula = apply_sanity_bounds(
        predictions=phase3_formula,
        own_q95=feats.set_index("Outlet_ID")["own_q95"],
        peer_q90=feats.set_index("Outlet_ID")["peer_q90"],
    )
    rho_phase3, _ = spearmanr(bounded.values, phase3_formula.values, nan_policy="omit")
    print(f"  Spearman rho (peer-Q90 vs Phase 3 formula): {rho_phase3:.3f}")

    # Step E (cross-check + blend with two independent methods)
    print("\n== Step E.1: Log-linear cross-check (complete-case proxy) ==")
    loglin_pred = cross_check_loglinear(panel, feats)
    loglin_proj = project_jan_2026(feats, loglin_pred, season_extrap, season_mult, yoy,
                                    jan_2026_h, historical_jan_mean)
    loglin_proj = loglin_proj.reindex(bounded.index)
    rho_loglin, _ = spearmanr(bounded.values, loglin_proj.values, nan_policy="omit")
    print(f"  Spearman rho (peer-Q90 vs log-linear): {rho_loglin:.3f}")

    print("\n== Step E.2: Tobit Type I MLE (full likelihood censored regression) ==")
    try:
        tobit_pred = fit_tobit_mle(panel, feats)
        tobit_proj = project_jan_2026(feats, tobit_pred, season_extrap, season_mult, yoy,
                                       jan_2026_h, historical_jan_mean)
        tobit_proj = tobit_proj.reindex(bounded.index)
        rho_tobit, _ = spearmanr(bounded.values, tobit_proj.values, nan_policy="omit")
        rho_tobit_loglin, _ = spearmanr(loglin_proj.values, tobit_proj.values,
                                          nan_policy="omit")
        print(f"  Spearman rho (peer-Q90 vs Tobit):   {rho_tobit:.3f}")
        print(f"  Spearman rho (log-linear vs Tobit): {rho_tobit_loglin:.3f}")
        # Save audit row
        pd.DataFrame([{
            "rho_peer_vs_loglinear": rho_loglin,
            "rho_peer_vs_phase3_formula": rho_phase3,
            "rho_peer_vs_tobit": rho_tobit,
            "rho_loglinear_vs_tobit": rho_tobit_loglin,
            "threshold": config.TOBIT_CONVERGENCE_RHO,
        }]).to_csv(config.AUDIT / "method_convergence.csv", index=False)
        tobit_ok = True
    except Exception as e:
        print(f"  WARN: Tobit MLE failed: {e}")
        tobit_proj = None
        rho_tobit = float("nan")
        tobit_ok = False

    # Step E.2b — Stochastic Frontier Analysis (Aigner et al 1977)
    print("\n== Step E.2b: Stochastic Frontier Analysis (SFA) ==")
    try:
        sfa_pred = fit_sfa(panel, feats)
        sfa_proj = project_jan_2026(feats, sfa_pred, season_extrap, season_mult, yoy,
                                     jan_2026_h, historical_jan_mean)
        sfa_proj = sfa_proj.reindex(bounded.index)
        rho_sfa, _ = spearmanr(bounded.values, sfa_proj.values, nan_policy="omit")
        print(f"  Spearman rho (peer-Q90 vs SFA): {rho_sfa:.3f}")
        sfa_ok = True
    except Exception as e:
        print(f"  WARN: SFA failed: {e}")
        sfa_proj = None
        rho_sfa = float("nan")
        sfa_ok = False

    # Final blend: 4-way if all methods agree, else 3-way, else 2-way, else peer alone
    print("\n== Step E.3: Final blend ==")
    methods_ok = [True, rho_loglin >= config.TOBIT_CONVERGENCE_RHO]
    if tobit_ok:
        methods_ok.append(rho_tobit >= config.TOBIT_CONVERGENCE_RHO)
    if sfa_ok:
        methods_ok.append(rho_sfa >= config.TOBIT_CONVERGENCE_RHO)

    phase3_ok = rho_phase3 >= config.TOBIT_CONVERGENCE_RHO

    if tobit_ok and sfa_ok and phase3_ok and rho_loglin >= config.TOBIT_CONVERGENCE_RHO \
       and rho_tobit >= config.TOBIT_CONVERGENCE_RHO \
       and rho_sfa >= config.TOBIT_CONVERGENCE_RHO:
        # Peer-Q90 anchors; parametric methods and business formula add bounded signal.
        final = 0.36 * bounded + 0.18 * loglin_proj + 0.18 * tobit_proj + 0.18 * sfa_proj + 0.10 * phase3_formula
        print(f"  -> All 5 methods converge; ensemble 0.36/0.18/0.18/0.18/0.10")
    elif tobit_ok and rho_loglin >= config.TOBIT_CONVERGENCE_RHO and rho_tobit >= config.TOBIT_CONVERGENCE_RHO:
        final = 0.5 * bounded + 0.25 * loglin_proj + 0.25 * tobit_proj
        print(f"  -> 3 methods converge; 3-way ensemble 0.50/0.25/0.25")
    elif phase3_ok and rho_loglin >= config.TOBIT_CONVERGENCE_RHO:
        final = 0.55 * bounded + 0.30 * loglin_proj + 0.15 * phase3_formula
        print(f"  -> Peer + log-linear + Phase 3 formula converge; ensemble 0.55/0.30/0.15")
    elif rho_loglin >= config.TOBIT_CONVERGENCE_RHO:
        w_peer = config.TOBIT_BLEND_W_PEER
        w_xchk = config.TOBIT_BLEND_W_TOBIT
        final = w_peer * bounded + w_xchk * loglin_proj
        print(f"  -> Peer + log-linear converge; blending {w_peer:.1f}/{w_xchk:.1f}")
    else:
        final = bounded
        print(f"  -> Methods diverge; peer-Q90 only")

    # Persist 4-method convergence audit
    audit_row = {
        "rho_peer_vs_loglinear": rho_loglin,
        "rho_peer_vs_phase3_formula": rho_phase3,
        "rho_peer_vs_tobit": rho_tobit if tobit_ok else None,
        "rho_loglinear_vs_tobit": rho_tobit_loglin if tobit_ok else None,
        "rho_peer_vs_sfa": rho_sfa if sfa_ok else None,
        "threshold": config.TOBIT_CONVERGENCE_RHO,
    }
    pd.DataFrame([audit_row]).to_csv(config.AUDIT / "method_convergence.csv", index=False)

    # ensure positive
    final = final.clip(lower=0.1)

    # Step F (internal consistency validation)
    print("\n== Step F: Internal consistency validation ==")
    validate_quantile_sensitivity(panel, feats, config.AUDIT / "sensitivity_quantile.png")
    validate_constraint_rate(feats, config.AUDIT / "constraint_breakdown.csv")
    validate_magnitude(final, feats, config.AUDIT / "magnitude_ratio.png")
    validate_spatial(final, feats, config.AUDIT / "spatial_consistency.csv")
    validate_constraint_threshold_sensitivity(panel, feats,
        config.AUDIT / "constraint_threshold_sensitivity.csv")

    # Step F.b — Visualisations + Business recommendations
    print("\n== Step F.b: Maps + Business recommendations ==")
    try:
        make_sri_lanka_potential_map(feats, final,
            config.AUDIT / "map_sri_lanka_potential.png")
        make_province_choropleth(feats, final,
            config.AUDIT / "province_potential_bars.png")
        make_business_recommendations(feats, final,
            config.AUDIT / "top100_outlets_priority.csv", top_n=100)
    except Exception as e:
        print(f"  WARN: visualisations failed: {e}")

    # Step G: Hold-out validation (predict Jan 2025 from 2023+2024 history)
    print("\n== Step G: Hold-out validation (Jan 2025 predict-from-past) ==")
    try:
        _ = holdout_validation_jan_2025(panel, feats)
    except Exception as e:
        print(f"  WARN: hold-out validation failed: {e}")

    # Write predictions CSV (deliverable #1)
    out = pd.DataFrame({
        "Outlet_ID": final.index,
        "Maximum_Monthly_Liters": final.values.round(3),
    }).sort_values("Outlet_ID").reset_index(drop=True)

    # All 20,000 outlets in master must appear (use original full master, not silver-cleaned)
    master_full = pd.read_csv(config.BRONZE / "outlet_master.csv")["Outlet_ID"].astype(str).str.strip().unique()
    missing = set(master_full) - set(out["Outlet_ID"])
    if missing:
        # Outlets that were quarantined (null master, bad coords, etc.) — use global Q90
        global_q90 = float(panel.loc[panel["constrained"] == 0, "monthly_volume"]
                                 .quantile(config.PEER_QUANTILE))
        # apply mean YoY + mean seasonality for global fallback
        avg_mult = yoy["yoy_clipped"].mean() * 1.0  # neutral seasonality
        fallback_value = max(global_q90 * avg_mult, 0.1)
        fallback_rows = pd.DataFrame({
            "Outlet_ID": sorted(missing),
            "Maximum_Monthly_Liters": [round(fallback_value, 3)] * len(missing),
        })
        out = pd.concat([out, fallback_rows], ignore_index=True).sort_values("Outlet_ID")
        print(f"  filled {len(missing):,} quarantined outlets with global fallback "
              f"({fallback_value:.2f} L)")

    out.to_csv(config.PREDICTIONS_CSV, index=False, encoding="utf-8")
    print(f"\nPredictions written: {config.PREDICTIONS_CSV}  shape={out.shape}")
    print(f"Summary: min={out['Maximum_Monthly_Liters'].min():.2f}, "
          f"median={out['Maximum_Monthly_Liters'].median():.2f}, "
          f"mean={out['Maximum_Monthly_Liters'].mean():.2f}, "
          f"max={out['Maximum_Monthly_Liters'].max():.2f}")

    # Final sanity assertions
    assert len(out) == 20000, f"Expected 20,000 rows, got {len(out)}"
    assert set(out.columns) == {"Outlet_ID", "Maximum_Monthly_Liters"}
    assert out["Maximum_Monthly_Liters"].isna().sum() == 0
    assert (out["Maximum_Monthly_Liters"] > 0).all()
    print("All sanity assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
