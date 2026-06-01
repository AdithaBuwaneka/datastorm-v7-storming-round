"""Single-process cache for the gold / audit artifacts the API serves.

The pipeline emits parquet + CSV files under data/gold and outputs/audit.
This module loads them once at process startup and exposes typed accessors.
The FastAPI app holds the cache as application state so endpoints share
the same in-memory frames.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd


def _repo_root() -> Path:
    """Locate the repository root from REPO_ROOT env var or by walking up."""
    env_root = os.environ.get("REPO_ROOT")
    if env_root:
        return Path(env_root).resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "data" / "gold").is_dir():
            return parent
    raise RuntimeError("Could not locate repo root containing data/gold/")


@dataclass
class DataCache:
    """In-memory snapshot of all artifacts the API needs."""
    repo_root: Path
    features: pd.DataFrame = field(default_factory=pd.DataFrame)
    predictions: pd.DataFrame = field(default_factory=pd.DataFrame)
    counterfactuals: pd.DataFrame = field(default_factory=pd.DataFrame)
    shap_drivers: pd.DataFrame = field(default_factory=pd.DataFrame)
    shap_global: pd.DataFrame = field(default_factory=pd.DataFrame)
    budget: pd.DataFrame = field(default_factory=pd.DataFrame)
    budget_channels: pd.DataFrame = field(default_factory=pd.DataFrame)
    budget_by_distributor: pd.DataFrame = field(default_factory=pd.DataFrame)
    cooler_roi_full: pd.DataFrame = field(default_factory=pd.DataFrame)
    cooler_roi_top100: pd.DataFrame = field(default_factory=pd.DataFrame)
    dormancy: pd.DataFrame = field(default_factory=pd.DataFrame)
    dormancy_top: pd.DataFrame = field(default_factory=pd.DataFrame)
    scorecard: pd.DataFrame = field(default_factory=pd.DataFrame)
    territories: pd.DataFrame = field(default_factory=pd.DataFrame)
    cluster_membership: pd.DataFrame = field(default_factory=pd.DataFrame)
    outlet_actions: pd.DataFrame = field(default_factory=pd.DataFrame)
    forensics: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def outlets_table(self) -> pd.DataFrame:
        """Returns the canonical outlet table the listing pages render."""
        if self._outlets_table is None:
            self._outlets_table = self._build_outlets_table()
        return self._outlets_table

    _outlets_table: Optional[pd.DataFrame] = None

    def _build_outlets_table(self) -> pd.DataFrame:
        cols = [
            "Outlet_ID", "Outlet_Type", "Outlet_Size", "Distributor_ID", "Province",
            "Cooler_Count", "Latitude", "Longitude",
            "active_months", "monthly_volume_mean", "monthly_volume_q90",
            "competitors_1km", "hhi_1500m", "spatial_demand_score",
            "replenishment_friction",
        ]
        df = self.features[[c for c in cols if c in self.features.columns]].copy()
        df = df.merge(self.predictions, on="Outlet_ID", how="left")
        if not self.dormancy.empty:
            df = df.merge(self.dormancy[["Outlet_ID", "dormancy_risk_score", "risk_band"]],
                          on="Outlet_ID", how="left")
        if not self.cluster_membership.empty:
            df = df.merge(self.cluster_membership, on="Outlet_ID", how="left")
        if not self.budget.empty:
            df = df.merge(self.budget, on="Outlet_ID", how="left")
        return df


def _read_parquet(p: Path) -> pd.DataFrame:
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


def _read_csv(p: Path) -> pd.DataFrame:
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


@lru_cache(maxsize=1)
def get_cache() -> DataCache:
    root = _repo_root()
    gold = root / "data" / "gold"
    out = root / "outputs"
    audit = out / "audit"

    cache = DataCache(repo_root=root)
    cache.features          = _read_parquet(gold / "outlet_features.parquet")
    cache.predictions       = _read_csv(out / "DataX_predictions.csv")
    cache.counterfactuals   = _read_parquet(gold / "counterfactuals.parquet")
    cache.shap_drivers      = _read_csv(audit / "shap_top_drivers_per_outlet.csv")
    cache.shap_global       = _read_csv(audit / "shap_global_importance.csv")
    cache.budget            = _read_csv(out / "DataX_budget_allocations.csv")
    cache.budget_channels   = _read_csv(audit / "budget_allocation_by_channel.csv")
    cache.budget_by_distributor = _read_csv(audit / "budget_allocation_by_distributor.csv")
    cache.cooler_roi_full   = _read_csv(audit / "cooler_roi_full.csv")
    cache.cooler_roi_top100 = _read_csv(audit / "cooler_roi_top100.csv")
    cache.dormancy          = _read_parquet(gold / "dormancy_risk.parquet")
    cache.dormancy_top      = _read_csv(audit / "dormancy_top200_at_risk.csv")
    cache.scorecard         = _read_csv(audit / "distributor_scorecard.csv")
    cache.territories       = _read_csv(audit / "territory_clusters_summary.csv")
    cache.cluster_membership = _read_parquet(gold / "outlet_clusters.parquet")
    cache.outlet_actions    = _read_parquet(gold / "outlet_actions.parquet")
    cache.forensics         = _read_csv(audit / "forensics_findings.csv")
    return cache
