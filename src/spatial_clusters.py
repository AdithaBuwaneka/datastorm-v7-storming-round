"""Geographic outlet clustering for territory definition.

HDBSCAN over outlet coordinates (haversine on the sphere) groups outlets
into natural geographic markets. Unlike a fixed administrative cut, the
result is data-driven and adapts to outlet density: tight clusters appear
in Colombo metro, looser ones in rural districts.

Each cluster becomes a "natural territory" that the trade-marketing team
can use to plan sales-rep routes, promotional sweeps, or distributor
re-balancing.

Per-cluster aggregates:
  cluster_id, n_outlets, centroid_lat/lon, span_km
  total_predicted_jan2026, median_predicted_jan2026
  dominant_outlet_type, dominant_province, dominant_distributor
  avg_hhi_1500m, avg_type_weighted_pressure, avg_spatial_demand_score
  avg_competitors_1km, avg_cooler_count

Outputs:
  data/gold/outlet_clusters.parquet            - per-outlet cluster_id
  outputs/audit/territory_clusters_summary.csv - per-cluster aggregates
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import HDBSCAN

from src import config


EARTH_RADIUS_KM = 6_371.0
# Tuned to surface sub-province "sales territories" rather than just the four
# administrative regions. We use leaf cluster selection with a modest min_size
# so dense urban clusters split apart while rural areas still receive a
# sensible territory id.
MIN_CLUSTER_SIZE = 60
MIN_SAMPLES = 5
CLUSTER_SELECTION_METHOD = "leaf"
CLUSTER_SELECTION_EPSILON_KM = 0.0   # no merging — preserve fine sub-territories


def fit_clusters(outlets: pd.DataFrame) -> np.ndarray:
    coords = outlets[["Latitude", "Longitude"]].to_numpy(dtype=float)
    rad = np.radians(coords)
    eps_rad = CLUSTER_SELECTION_EPSILON_KM / EARTH_RADIUS_KM

    model = HDBSCAN(
        min_cluster_size=MIN_CLUSTER_SIZE,
        min_samples=MIN_SAMPLES,
        metric="haversine",
        cluster_selection_method=CLUSTER_SELECTION_METHOD,
        cluster_selection_epsilon=eps_rad,
        n_jobs=-1,
    )
    labels = model.fit_predict(rad)

    # Reduce noise: assign each unclustered outlet to its nearest cluster's
    # centroid so the trade-marketing team has a territory for every outlet.
    if (labels == -1).any() and (labels >= 0).any():
        labels = _attach_noise_to_nearest(rad, labels)
    return labels


def _attach_noise_to_nearest(rad_coords: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Reassign noise points (-1) to the nearest cluster centroid (haversine)."""
    out = labels.copy()
    pos = labels >= 0
    if not pos.any():
        return out

    # Compute centroid per cluster (mean of radian coords)
    cluster_ids = np.unique(labels[pos])
    centroids = np.array([rad_coords[labels == c].mean(axis=0) for c in cluster_ids])

    noise_idx = np.where(labels == -1)[0]
    if noise_idx.size == 0:
        return out

    noise_coords = rad_coords[noise_idx]
    # Haversine distance to each centroid
    dlat = noise_coords[:, [0]] - centroids[:, 0]
    dlon = noise_coords[:, [1]] - centroids[:, 1]
    a = (np.sin(dlat / 2.0) ** 2
         + np.cos(noise_coords[:, [0]]) * np.cos(centroids[:, 0])
         * np.sin(dlon / 2.0) ** 2)
    d = 2.0 * np.arcsin(np.sqrt(a))
    nearest = d.argmin(axis=1)
    out[noise_idx] = cluster_ids[nearest]
    return out


def _haversine_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    p1 = np.radians([a_lat, a_lon])
    p2 = np.radians([b_lat, b_lon])
    dlat = p2[0] - p1[0]
    dlon = p2[1] - p1[1]
    h = (np.sin(dlat / 2.0) ** 2
         + np.cos(p1[0]) * np.cos(p2[0]) * np.sin(dlon / 2.0) ** 2)
    return float(2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(h)))


def summarise_clusters(outlets: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cid, grp in outlets.groupby("cluster_id"):
        if cid == -1:
            continue
        clat = float(grp["Latitude"].mean())
        clon = float(grp["Longitude"].mean())

        # Span: max pairwise distance approximated by 2x radius from centroid
        max_dist_km = 0.0
        sample = grp[["Latitude", "Longitude"]].to_numpy()
        if len(sample) > 1:
            ds = np.array([
                _haversine_km(clat, clon, float(r[0]), float(r[1]))
                for r in sample
            ])
            max_dist_km = float(ds.max())

        rows.append({
            "cluster_id": int(cid),
            "n_outlets": int(len(grp)),
            "centroid_lat": round(clat, 5),
            "centroid_lon": round(clon, 5),
            "radius_km": round(max_dist_km, 3),
            "total_predicted_jan2026":   round(float(grp["Maximum_Monthly_Liters"].sum()), 0),
            "median_predicted_jan2026":  round(float(grp["Maximum_Monthly_Liters"].median()), 2),
            "dominant_outlet_type":      grp["Outlet_Type"].mode().iat[0],
            "dominant_province":         grp["Province"].mode().iat[0],
            "dominant_distributor":      grp["Distributor_ID"].mode().iat[0],
            "avg_hhi_1500m":             round(float(grp["hhi_1500m"].mean()), 2),
            "avg_type_pressure":         round(float(grp["type_weighted_pressure"].mean()), 2),
            "avg_spatial_demand":        round(float(grp["spatial_demand_score"].mean()), 4),
            "avg_competitors_1km":       round(float(grp["competitors_1km"].mean()), 2),
            "avg_cooler_count":          round(float(grp["Cooler_Count"].mean()), 2),
        })
    return (pd.DataFrame(rows)
            .sort_values("total_predicted_jan2026", ascending=False)
            .reset_index(drop=True))


def main() -> None:
    print("\n" + "=" * 70)
    print("Geographic outlet clustering (HDBSCAN, haversine)")
    print("=" * 70)
    print(f"  min_cluster_size = {MIN_CLUSTER_SIZE}, min_samples = {MIN_SAMPLES}")

    feats = pd.read_parquet(config.GOLD / "outlet_features.parquet")
    preds = pd.read_csv(config.OUTPUTS / f"{config.TEAM_NAME}_predictions.csv")

    df = feats.merge(preds, on="Outlet_ID", how="left").copy()
    df["cluster_id"] = fit_clusters(df).astype(int)

    n_clusters = int((df["cluster_id"] >= 0).any() and df["cluster_id"].nunique() - (1 if -1 in df["cluster_id"].values else 0))
    n_noise = int((df["cluster_id"] == -1).sum())
    print(f"  Clusters discovered: {n_clusters}")
    print(f"  Outlets assigned:    {(df['cluster_id'] >= 0).sum():,}")
    print(f"  Noise (unclustered): {n_noise:,}")

    # Persist per-outlet cluster id
    out = df[["Outlet_ID", "cluster_id"]].sort_values("Outlet_ID")
    out_path = config.GOLD / "outlet_clusters.parquet"
    out.to_parquet(out_path, index=False)
    print(f"  -> {out_path}  shape={out.shape}")

    # Per-cluster summary
    summary = summarise_clusters(df)
    summ_path = config.AUDIT / "territory_clusters_summary.csv"
    summary.to_csv(summ_path, index=False)
    print(f"  -> {summ_path}  shape={summary.shape}")
    print()
    print("Top 10 territories by predicted potential:")
    print(summary.head(10)[
        ["cluster_id", "n_outlets", "dominant_province", "dominant_outlet_type",
         "radius_km", "total_predicted_jan2026", "avg_hhi_1500m",
         "avg_competitors_1km"]
    ].to_string(index=False))

    print("\nSpatial clustering: OK")


if __name__ == "__main__":
    main()
