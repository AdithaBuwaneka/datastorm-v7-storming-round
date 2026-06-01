"""Non-linear competitive-saturation features for each outlet.

We supplement the existing flat competitor counts and gravity score with two
complementary measures of local market structure:

  1. Herfindahl-Hirschman Index (HHI) within a fixed neighborhood radius.
     HHI sums the squared market shares of the competitors located inside
     the outlet's catchment. Higher HHI -> the local market is dominated by
     a few large outlets (concentrated). Lower HHI -> many small competitors
     (fragmented). The metric is widely used by competition authorities and
     translates naturally to retail catchment analysis.

  2. Voronoi-style territory radius. We approximate the size of each
     outlet's catchment by the mean distance to its k nearest neighbour
     outlets (k = 5). Larger radius -> more isolated outlet -> bigger
     theoretical catchment to itself.

  3. Type-weighted competition pressure: a competitor of the same Outlet_Type
     within the same neighborhood weighs heavier than a different-type one.

All features are appended to the outlet feature frame as numeric columns.
The features are deterministic functions of geometry + observed history; no
ML training is involved.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

EARTH_RADIUS_M = 6_371_000.0

HHI_RADIUS_M = 1500.0   # 1.5 km neighborhood used for market-share calc
TERRITORY_K = 5         # k nearest neighbours for territory radius estimate

# Same-vs-different outlet-type similarity: 1.0 for same type, lower otherwise.
# Roughly groups outlet types by overlap of customer demand:
#   Grocery <-> SMMT, Bakery, Eatery: significant overlap (impulse beverage buy)
#   Hotel, Pharmacy, Kiosk: lower overlap with each other
TYPE_SIMILARITY = {
    ("Grocery", "Grocery"): 1.0,  ("Grocery", "SMMT"): 0.7, ("Grocery", "Bakery"): 0.5,
    ("Grocery", "Eatery"): 0.5,    ("Grocery", "Kiosk"): 0.7, ("Grocery", "Pharmacy"): 0.3,
    ("Grocery", "Hotel"): 0.2,
    ("SMMT", "SMMT"): 1.0,         ("SMMT", "Bakery"): 0.4, ("SMMT", "Eatery"): 0.4,
    ("SMMT", "Kiosk"): 0.6,        ("SMMT", "Pharmacy"): 0.3, ("SMMT", "Hotel"): 0.2,
    ("Bakery", "Bakery"): 1.0,     ("Bakery", "Eatery"): 0.6,
    ("Bakery", "Kiosk"): 0.4,      ("Bakery", "Pharmacy"): 0.2, ("Bakery", "Hotel"): 0.3,
    ("Eatery", "Eatery"): 1.0,     ("Eatery", "Hotel"): 0.5,
    ("Eatery", "Kiosk"): 0.4,      ("Eatery", "Pharmacy"): 0.2,
    ("Pharmacy", "Pharmacy"): 1.0, ("Pharmacy", "Kiosk"): 0.3, ("Pharmacy", "Hotel"): 0.1,
    ("Hotel", "Hotel"): 1.0,       ("Hotel", "Kiosk"): 0.2,
    ("Kiosk", "Kiosk"): 1.0,
}


def _pair_sim(a: str, b: str) -> float:
    """Symmetric type-similarity lookup; unknown pairs default to 0.3."""
    key = (a, b) if (a, b) in TYPE_SIMILARITY else (b, a)
    return float(TYPE_SIMILARITY.get(key, 0.3))


def _build_tree(coords_deg: np.ndarray) -> BallTree:
    return BallTree(np.radians(coords_deg), metric="haversine")


def compute_hhi(outlets: pd.DataFrame, market_share_col: str) -> pd.Series:
    """HHI of the neighborhood within HHI_RADIUS_M, computed per outlet.

    Market share proxy is the value in `market_share_col` (e.g.,
    monthly_volume_mean) — relative weight of each neighbour. We sum
    squared shares of *only* the competitors strictly inside the radius
    (the outlet itself is excluded).
    """
    coords = outlets[["Latitude", "Longitude"]].to_numpy(dtype=float)
    shares = outlets[market_share_col].fillna(0.0).clip(lower=0.0).to_numpy(dtype=float)
    n = len(outlets)
    if n == 0:
        return pd.Series([], index=outlets.index, dtype=float)

    tree = _build_tree(coords)
    radius_rad = HHI_RADIUS_M / EARTH_RADIUS_M
    idxs = tree.query_radius(np.radians(coords), r=radius_rad)

    hhi = np.zeros(n, dtype=float)
    for i, neighbours in enumerate(idxs):
        # Exclude self
        nb = neighbours[neighbours != i]
        if nb.size == 0:
            hhi[i] = 0.0
            continue
        local_shares = shares[nb]
        s = local_shares.sum()
        if s <= 0:
            hhi[i] = 0.0
            continue
        s_norm = local_shares / s
        hhi[i] = float((s_norm ** 2).sum())  # in [0, 1]
    # Rescale to the standard 0-10000 HHI range used in regulation
    return pd.Series(hhi * 10_000.0, index=outlets.index, name="hhi_1500m")


def compute_territory_radius(outlets: pd.DataFrame, k: int = TERRITORY_K) -> pd.Series:
    """Mean distance (m) to the k nearest neighbour outlets."""
    coords = outlets[["Latitude", "Longitude"]].to_numpy(dtype=float)
    n = len(coords)
    if n <= 1:
        return pd.Series(np.full(n, 0.0), index=outlets.index, name="territory_radius_m")

    tree = _build_tree(coords)
    k_eff = min(k + 1, n)
    dists_rad, _ = tree.query(np.radians(coords), k=k_eff)
    # First column is the outlet itself (distance 0); skip it
    if dists_rad.shape[1] > 1:
        mean_dist_rad = dists_rad[:, 1:].mean(axis=1)
    else:
        mean_dist_rad = dists_rad[:, 0]
    return pd.Series(mean_dist_rad * EARTH_RADIUS_M, index=outlets.index,
                     name="territory_radius_m")


def compute_type_weighted_pressure(outlets: pd.DataFrame) -> pd.Series:
    """Sum of type-similarity weights of competitors within HHI_RADIUS_M.

    A nearby same-type outlet contributes weight 1.0; a different-type one
    contributes its similarity (0.1 to 0.7). The result is a heavier penalty
    for clustered same-type competition than for mixed-type neighborhoods.
    """
    coords = outlets[["Latitude", "Longitude"]].to_numpy(dtype=float)
    types = outlets["Outlet_Type"].astype(str).to_numpy()
    n = len(outlets)
    if n == 0:
        return pd.Series([], index=outlets.index, dtype=float, name="type_weighted_pressure")

    tree = _build_tree(coords)
    radius_rad = HHI_RADIUS_M / EARTH_RADIUS_M
    idxs = tree.query_radius(np.radians(coords), r=radius_rad)

    out = np.zeros(n, dtype=float)
    for i, neighbours in enumerate(idxs):
        nb = neighbours[neighbours != i]
        if nb.size == 0:
            continue
        own = types[i]
        out[i] = float(sum(_pair_sim(own, types[j]) for j in nb))
    return pd.Series(out, index=outlets.index, name="type_weighted_pressure")


def add_features(feats: pd.DataFrame,
                 market_share_col: str = "monthly_volume_mean") -> pd.DataFrame:
    """Append HHI, territory radius, and type-weighted pressure to feats."""
    if feats.empty:
        return feats
    out = feats.copy()
    out["hhi_1500m"] = compute_hhi(out, market_share_col=market_share_col).values
    out["territory_radius_m"] = compute_territory_radius(out).values
    out["type_weighted_pressure"] = compute_type_weighted_pressure(out).values

    # Derived flags: heavy concentration / wide isolation
    out["market_concentrated_flag"] = (out["hhi_1500m"] >= 2500).astype(int)
    out["market_fragmented_flag"]   = (out["hhi_1500m"] <= 1500).astype(int)
    out["isolated_territory_flag"]  = (out["territory_radius_m"] >= out["territory_radius_m"].quantile(0.75)).astype(int)
    return out


def summary_table(feats: pd.DataFrame) -> pd.DataFrame:
    """Province-level summary used in audit artifacts."""
    cols = ["hhi_1500m", "territory_radius_m", "type_weighted_pressure"]
    avail = [c for c in cols if c in feats.columns]
    if not avail:
        return pd.DataFrame()
    return feats.groupby("Province")[avail].agg(["mean", "median"]).round(2)
