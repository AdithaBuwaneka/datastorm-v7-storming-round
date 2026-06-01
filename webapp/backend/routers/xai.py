"""XAI narrative endpoint — wraps Gemini around the per-outlet factual payload."""
from __future__ import annotations

from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException

from services.data_loader import get_cache
from services.gemini_xai import generate_narrative


router = APIRouter(prefix="/api/xai", tags=["xai"])


def _payload_for_outlet(outlet_id: str) -> Optional[dict]:
    cache = get_cache()
    df = cache.outlets_table
    if df.empty:
        return None
    row = df[df["Outlet_ID"] == outlet_id]
    if row.empty:
        return None
    r = row.iloc[0]

    summary = {
        "Province":           r.get("Province"),
        "Distributor":        r.get("Distributor_ID"),
        "Outlet type":        r.get("Outlet_Type"),
        "Outlet size":        r.get("Outlet_Size"),
        "Coolers today":      int(r.get("Cooler_Count", 0) or 0),
        "Predicted Jan 2026 potential (L)": round(float(r.get("Maximum_Monthly_Liters", 0) or 0), 1),
        "Recent monthly average (L)":       round(float(r.get("monthly_volume_mean", 0) or 0), 1),
        "Active months":      int(r.get("active_months", 0) or 0),
        "Local competitors within 1 km":    int(r.get("competitors_1km", 0) or 0),
        "Market concentration (HHI)":       round(float(r.get("hhi_1500m", 0) or 0), 1),
        "Replenishment friction (0-1)":     round(float(r.get("replenishment_friction", 0) or 0), 3),
        "Dormancy risk band":               r.get("risk_band"),
    }

    drivers: list[dict] = []
    shap_df = cache.shap_drivers
    if not shap_df.empty:
        m = shap_df[shap_df["Outlet_ID"] == outlet_id]
        if not m.empty:
            d = m.iloc[0].to_dict()
            for rank in range(1, 4):
                f = d.get(f"pos_{rank}_feature")
                if f:
                    drivers.append({"feature": f, "shap": float(d.get(f"pos_{rank}_shap") or 0.0)})
            for rank in range(1, 4):
                f = d.get(f"neg_{rank}_feature")
                if f:
                    drivers.append({"feature": f, "shap": float(d.get(f"neg_{rank}_shap") or 0.0)})

    cf = cache.counterfactuals
    cf_payload = {}
    if not cf.empty:
        m = cf[cf["Outlet_ID"] == outlet_id]
        if not m.empty:
            c = m.iloc[0]
            cf_payload = {
                "If we added a cooler":         f"{float(c.get('delta_add_cooler', 0) or 0):.1f} L/mo",
                "If competition were removed":  f"{float(c.get('delta_zero_competition', 0) or 0):.1f} L/mo",
            }

    actions: list[dict] = []
    act_df = cache.outlet_actions
    if not act_df.empty:
        m = act_df[act_df["Outlet_ID"] == outlet_id].sort_values("rank")
        for _, a in m.iterrows():
            actions.append({
                "action": a.get("action"),
                "uplift_L": float(a.get("predicted_uplift_L_per_month", 0) or 0),
                "rationale": a.get("rationale"),
            })

    extras: dict = {}
    if "Trade_Spend_LKR" in r.index and pd.notna(r.get("Trade_Spend_LKR")):
        extras["LKR allocated for Jan 2026 (Western only)"] = round(float(r.get("Trade_Spend_LKR")), 0)

    return {
        "outlet_id": outlet_id,
        "summary": summary,
        "top_drivers": drivers,
        "counterfactual": cf_payload,
        "recommended_actions": actions,
        "extras": extras,
    }


@router.post("/explain/{outlet_id}")
def explain(outlet_id: str):
    payload = _payload_for_outlet(outlet_id)
    if payload is None:
        raise HTTPException(404, f"Outlet {outlet_id} not found")
    try:
        narrative = generate_narrative(payload)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Gemini call failed: {exc}")
    return {"outlet_id": outlet_id, "payload": payload, "narrative": narrative}
