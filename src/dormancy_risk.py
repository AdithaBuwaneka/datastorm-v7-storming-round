"""Outlet dormancy-risk early warning.

Background: forensics flagged 2,730 outlets that went dormant for >=6
consecutive months in the historical panel and later resumed (the
"dead-then-resurrected" pattern). These outlets give us a labelled training
signal for "outlets that lapse and then come back" — the population a sales
team would want to call on before they lapse again.

Method:
  1. Re-derive the binary label per outlet from the gold panel:
       dormancy_event = 1  if outlet had >=6 consecutive zero months
                            AND then had at least one positive month after
  2. Train an XGBoost classifier on outlet-level features that are *not*
     direct functions of the label (we exclude max_consecutive_zeros and
     zero_months_share to avoid trivial leakage).
  3. Score every outlet to produce a 0-1 dormancy risk.
  4. Persist top-N at-risk outlets per distributor for sales-rep intervention.

Outputs:
    data/gold/dormancy_risk.parquet           - per-outlet risk score
    outputs/audit/dormancy_top200_at_risk.csv - prioritised early-warning list
    outputs/audit/dormancy_model_fit.csv      - AUC + calibration of the model
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import roc_auc_score, brier_score_loss
import xgboost as xgb

from src import config


RANDOM_SEED = 42
DORMANCY_THRESHOLD_MONTHS = 6
RISK_BANDS = [("low", 0.25), ("moderate", 0.50), ("high", 0.75), ("critical", 1.01)]


def derive_dormancy_label(panel: pd.DataFrame) -> pd.DataFrame:
    """Return DataFrame with Outlet_ID + dormancy_event (0/1).

    Definition: the outlet had >=6 consecutive zero-volume months and then
    had at least one positive month after the streak.
    """
    p = panel.sort_values(["Outlet_ID", "Year", "Month"]).copy()
    p["is_zero"] = (p["monthly_volume"] == 0).astype(int)

    out_rows = []
    for outlet_id, grp in p.groupby("Outlet_ID", sort=False):
        zeros = grp["is_zero"].values
        n = len(zeros)
        had_event = False
        # Walk through and look for a >=6 zero run followed by any non-zero
        run = 0
        run_max = 0
        for i, z in enumerate(zeros):
            if z == 1:
                run += 1
                run_max = max(run_max, run)
            else:
                if run >= DORMANCY_THRESHOLD_MONTHS:
                    had_event = True
                    break
                run = 0
        out_rows.append({"Outlet_ID": outlet_id, "dormancy_event": int(had_event)})

    return pd.DataFrame(out_rows)


# Feature whitelist — exclude direct functions of the label to avoid leakage.
SAFE_FEATURE_BLOCKS = [
    # Master attributes
    "Cooler_Count", "outlet_size_score", "outlet_type_multiplier", "has_no_cooler",
    # Aggregate volume statistics (mean / std / quantiles)
    "monthly_volume_mean", "monthly_volume_median", "monthly_volume_std",
    "monthly_volume_q90", "monthly_volume_q95",
    "monthly_revenue_mean", "monthly_revenue_median",
    "monthly_cv",
    # SKU mix
    "premium_share", "mid_share", "mass_share", "super_premium_share",
    "avg_price_per_liter", "sku_diversity",
    # Spatial decay
    "footfall_score_norm", "school_score_norm", "tourist_score_norm",
    "health_score_norm", "worship_score_norm", "food_pairing_score_norm",
    "leisure_rec_score_norm", "population_score_norm",
    "competitor_poi_score_norm", "spatial_demand_score", "poi_diversity_score",
    # Competition / market structure
    "competitors_500m", "competitors_1km", "competitors_2km",
    "same_type_competitors_500m", "same_type_competitors_1km",
    "competitor_density_norm", "type_weighted_pressure",
    "hhi_1500m", "territory_radius_m",
    # Climate
    "climate_jan_temp_c", "climate_jan_humid_pct",
    # Geography
    "Latitude", "Longitude",
]
CATEGORICAL = ["Outlet_Type", "Outlet_Size", "Province"]


def _build_X(feats: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    num = [c for c in SAFE_FEATURE_BLOCKS if c in feats.columns]
    cat = [c for c in CATEGORICAL if c in feats.columns]

    X_num = feats[num].fillna(0.0).astype(float)
    if cat:
        X_cat = pd.get_dummies(feats[cat].astype(str), prefix=cat, dtype=float)
        X = pd.concat([X_num, X_cat], axis=1)
    else:
        X = X_num
    return X, list(X.columns)


def risk_band(score: float) -> str:
    for label, upper in RISK_BANDS:
        if score < upper:
            return label
    return "critical"


def fit_and_score(feats: pd.DataFrame,
                  labels: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = feats.merge(labels, on="Outlet_ID", how="inner")
    print(f"  Outlets joined: {len(df):,}")
    print(f"  Positive (dormancy_event=1): "
          f"{int(df['dormancy_event'].sum()):,} "
          f"({df['dormancy_event'].mean()*100:.2f}%)")

    X, cols = _build_X(df)
    y = df["dormancy_event"].astype(int).values

    pos = int(y.sum())
    neg = int((1 - y).sum())
    scale_pos = neg / max(pos, 1)

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        scale_pos_weight=scale_pos,
        random_state=RANDOM_SEED,
        eval_metric="auc",
        tree_method="hist",
        n_jobs=-1,
    )

    cv = StratifiedKFold(5, shuffle=True, random_state=RANDOM_SEED)
    cv_aucs = cross_val_score(model, X, y, cv=cv, scoring="roc_auc", n_jobs=-1)
    print(f"  5-fold CV AUC: mean={cv_aucs.mean():.4f}  std={cv_aucs.std():.4f}")

    model.fit(X, y)
    proba = model.predict_proba(X)[:, 1]
    in_sample_auc = roc_auc_score(y, proba)
    brier = brier_score_loss(y, proba)
    print(f"  In-sample AUC: {in_sample_auc:.4f}, Brier: {brier:.4f}")

    out = pd.DataFrame({
        "Outlet_ID": df["Outlet_ID"].values,
        "dormancy_event_historical": y,
        "dormancy_risk_score": np.round(proba, 4),
        "risk_band": [risk_band(p) for p in proba],
    })

    metrics = {
        "cv_auc_mean": float(cv_aucs.mean()),
        "cv_auc_std": float(cv_aucs.std()),
        "in_sample_auc": float(in_sample_auc),
        "brier_score": float(brier),
        "n_outlets": int(len(df)),
        "n_positive_historical": int(pos),
        "feature_count": int(X.shape[1]),
    }
    return out, metrics


def write_outputs(scored: pd.DataFrame, metrics: dict,
                  feats: pd.DataFrame) -> None:
    config.GOLD.mkdir(parents=True, exist_ok=True)
    config.AUDIT.mkdir(parents=True, exist_ok=True)

    parq = config.GOLD / "dormancy_risk.parquet"
    scored.to_parquet(parq, index=False)
    print(f"  -> {parq}  shape={scored.shape}")

    metrics_df = pd.DataFrame([metrics])
    metrics_path = config.AUDIT / "dormancy_model_fit.csv"
    metrics_df.to_csv(metrics_path, index=False)
    print(f"  -> {metrics_path}")

    # At-risk shortlist: currently active outlets with the highest risk scores.
    # Active = has at least one positive month recently.
    joined = scored.merge(
        feats[["Outlet_ID", "Distributor_ID", "Province", "Outlet_Type",
               "Outlet_Size", "monthly_volume_mean", "Cooler_Count",
               "active_months"]],
        on="Outlet_ID", how="left",
    )
    # Drop already-dormant outlets so the list is actionable
    currently_active = joined[joined["active_months"] >= 6]
    top200 = (currently_active
              .sort_values("dormancy_risk_score", ascending=False)
              .head(200))
    at_risk_path = config.AUDIT / "dormancy_top200_at_risk.csv"
    top200.to_csv(at_risk_path, index=False)
    print(f"  -> {at_risk_path}  shape={top200.shape}")

    band_dist = scored["risk_band"].value_counts().reindex(
        ["low", "moderate", "high", "critical"]).fillna(0).astype(int)
    print(f"  Risk-band distribution: {band_dist.to_dict()}")


def main() -> None:
    print("\n" + "=" * 70)
    print("Dormancy-risk early warning (XGBoost classifier)")
    print("=" * 70)

    panel = pd.read_parquet(config.GOLD / "outlet_month_panel.parquet")
    feats = pd.read_parquet(config.GOLD / "outlet_features.parquet")

    print(f"  Deriving labels from panel ({len(panel):,} rows)...")
    labels = derive_dormancy_label(panel)
    pos = int(labels["dormancy_event"].sum())
    print(f"  Positive labels (>= {DORMANCY_THRESHOLD_MONTHS}-month run then resumed): "
          f"{pos:,} of {len(labels):,}")

    scored, metrics = fit_and_score(feats, labels)
    write_outputs(scored, metrics, feats)
    print("\nDormancy risk: OK")


if __name__ == "__main__":
    main()
