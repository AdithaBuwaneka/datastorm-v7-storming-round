"""Fetch POI counts from OpenStreetMap via Overpass API and join to outlets.

Strategy:
  1. For each of N POI tags, issue ONE bbox query covering all of Sri Lanka.
     This is 16 queries total, not 20,000 (16 x per-outlet).
  2. Cache the raw JSON responses so re-runs are free.
  3. Build a single (lat, lon, tag_key, tag_value) POI dataframe.
  4. Build a BallTree (haversine, radians) over the POIs.
  5. For each outlet, count nearby POIs within 1km / 2km / 5km.
  6. Save 1 row per outlet with 16 tags x 3 radii = 48 count columns.

Output: data/silver/clean/poi_clean.parquet
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.neighbors import BallTree

from src import config


OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "DataStorm7.0-DataX/1.0 (academic competition; contact: team)"
EARTH_RADIUS_M = 6_371_000.0


def _query_for_tag(key: str, value: str, bbox: tuple) -> str:
    """Build an Overpass QL query that returns nodes + way-centres + relation-centres
    matching key=value inside bbox. `out center` gives lat/lon even for ways/relations.
    """
    south, west, north, east = bbox
    return f"""
[out:json][timeout:180];
(
  node["{key}"="{value}"]({south},{west},{north},{east});
  way["{key}"="{value}"]({south},{west},{north},{east});
  relation["{key}"="{value}"]({south},{west},{north},{east});
);
out center;
"""


def _cache_path(key: str, value: str) -> Path:
    safe = f"{key}_{value}".replace("/", "_")
    return config.POI_RAW / f"overpass_{safe}.json"


def fetch_with_retry(key: str, value: str,
                     max_retries: int = 4,
                     base_wait_s: float = 8.0) -> dict:
    """Fetch one (key, value) tag with exponential backoff. Uses local cache."""
    cache = _cache_path(key, value)
    if cache.exists() and cache.stat().st_size > 100:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass  # corrupted cache: re-fetch

    query = _query_for_tag(key, value, config.SL_BBOX)
    for attempt in range(max_retries):
        try:
            r = requests.post(
                OVERPASS_URL,
                data={"data": query},
                headers={"User-Agent": USER_AGENT},
                timeout=200,
            )
            if r.status_code == 200:
                data = r.json()
                cache.write_text(json.dumps(data), encoding="utf-8")
                return data
            elif r.status_code in (429, 504):
                wait = base_wait_s * (2 ** attempt)
                print(f"    [retry] {key}={value} HTTP {r.status_code}, wait {wait}s")
                time.sleep(wait)
            else:
                print(f"    [fail] {key}={value} HTTP {r.status_code}: {r.text[:120]}")
                return {"elements": []}
        except Exception as e:
            wait = base_wait_s * (2 ** attempt)
            print(f"    [retry] {key}={value} exception {e}, wait {wait}s")
            time.sleep(wait)
    print(f"    [give-up] {key}={value} after {max_retries} retries")
    return {"elements": []}


def parse_elements(data: dict, tag_key: str, tag_value: str) -> pd.DataFrame:
    """Extract (lat, lon) per element from Overpass JSON."""
    rows = []
    for el in data.get("elements", []):
        # nodes have lat/lon directly; ways/relations have center.{lat,lon}
        lat = el.get("lat", el.get("center", {}).get("lat"))
        lon = el.get("lon", el.get("center", {}).get("lon"))
        if lat is None or lon is None:
            continue
        rows.append({"lat": lat, "lon": lon, "tag_key": tag_key, "tag_value": tag_value})
    return pd.DataFrame(rows)


def fetch_all_pois() -> pd.DataFrame:
    config.POI_RAW.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []
    for i, (key, value) in enumerate(config.POI_TAGS, 1):
        print(f"  [{i}/{len(config.POI_TAGS)}] fetching {key}={value} ...")
        data = fetch_with_retry(key, value)
        df = parse_elements(data, key, value)
        print(f"    -> {len(df):,} POIs in Sri Lanka bbox")
        frames.append(df)
        time.sleep(1.0)  # polite spacing between queries
    poi = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["lat", "lon", "tag_key", "tag_value"]
    )
    return poi


def count_pois_per_outlet(outlets: pd.DataFrame, poi: pd.DataFrame) -> pd.DataFrame:
    """For each outlet, count POIs of each tag within each radius.

    Returns: DataFrame indexed by Outlet_ID with columns
      poi_{key}_{value}_{radius_km}km
    """
    # Outlet positions in radians
    o = outlets[["Latitude", "Longitude"]].to_numpy()
    o_rad = np.radians(o)

    result = outlets[["Outlet_ID", "Latitude", "Longitude"]].copy().reset_index(drop=True)

    for (key, value) in config.POI_TAGS:
        mask = (poi["tag_key"] == key) & (poi["tag_value"] == value)
        sub = poi.loc[mask]
        col_base = f"poi_{key}_{value}".replace("/", "_")
        if sub.empty:
            for r_m in config.POI_RADII_M:
                r_km = r_m // 1000
                result[f"{col_base}_{r_km}km"] = 0
            continue

        p_rad = np.radians(sub[["lat", "lon"]].to_numpy())
        tree = BallTree(p_rad, metric="haversine")

        for r_m in config.POI_RADII_M:
            r_km = r_m // 1000
            r_rad = r_m / EARTH_RADIUS_M
            counts = tree.query_radius(o_rad, r=r_rad, count_only=True)
            result[f"{col_base}_{r_km}km"] = counts

    # Aggregate density features (handy for modeling cohorts)
    radii_km = [m // 1000 for m in config.POI_RADII_M]
    for r_km in radii_km:
        cols = [c for c in result.columns if c.endswith(f"_{r_km}km")]
        result[f"poi_total_{r_km}km"] = result[cols].sum(axis=1)

    return result


def main() -> int:
    print(f"POI scraping: bbox={config.SL_BBOX}, {len(config.POI_TAGS)} tags")
    poi = fetch_all_pois()
    print(f"\nTotal POIs across all tags: {len(poi):,}")

    # Persist raw aggregated POI table (forensic artifact + reproducibility)
    raw_out = config.BRONZE / "poi_raw" / "_aggregated_pois.parquet"
    poi.to_parquet(raw_out, index=False)
    print(f"Aggregated POIs saved: {raw_out}")

    # Load cleaned coordinates from silver
    coords_path = config.SILVER_CLEAN / "outlet_coordinates_clean.parquet"
    coords = pd.read_parquet(coords_path)
    print(f"Outlets to join: {len(coords):,}")

    result = count_pois_per_outlet(coords, poi)
    out = config.SILVER_CLEAN / "poi_clean.parquet"
    result.to_parquet(out, index=False)
    print(f"\nPOI clean saved: {out}  shape={result.shape}")
    # Sanity: at least one tag has non-zero counts
    poi_cols = [c for c in result.columns if c.startswith("poi_")]
    non_zero_per_tag = (result[poi_cols] > 0).sum().sort_values(ascending=False)
    print("Top 10 features by non-zero outlet count:")
    print(non_zero_per_tag.head(10).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
