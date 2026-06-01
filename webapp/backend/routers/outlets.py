"""Outlet listing + drill-down endpoints."""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ..services.data_loader import get_cache


router = APIRouter(prefix="/api/outlets", tags=["outlets"])


def _to_records(df: pd.DataFrame) -> list[dict]:
    """JSON-safe dict records (NaN -> None)."""
    return df.replace({float("nan"): None}).to_dict(orient="records")


@router.get("/")
def list_outlets(
    province: Optional[str] = Query(None, description="Filter by Province"),
    distributor: Optional[str] = Query(None, description="Filter by Distributor_ID"),
    outlet_type: Optional[str] = Query(None, description="Filter by Outlet_Type"),
    outlet_size: Optional[str] = Query(None, description="Filter by Outlet_Size"),
    risk_band: Optional[str] = Query(None, description="Filter by dormancy risk band"),
    search: Optional[str] = Query(None, description="Substring match on Outlet_ID"),
    sort_by: str = Query("Maximum_Monthly_Liters", description="Sortable column"),
    descending: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    cache = get_cache()
    df = cache.outlets_table.copy()
    if df.empty:
        raise HTTPException(503, "Outlet data not yet loaded; run the pipeline first.")

    if province:
        df = df[df["Province"] == province]
    if distributor:
        df = df[df["Distributor_ID"] == distributor]
    if outlet_type:
        df = df[df["Outlet_Type"] == outlet_type]
    if outlet_size:
        df = df[df["Outlet_Size"] == outlet_size]
    if risk_band:
        df = df[df["risk_band"] == risk_band]
    if search:
        df = df[df["Outlet_ID"].astype(str).str.contains(search, case=False, na=False)]

    if sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=not descending, kind="mergesort")

    total = len(df)
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = df.iloc[start:end]

    return {
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "n_pages": max(1, math.ceil(total / page_size)),
        "rows": _to_records(page_rows),
    }


@router.get("/filters")
def list_filters():
    cache = get_cache()
    df = cache.outlets_table
    if df.empty:
        return {}
    def _vals(col: str) -> list:
        if col not in df.columns:
            return []
        return sorted(v for v in df[col].dropna().unique().tolist() if v != "")
    return {
        "provinces":    _vals("Province"),
        "distributors": _vals("Distributor_ID"),
        "outlet_types": _vals("Outlet_Type"),
        "outlet_sizes": _vals("Outlet_Size"),
        "risk_bands":   ["low", "moderate", "high", "critical"],
    }


def _outlet_row(outlet_id: str) -> Optional[pd.Series]:
    cache = get_cache()
    df = cache.outlets_table
    if df.empty:
        return None
    match = df[df["Outlet_ID"] == outlet_id]
    if match.empty:
        return None
    return match.iloc[0]


@router.get("/{outlet_id}")
def outlet_detail(outlet_id: str):
    cache = get_cache()
    row = _outlet_row(outlet_id)
    if row is None:
        raise HTTPException(404, f"Outlet {outlet_id} not found")

    # Top SHAP drivers
    shap_df = cache.shap_drivers
    drivers: list[dict] = []
    if not shap_df.empty and "Outlet_ID" in shap_df.columns:
        match = shap_df[shap_df["Outlet_ID"] == outlet_id]
        if not match.empty:
            r = match.iloc[0].to_dict()
            for rank in range(1, 6):
                f = r.get(f"pos_{rank}_feature")
                s = r.get(f"pos_{rank}_shap")
                if f:
                    drivers.append({"direction": "positive", "feature": f,
                                    "shap": float(s) if pd.notna(s) else 0.0})
            for rank in range(1, 6):
                f = r.get(f"neg_{rank}_feature")
                s = r.get(f"neg_{rank}_shap")
                if f:
                    drivers.append({"direction": "negative", "feature": f,
                                    "shap": float(s) if pd.notna(s) else 0.0})

    # Counterfactual deltas
    cf_df = cache.counterfactuals
    cf_row = {}
    if not cf_df.empty:
        m = cf_df[cf_df["Outlet_ID"] == outlet_id]
        if not m.empty:
            cf_row = m.iloc[0].to_dict()
            cf_row.pop("Outlet_ID", None)
            cf_row = {k: (None if pd.isna(v) else float(v)) for k, v in cf_row.items()}

    # Outlet action cards (top-3 recommended actions)
    actions_df = cache.outlet_actions
    actions: list[dict] = []
    if not actions_df.empty and "Outlet_ID" in actions_df.columns:
        m = actions_df[actions_df["Outlet_ID"] == outlet_id].sort_values("rank")
        for _, a in m.iterrows():
            actions.append({k: (None if pd.isna(v) else v)
                            for k, v in a.to_dict().items()})

    # Cooler ROI snapshot if eligible
    roi_df = cache.cooler_roi_full
    roi_row = {}
    if not roi_df.empty and "Outlet_ID" in roi_df.columns:
        m = roi_df[roi_df["Outlet_ID"] == outlet_id]
        if not m.empty:
            r = m.iloc[0].to_dict()
            roi_row = {k: (None if pd.isna(v) else v) for k, v in r.items()}

    return {
        "outlet":            {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()},
        "top_drivers":       drivers,
        "counterfactual":    cf_row,
        "recommended_actions": actions,
        "cooler_roi":        roi_row,
    }
