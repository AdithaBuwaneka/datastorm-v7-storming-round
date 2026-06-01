"""Per-outlet feature attribution and counterfactual deltas.

We train an XGBoost surrogate of the ensemble prediction and use SHAP to
produce, per outlet:
  - signed contribution of each feature to that outlet's predicted potential
  - top-K positive and top-K negative drivers
  - what-if predictions for two practical interventions (add a cooler;
    remove competitive drag)

These artifacts feed downstream explanation rendering (web UI cards and
narrative generation).

Outputs:
  data/gold/shap_values.parquet
  outputs/audit/shap_global_importance.csv
  outputs/audit/shap_top_drivers_per_outlet.csv
  data/gold/counterfactuals.parquet
  outputs/audit/xai_surrogate_fidelity.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import xgboost as xgb
import shap

from scipy.stats import spearmanr

from src import config


RANDOM_SEED = 42

# Feature blocks (must exist in gold/outlet_features.parquet).
# We include numeric features only; categoricals get one-hot encoded inline.
NUMERIC_FEATURES = [
    # Volume statistics
    "monthly_volume_mean", "monthly_volume_median", "monthly_volume_std",
    "monthly_volume_q90", "monthly_volume_q95",
    # Activity
    "active_months", "zero_months_count", "zero_months_share",
    "max_consecutive_zeros", "monthly_cv",
    # Master attributes (numeric)
    "Cooler_Count", "outlet_size_score", "outlet_type_multiplier", "has_no_cooler",
    # SKU mix
    "premium_share", "mid_share", "mass_share", "super_premium_share",
    "avg_price_per_liter", "sku_diversity",
    # Competition
    "competitors_500m", "competitors_1km", "competitors_2km",
    "same_type_competitors_500m", "same_type_competitors_1km",
    "competitor_density_norm",
    "is_isolated_market", "is_dense_market",
    # Spatial demand decay scores (normalised)
    "footfall_score_norm", "school_score_norm", "tourist_score_norm",
    "health_score_norm", "worship_score_norm", "food_pairing_score_norm",
    "leisure_rec_score_norm", "population_score_norm",
    "competitor_poi_score_norm",
    "spatial_demand_score", "poi_diversity_score",
    # Climate
    "climate_jan_temp_c", "climate_jan_humid_pct",
    # Geography
    "Latitude", "Longitude",
    # Historical Jan signal
    "jan_mean", "jan_volume_q90",
]

CATEGORICAL_FEATURES = ["Outlet_Type", "Outlet_Size", "Province", "Distributor_ID"]


def _available(df: pd.DataFrame, cols: list[str]) -> list[str]:
    return [c for c in cols if c in df.columns]


def build_design_matrix(feats: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Return (X, feature_names) — numeric features + one-hot categoricals."""
    num_cols = _available(feats, NUMERIC_FEATURES)
    cat_cols = _available(feats, CATEGORICAL_FEATURES)

    X_num = feats[num_cols].fillna(0.0).astype(float).copy()
    if cat_cols:
        X_cat = pd.get_dummies(feats[cat_cols].astype(str), prefix=cat_cols, dtype=float)
        X = pd.concat([X_num, X_cat], axis=1)
    else:
        X = X_num

    return X, list(X.columns)


def train_surrogate(X: pd.DataFrame, y: pd.Series) -> xgb.XGBRegressor:
    """Train an XGBoost regressor to surrogate our prediction.

    Monotonic constraints enforce defensible business assumptions:
      - Cooler_Count: +1 (more coolers can never lower predicted potential)
      - competitor_density_norm: -1 (more competition can never raise it)
      - has_no_cooler: -1 (lacking a cooler can never raise it)
      - active_months: +1 (more activity history can never lower it)
    Other features are unconstrained.
    """
    monotone = []
    for col in X.columns:
        if col == "Cooler_Count" or col == "active_months":
            monotone.append(1)
        elif col == "competitor_density_norm" or col == "has_no_cooler":
            monotone.append(-1)
        else:
            monotone.append(0)

    model = xgb.XGBRegressor(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=1.0,
        tree_method="hist",
        random_state=RANDOM_SEED,
        n_jobs=-1,
        monotone_constraints="(" + ",".join(str(m) for m in monotone) + ")",
    )
    model.fit(X, y, verbose=False)
    return model


def compute_shap(model: xgb.XGBRegressor, X: pd.DataFrame) -> np.ndarray:
    """Exact SHAP values for tree-based models (TreeExplainer)."""
    explainer = shap.TreeExplainer(model)
    return explainer.shap_values(X)


def per_outlet_top_drivers(
    shap_values: np.ndarray,
    feature_names: list[str],
    outlet_ids: pd.Series,
    k: int = 5,
) -> pd.DataFrame:
    """For each outlet, return the k strongest positive and k strongest
    negative drivers (by signed SHAP value).
    """
    rows = []
    for i, oid in enumerate(outlet_ids):
        contribs = shap_values[i]
        order = np.argsort(contribs)
        bottom_k = order[:k]            # most negative
        top_k = order[-k:][::-1]        # most positive (descending)
        row = {"Outlet_ID": oid}
        for rank, j in enumerate(top_k, 1):
            row[f"pos_{rank}_feature"] = feature_names[j]
            row[f"pos_{rank}_shap"]    = float(contribs[j])
        for rank, j in enumerate(bottom_k, 1):
            row[f"neg_{rank}_feature"] = feature_names[j]
            row[f"neg_{rank}_shap"]    = float(contribs[j])
        rows.append(row)
    return pd.DataFrame(rows)


def counterfactual_predictions(
    model: xgb.XGBRegressor,
    X: pd.DataFrame,
    feats: pd.DataFrame,
    feature_names: list[str],
) -> pd.DataFrame:
    """Compute two practical counterfactuals per outlet:

      cf_add_cooler:  what would prediction be if Cooler_Count += 1
                      (clipped to <= 6); also turn off has_no_cooler
      cf_zero_competition:  what if competitor_density_norm = 0
                            (isolated market scenario)
    """
    base = model.predict(X)

    # Intervention 1: add a cooler
    X_cf1 = X.copy()
    if "Cooler_Count" in X_cf1.columns:
        X_cf1["Cooler_Count"] = (X_cf1["Cooler_Count"] + 1).clip(upper=6)
    if "has_no_cooler" in X_cf1.columns:
        X_cf1["has_no_cooler"] = 0.0
    cf_add_cooler = model.predict(X_cf1)

    # Intervention 2: remove competition
    X_cf2 = X.copy()
    if "competitor_density_norm" in X_cf2.columns:
        X_cf2["competitor_density_norm"] = 0.0
    if "is_isolated_market" in X_cf2.columns:
        X_cf2["is_isolated_market"] = 1.0
    if "is_dense_market" in X_cf2.columns:
        X_cf2["is_dense_market"] = 0.0
    cf_zero_comp = model.predict(X_cf2)

    out = pd.DataFrame({
        "Outlet_ID": feats["Outlet_ID"].values,
        "base_pred":       np.round(base, 3),
        "cf_add_cooler":   np.round(cf_add_cooler, 3),
        "cf_zero_competition": np.round(cf_zero_comp, 3),
        "delta_add_cooler":  np.round(cf_add_cooler - base, 3),
        "delta_zero_competition": np.round(cf_zero_comp - base, 3),
    })
    return out


def main() -> None:
    print("\n" + "=" * 70)
    print("XAI attribution + counterfactuals")
    print("=" * 70)

    feats = pd.read_parquet(config.GOLD / "outlet_features.parquet")
    preds = pd.read_csv(config.OUTPUTS / f"{config.TEAM_NAME}_predictions.csv")

    df = feats.merge(preds, on="Outlet_ID", how="inner")
    print(f"  Joined: {len(df):,} outlets")

    X, feature_names = build_design_matrix(df)
    y = df["Maximum_Monthly_Liters"].astype(float).values
    print(f"  Design matrix: {X.shape[0]:,} rows x {X.shape[1]:,} features")

    print("  Training XGBoost surrogate ...")
    model = train_surrogate(X, pd.Series(y))
    surrogate_pred = model.predict(X)

    # Fidelity: surrogate vs original prediction
    spearman, _ = spearmanr(y, surrogate_pred)
    r2 = 1.0 - ((y - surrogate_pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    mape = float(np.median(np.abs(surrogate_pred - y) / np.maximum(y, 1e-6)))
    print(f"  Surrogate fidelity: Spearman={spearman:.4f}, R^2={r2:.4f}, "
          f"median |%err|={mape*100:.2f}%")

    fidelity = pd.DataFrame([{
        "surrogate_spearman_vs_ensemble": round(float(spearman), 4),
        "surrogate_r2_vs_ensemble":       round(float(r2), 4),
        "surrogate_median_pct_err":       round(float(mape * 100), 2),
        "n_features": X.shape[1],
        "n_outlets": X.shape[0],
    }])
    fidelity.to_csv(config.AUDIT / "xai_surrogate_fidelity.csv", index=False)

    print("  Computing SHAP values (TreeExplainer; exact)...")
    shap_values = compute_shap(model, X)

    # Persist per-outlet SHAP matrix as parquet (long-form keys for webapp lookup)
    shap_df = pd.DataFrame(shap_values, columns=feature_names)
    shap_df.insert(0, "Outlet_ID", df["Outlet_ID"].values)
    shap_path = config.GOLD / "shap_values.parquet"
    shap_df.to_parquet(shap_path, index=False)
    print(f"  -> {shap_path}  shape={shap_df.shape}")

    # Global importance
    global_imp = (
        pd.DataFrame({
            "feature": feature_names,
            "mean_abs_shap": np.abs(shap_values).mean(axis=0),
        })
        .sort_values("mean_abs_shap", ascending=False)
        .reset_index(drop=True)
    )
    global_imp_path = config.AUDIT / "shap_global_importance.csv"
    global_imp.to_csv(global_imp_path, index=False)
    print(f"  -> {global_imp_path}  top 10:")
    print(global_imp.head(10).to_string(index=False))

    # Top drivers per outlet
    print("\n  Extracting top-5 +/- drivers per outlet ...")
    drivers = per_outlet_top_drivers(shap_values, feature_names, df["Outlet_ID"], k=5)
    drivers_path = config.AUDIT / "shap_top_drivers_per_outlet.csv"
    drivers.to_csv(drivers_path, index=False)
    print(f"  -> {drivers_path}  shape={drivers.shape}")

    # Counterfactuals
    print("\n  Computing counterfactual deltas (add cooler, zero competition)...")
    cf = counterfactual_predictions(model, X, df, feature_names)
    cf_path = config.GOLD / "counterfactuals.parquet"
    cf.to_parquet(cf_path, index=False)
    print(f"  -> {cf_path}  shape={cf.shape}")
    print(f"  Median delta_add_cooler:        {cf['delta_add_cooler'].median():.1f} L")
    print(f"  Median delta_zero_competition:  {cf['delta_zero_competition'].median():.1f} L")
    print(f"  Mean delta_add_cooler:          {cf['delta_add_cooler'].mean():.1f} L")
    print(f"  Outlets w/ cooler-add uplift > 0: "
          f"{int((cf['delta_add_cooler'] > 0).sum()):,} / {len(cf):,}")

    print("\nXAI attribution: OK")


if __name__ == "__main__":
    main()
