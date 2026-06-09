"""Dashboard endpoints: budget, cooler ROI, dormancy, scorecard, territories."""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter

from services.data_loader import get_cache


router = APIRouter(prefix="/api", tags=["dashboards"])


def _records(df: pd.DataFrame) -> list[dict]:
    return df.replace({float("nan"): None}).to_dict(orient="records")


@router.get("/summary")
def summary():
    """Headline KPIs for the dashboard tile-row."""
    c = get_cache()
    feats = c.features
    preds = c.predictions
    budget = c.budget
    dormancy = c.dormancy
    roi100 = c.cooler_roi_top100

    n_outlets = int(len(feats))
    total_potential = float(preds["Maximum_Monthly_Liters"].sum()) if not preds.empty else 0.0
    median_potential = float(preds["Maximum_Monthly_Liters"].median()) if not preds.empty else 0.0
    total_budget = float(budget["Trade_Spend_LKR"].sum()) if not budget.empty else 0.0
    n_high_risk = int(((dormancy.get("risk_band", pd.Series()) == "high")
                        | (dormancy.get("risk_band", pd.Series()) == "critical")).sum()) if not dormancy.empty else 0
    n_top100_capex = float(len(roi100) * 50_000) if not roi100.empty else 0.0
    n_top100_margin = float(roi100["monthly_margin_uplift_LKR"].sum() * 24) if not roi100.empty else 0.0

    by_prov = (feats.groupby("Province")["Outlet_ID"].count().to_dict()
               if "Province" in feats.columns else {})

    return {
        "n_outlets": n_outlets,
        "total_predicted_jan2026_L": round(total_potential, 0),
        "median_predicted_jan2026_L": round(median_potential, 1),
        "budget_allocated_LKR": round(total_budget, 0),
        "outlets_high_or_critical_risk": n_high_risk,
        "cooler_top100_capex_LKR": round(n_top100_capex, 0),
        "cooler_top100_24mo_margin_LKR": round(n_top100_margin, 0),
        "outlets_by_province": by_prov,
    }


@router.get("/budget/distributors")
def budget_by_distributor():
    c = get_cache()
    return _records(c.budget_by_distributor)


@router.get("/budget/channels")
def budget_by_channel():
    c = get_cache()
    if c.budget_channels.empty:
        return {"rows": [], "totals": {}}
    df = c.budget_channels
    totals = {
        "Discount_LKR":      float(df["Discount_LKR"].sum()),
        "Merchandising_LKR": float(df["Merchandising_LKR"].sum()),
        "Promotional_LKR":   float(df["Promotional_LKR"].sum()),
        "Total_LKR":         float(df["Trade_Spend_LKR"].sum()),
    }
    return {"totals": totals, "rows": _records(df.head(500))}


@router.get("/budget/outlets")
def budget_outlets(limit: int = 200):
    c = get_cache()
    if c.budget.empty:
        return []
    df = c.budget.sort_values("Trade_Spend_LKR", ascending=False).head(limit)
    return _records(df)


@router.get("/cooler-roi/top100")
def cooler_roi_top100():
    c = get_cache()
    return _records(c.cooler_roi_top100)


@router.get("/cooler-roi/summary")
def cooler_roi_summary():
    c = get_cache()
    df = c.cooler_roi_full
    if df.empty:
        return {}
    return {
        "outlets_without_cooler":       int((df["Cooler_Count"] == 0).sum()),
        "material_cases":               int(df.get("is_material_case", pd.Series([0])).sum()),
        "payback_within_24mo":          int(df.get("payback_within_24mo", pd.Series([0])).sum()),
        "top100_total_capex_LKR":       float(len(c.cooler_roi_top100) * 50_000),
        "top100_24mo_margin_LKR":       float(c.cooler_roi_top100["monthly_margin_uplift_LKR"].sum() * 24)
                                          if not c.cooler_roi_top100.empty else 0.0,
        "top100_median_payback_months": float(c.cooler_roi_top100["payback_months"].median())
                                          if not c.cooler_roi_top100.empty else 0.0,
    }


@router.get("/dormancy/top")
def dormancy_top(limit: int = 200):
    c = get_cache()
    if c.dormancy_top.empty:
        return []
    return _records(c.dormancy_top.head(limit))


@router.get("/dormancy/bands")
def dormancy_bands():
    c = get_cache()
    if c.dormancy.empty:
        return {}
    counts = c.dormancy["risk_band"].value_counts().to_dict()
    return {b: int(counts.get(b, 0)) for b in ("low", "moderate", "high", "critical")}


@router.get("/scorecard")
def distributor_scorecard():
    c = get_cache()
    return _records(c.scorecard)


@router.get("/territories")
def territories():
    c = get_cache()
    return _records(c.territories)


@router.get("/forensics")
def forensics():
    c = get_cache()
    return _records(c.forensics)


@router.get("/shap/global")
def shap_global(limit: int = 30):
    c = get_cache()
    if c.shap_global.empty:
        return []
    return _records(c.shap_global.head(limit))


@router.get("/shop-map/outlets")
def shop_map_outlets():
    """All outlet locations annotated with their data-lake level.

    Returns three lists:
    - gold:     outlets that cleared all pipeline stages (outlet_features)
    - silver:   empty in this pipeline (silver == gold)
    - rejected: outlets dropped at the silver coordinate-DQ stage with failure reasons
    """
    c = get_cache()

    # Gold outlets — already have lat/lon in features
    gold_cols = ["Outlet_ID", "Latitude", "Longitude", "Outlet_Type", "Province"]
    gold_df = c.features[[col for col in gold_cols if col in c.features.columns]].copy()
    gold_records = (
        gold_df
        .rename(columns={"Outlet_ID": "outlet_id", "Latitude": "lat",
                         "Longitude": "lon", "Outlet_Type": "outlet_type",
                         "Province": "province"})
        .replace({float("nan"): None})
        .to_dict(orient="records")
    )

    # Rejected outlets — coordinate DQ failures not in gold.
    # rejected_coords already carries Latitude/Longitude from the evaluated dataset.
    rejected_records: list[dict] = []
    if not c.rejected_coords.empty:
        gold_ids = set(c.features["Outlet_ID"])
        not_gold = c.rejected_coords[~c.rejected_coords["Outlet_ID"].isin(gold_ids)]
        not_gold = not_gold.drop_duplicates("Outlet_ID")

        # Attach outlet type from bronze master
        rej = not_gold.copy()
        if not c.bronze_master.empty:
            rej = rej.merge(
                c.bronze_master[["Outlet_ID", "Outlet_Type"]],
                on="Outlet_ID", how="left"
            )

        keep = ["Outlet_ID", "Latitude", "Longitude", "Outlet_Type",
                "_rejection_reason", "_check_name"]
        rej = rej[[col for col in keep if col in rej.columns]]
        rejected_records = (
            rej
            .rename(columns={"Outlet_ID": "outlet_id", "Latitude": "lat",
                              "Longitude": "lon", "Outlet_Type": "outlet_type",
                              "_rejection_reason": "rejection_reason",
                              "_check_name": "check_name"})
            .replace({float("nan"): None})
            .to_dict(orient="records")
        )

    return {"gold": gold_records, "silver": [], "rejected": rejected_records}
