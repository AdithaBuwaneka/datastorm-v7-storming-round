"""Distributor scorecard.

Per-distributor benchmark across the dimensions a CPG operations team would
actually compare:

  Coverage     - share of master outlets that were active in the last 12 months
  Penetration  - average active months per outlet across the panel window
  Volume base  - total / median monthly volume per outlet
  Cooler density - average coolers per outlet
  Outlet mix   - share by Outlet_Type
  YoY growth   - Jan-2024 -> Jan-2025 geometric mean (already produced by gold)
  Constraint exposure - share of outlets flagged at-risk for dormancy
  Spatial demand - cohort mean of spatial_demand_score
  Predicted potential - sum / median Jan 2026 forecast
  Realisation gap - sum(predicted potential - recent observed)

A composite "operational health score" is z-scaled across the 10 distributors
so the scorecard can be sorted and reported.

Outputs:
    outputs/audit/distributor_scorecard.csv             - main table
    outputs/audit/distributor_scorecard_ranks.csv       - per-dimension ranks
    outputs/audit/distributor_outlet_mix.csv            - outlet-type shares
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config


SCORE_WEIGHTS = {
    "coverage_pct":              0.15,
    "penetration_active_months": 0.10,
    "median_volume_per_outlet":  0.15,
    "cooler_density":            0.10,
    "spatial_demand_avg":        0.10,
    "yoy_growth":                0.10,
    "median_predicted_jan2026":  0.15,
    "low_risk_share":            0.15,
}


def _zscore(s: pd.Series) -> pd.Series:
    sd = s.std()
    if sd == 0 or pd.isna(sd):
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / sd


def build_scorecard(panel: pd.DataFrame,
                    feats: pd.DataFrame,
                    predictions: pd.DataFrame,
                    yoy: pd.DataFrame,
                    dormancy: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Recent activity (last 12 months in panel)
    panel = panel.sort_values(["Outlet_ID", "Year", "Month"])
    last12 = (panel.groupby("Outlet_ID")
                  .tail(12)
                  .groupby("Outlet_ID")
                  .agg(recent_active_months=("monthly_volume",
                                              lambda v: int((v > 0).sum())),
                       recent_volume_sum=("monthly_volume", "sum"))
                  .reset_index())

    df = feats.merge(predictions, on="Outlet_ID", how="left")
    df = df.merge(last12, on="Outlet_ID", how="left")
    df = df.merge(dormancy[["Outlet_ID", "dormancy_risk_score", "risk_band"]],
                  on="Outlet_ID", how="left")
    df["recent_active_months"] = df["recent_active_months"].fillna(0)

    rows = []
    for dist_id, grp in df.groupby("Distributor_ID", sort=True):
        n_outlets = len(grp)
        n_active = int((grp["recent_active_months"] >= 1).sum())
        median_vol = float(grp["monthly_volume_mean"].median())
        cooler_density = float(grp["Cooler_Count"].mean())
        spatial = float(grp.get("spatial_demand_score", pd.Series([np.nan])).mean())
        median_pred = float(grp["Maximum_Monthly_Liters"].median())
        sum_pred = float(grp["Maximum_Monthly_Liters"].sum())
        sum_observed = float(grp["monthly_volume_mean"].sum())
        realisation_gap = max(0.0, sum_pred - sum_observed)
        low_risk_share = float((grp["risk_band"] == "low").mean()) if "risk_band" in grp.columns else np.nan
        critical_risk_share = float((grp["risk_band"] == "critical").mean()) if "risk_band" in grp.columns else np.nan
        penetration = float(grp["active_months"].mean())

        rows.append({
            "Distributor_ID": dist_id,
            "n_outlets": n_outlets,
            "n_active_last12": n_active,
            "coverage_pct": round(100.0 * n_active / n_outlets, 2),
            "penetration_active_months": round(penetration, 2),
            "median_volume_per_outlet": round(median_vol, 2),
            "cooler_density": round(cooler_density, 3),
            "spatial_demand_avg": round(spatial, 4),
            "median_predicted_jan2026": round(median_pred, 2),
            "total_predicted_jan2026": round(sum_pred, 0),
            "realisation_gap_L": round(realisation_gap, 0),
            "low_risk_share": round(low_risk_share, 3),
            "critical_risk_share": round(critical_risk_share, 3),
        })

    score = pd.DataFrame(rows)

    yoy_lookup = yoy.set_index("Distributor_ID")["yoy_clipped"].to_dict() if not yoy.empty else {}
    score["yoy_growth"] = score["Distributor_ID"].map(yoy_lookup).fillna(1.0).round(4)

    # Composite operational health (z-scored, weighted)
    z = pd.DataFrame({"Distributor_ID": score["Distributor_ID"]})
    for col, w in SCORE_WEIGHTS.items():
        if col in score.columns:
            z[col] = _zscore(score[col]) * w
    score["health_z"] = z.drop(columns=["Distributor_ID"]).sum(axis=1).round(3)
    score = score.sort_values("health_z", ascending=False).reset_index(drop=True)
    score.insert(0, "health_rank", range(1, len(score) + 1))

    # Per-dimension rank table (lower number = better)
    dims = ["coverage_pct", "penetration_active_months", "median_volume_per_outlet",
            "cooler_density", "spatial_demand_avg", "median_predicted_jan2026",
            "yoy_growth", "low_risk_share"]
    rank_rows = []
    for d in dims:
        if d in score.columns:
            r = score[d].rank(ascending=False, method="min").astype(int)
            rank_rows.append(pd.Series(r.values, index=score["Distributor_ID"], name=d))
    ranks = pd.concat(rank_rows, axis=1).reset_index()

    return score, ranks


def outlet_mix_by_distributor(feats: pd.DataFrame) -> pd.DataFrame:
    mix = (feats.groupby(["Distributor_ID", "Outlet_Type"]).size()
           .reset_index(name="n")
           .pivot(index="Distributor_ID", columns="Outlet_Type", values="n")
           .fillna(0).astype(int))
    mix["total"] = mix.sum(axis=1)
    for col in mix.columns:
        if col != "total":
            mix[f"{col}_pct"] = (100.0 * mix[col] / mix["total"]).round(2)
    return mix.reset_index()


def main() -> None:
    print("\n" + "=" * 70)
    print("Distributor scorecard")
    print("=" * 70)

    panel = pd.read_parquet(config.GOLD / "outlet_month_panel.parquet")
    feats = pd.read_parquet(config.GOLD / "outlet_features.parquet")
    predictions = pd.read_csv(config.OUTPUTS / f"{config.TEAM_NAME}_predictions.csv")
    dormancy = pd.read_parquet(config.GOLD / "dormancy_risk.parquet")
    yoy_path = config.AUDIT / "yoy_growth_factors.csv"
    yoy = pd.read_csv(yoy_path) if yoy_path.exists() else pd.DataFrame()

    score, ranks = build_scorecard(panel, feats, predictions, yoy, dormancy)

    score_path = config.AUDIT / "distributor_scorecard.csv"
    score.to_csv(score_path, index=False)
    print(f"  -> {score_path}")
    print(score.to_string(index=False))

    rank_path = config.AUDIT / "distributor_scorecard_ranks.csv"
    ranks.to_csv(rank_path, index=False)
    print(f"\n  -> {rank_path}")

    mix = outlet_mix_by_distributor(feats)
    mix_path = config.AUDIT / "distributor_outlet_mix.csv"
    mix.to_csv(mix_path, index=False)
    print(f"  -> {mix_path}  shape={mix.shape}")

    print("\nDistributor scorecard: OK")


if __name__ == "__main__":
    main()
