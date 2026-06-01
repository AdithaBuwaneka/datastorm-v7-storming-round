"""Gold layer: build the outlet-month panel and engineer per-outlet features.

Outputs:
  data/gold/outlet_month_panel.parquet   — (Outlet_ID, Year, Month, agg metrics)
  data/gold/outlet_features.parquet       — one row per outlet, ~50 features
  data/bronze/jan_2026_holidays.csv       — manually-curated target-month holidays
  outputs/audit/yoy_growth_factors.csv    — per-distributor YoY growth
  outputs/audit/seasonality_extrapolation.csv — per-distributor Jan-2026 index decision
  outputs/audit/seasonality_multipliers.csv   — Index level -> numeric multiplier
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src import forensics as fx


# ---------------------------------------------------------------------------
# January 2026 holiday lookup (target-month, file ends 2025-12-25 in source)
# Sri Lanka public holidays for January 2026 (lunar + fixed). Conservative set
# matching the structure of historical Januaries in holiday_list.csv. Multiple
# types per date (Public/Bank/Mercantile) mirror the source data convention.
# ---------------------------------------------------------------------------
JAN_2026_HOLIDAYS = [
    # Duruthu Full Moon Poya Day - January 3, 2026 (Saturday)
    ("2026-01-03", "Duruthu Full Moon Poya Day", "Public"),
    ("2026-01-03", "Duruthu Full Moon Poya Day", "Bank"),
    ("2026-01-03", "Duruthu Full Moon Poya Day", "Mercantile"),
    ("2026-01-03", "Duruthu Full Moon Poya Day", "Poya Day"),
    # Tamil Thai Pongal Day - January 14, 2026 (Wednesday)
    ("2026-01-14", "Tamil Thai Pongal Day", "Public"),
    ("2026-01-14", "Tamil Thai Pongal Day", "Bank"),
    ("2026-01-14", "Tamil Thai Pongal Day", "Mercantile"),
]


def write_jan_2026_holidays() -> pd.DataFrame:
    df = pd.DataFrame(JAN_2026_HOLIDAYS, columns=["Date", "Holiday_Name", "Holiday_Type"])
    df["Date"] = pd.to_datetime(df["Date"])
    out = config.BRONZE / "jan_2026_holidays.csv"
    df.to_csv(out, index=False)
    print(f"  Jan 2026 holidays written: {out}  rows={len(df)}")
    return df


# ---------------------------------------------------------------------------
# Outlet-month panel: aggregate SKU lines, fill missing months with zero
# ---------------------------------------------------------------------------

def build_outlet_month_panel(transactions: pd.DataFrame,
                              outlets_with_coords: set[str]) -> pd.DataFrame:
    """Aggregate transactions to (Outlet_ID, Year, Month) and reindex so
    every outlet has all 36 months present (gaps -> 0 volume)."""
    # Use only transactions whose outlets survived BOTH master and coords cleaning
    txns = transactions.loc[transactions["Outlet_ID"].isin(outlets_with_coords)].copy()
    print(f"  transactions filtered to outlets-with-coords: {len(txns):,}")

    # Returns subtract correctly because txn_tag classification kept them with negative volume
    panel = (txns.groupby(["Outlet_ID", "Year", "Month"])
                  .agg(monthly_volume=("Volume_Liters", "sum"),
                       monthly_revenue=("Total_Bill_Value", "sum"),
                       distinct_skus=("SKU_ID", "nunique"))
                  .reset_index())

    # Reindex: each outlet must have all 36 (Year, Month) rows
    all_months = pd.MultiIndex.from_product(
        [sorted(outlets_with_coords), [2023, 2024, 2025], range(1, 13)],
        names=["Outlet_ID", "Year", "Month"],
    )
    panel = (panel.set_index(["Outlet_ID", "Year", "Month"])
                  .reindex(all_months)
                  .fillna({"monthly_volume": 0.0, "monthly_revenue": 0.0,
                           "distinct_skus": 0})
                  .reset_index())

    panel["distinct_skus"] = panel["distinct_skus"].astype(int)
    print(f"  panel shape (outlets x 36 months): {panel.shape}")
    return panel


def compute_competitor_density(coords: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """For each outlet, count number of OTHER outlets within multiple radii.
    Uses BallTree haversine (radians). Captures local beverage-retail competition.
    Also computes competitors of SAME type vs different type.

    Returns DataFrame indexed by Outlet_ID with columns:
      competitors_200m, competitors_500m, competitors_1km, competitors_2km
      same_type_competitors_500m, same_type_competitors_1km, same_type_competitors_2km
      market_saturation_index, is_isolated
    """
    from sklearn.neighbors import BallTree
    EARTH_R = 6_371_000.0

    df = coords.merge(master[["Outlet_ID", "Outlet_Type"]], on="Outlet_ID", how="inner")
    pos_rad = np.radians(df[["Latitude", "Longitude"]].to_numpy())
    tree = BallTree(pos_rad, metric="haversine")

    out = df[["Outlet_ID", "Outlet_Type"]].copy().reset_index(drop=True)
    name_map = {
        200: "competitors_200m",
        500: "competitors_500m",
        1000: "competitors_1km",
        2000: "competitors_2km",
    }
    for r_m, col in name_map.items():
        r_rad = r_m / EARTH_R
        counts = tree.query_radius(pos_rad, r=r_rad, count_only=True) - 1  # exclude self
        out[col] = counts

    # Same-type competitors: count nearby outlets that share Outlet_Type
    # (a beverage-specific competition signal)
    same_type_counts = {500: np.zeros(len(df), dtype=int),
                         1000: np.zeros(len(df), dtype=int),
                         2000: np.zeros(len(df), dtype=int)}
    types = df["Outlet_Type"].to_numpy()
    for r_m in (500, 1000, 2000):
        r_rad = r_m / EARTH_R
        neighbors = tree.query_radius(pos_rad, r=r_rad)
        for i, neigh in enumerate(neighbors):
            same_type_counts[r_m][i] = int((types[neigh] == types[i]).sum()) - 1  # exclude self

    out["same_type_competitors_500m"] = same_type_counts[500]
    out["same_type_competitors_1km"]  = same_type_counts[1000]
    out["same_type_competitors_2km"]  = same_type_counts[2000]

    # Saturation + isolation indicators
    out["market_saturation_index"] = (
        out["competitors_200m"] * 3
        + out["competitors_500m"] * 2
        + out["competitors_1km"] * 1
    ) / 6.0
    out["is_isolated"] = (out["competitors_1km"] < 3).astype(int)

    return out.drop(columns=["Outlet_Type"])


def attach_distributor(panel: pd.DataFrame, transactions: pd.DataFrame) -> pd.DataFrame:
    """Each outlet's primary distributor = most-frequent Distributor_ID across
    its transactions. Returns panel with Distributor_ID column attached.
    """
    # mode per outlet
    primary = (transactions.groupby("Outlet_ID")["Distributor_ID"]
                            .agg(lambda s: s.value_counts().index[0])
                            .rename("Distributor_ID")
                            .reset_index())
    return panel.merge(primary, on="Outlet_ID", how="left")


# ---------------------------------------------------------------------------
# SKU mix features (premium / mass / mid share + price tier + diversity)
#
# Empirical price tiers derived from observed price-per-liter:
#   Mass     (avg < 100 LKR/L): SKU_05, SKU_06
#   Mid-tier (200-400 LKR/L):    SKU_01, SKU_02, SKU_03, SKU_04, SKU_10
#   Premium  (400-700 LKR/L):    SKU_07, SKU_08
#   Super-premium (>1000 LKR/L): SKU_09
# ---------------------------------------------------------------------------

SKU_TIER = {
    "SKU_05": "mass",        "SKU_06": "mass",
    "SKU_01": "mid",         "SKU_02": "mid",  "SKU_03": "mid",
    "SKU_04": "mid",         "SKU_10": "mid",
    "SKU_07": "premium",     "SKU_08": "premium",
    "SKU_09": "super_premium",
}


def compute_sku_mix(transactions: pd.DataFrame) -> pd.DataFrame:
    """Per-outlet SKU mix features. Returns one row per Outlet_ID with:
       avg_price_per_liter, premium_share, mass_share, mid_share, super_premium_share,
       sku_diversity, top_sku_share.
    """
    t = transactions.copy()
    t["sku_tier"] = t["SKU_ID"].map(SKU_TIER).fillna("mid")
    # Use absolute volume so returns don't artificially deflate
    t["abs_vol"] = t["Volume_Liters"].abs()
    t["abs_bill"] = t["Total_Bill_Value"].abs()

    # Volume-weighted average price per liter
    grp = t.groupby("Outlet_ID")
    total_vol = grp["abs_vol"].sum()
    total_bill = grp["abs_bill"].sum()
    avg_price = (total_bill / total_vol.replace(0, np.nan)).rename("avg_price_per_liter")

    # Tier shares (volume-weighted)
    tier_vol = (t.groupby(["Outlet_ID", "sku_tier"])["abs_vol"].sum()
                 .unstack(fill_value=0))
    tier_share = tier_vol.div(tier_vol.sum(axis=1), axis=0).fillna(0)
    for col in ["mass", "mid", "premium", "super_premium"]:
        if col not in tier_share.columns:
            tier_share[col] = 0.0
    tier_share = tier_share.rename(columns={
        "mass": "mass_share",
        "mid": "mid_share",
        "premium": "premium_share",
        "super_premium": "super_premium_share",
    })

    # SKU diversity + top-SKU dominance
    sku_diversity = grp["SKU_ID"].nunique().rename("sku_diversity")
    top_sku_share = (t.groupby(["Outlet_ID", "SKU_ID"])["abs_vol"].sum()
                       .groupby(level=0).apply(lambda s: s.max() / s.sum() if s.sum() > 0 else 0)
                       .rename("top_sku_share"))

    return pd.concat([avg_price, tier_share, sku_diversity, top_sku_share], axis=1).reset_index()


# ---------------------------------------------------------------------------
# Constraint indicators at outlet-month level (used by modeling Phase 5)
# ---------------------------------------------------------------------------

def add_stockout_flag(panel: pd.DataFrame) -> pd.DataFrame:
    """Stockout = zero volume month with both adjacent months non-zero."""
    p = panel.sort_values(["Outlet_ID", "Year", "Month"]).copy()
    p["prev_v"] = p.groupby("Outlet_ID")["monthly_volume"].shift(1)
    p["next_v"] = p.groupby("Outlet_ID")["monthly_volume"].shift(-1)
    p["stockout_flag"] = (
        (p["monthly_volume"] == 0)
        & (p["prev_v"].fillna(0) > 0)
        & (p["next_v"].fillna(0) > 0)
    ).astype(int)
    p = p.drop(columns=["prev_v", "next_v"])
    return p


# ---------------------------------------------------------------------------
# Seasonality calibration
# ---------------------------------------------------------------------------

def calibrate_seasonality(panel: pd.DataFrame,
                          seasonality: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Translate categorical Seasonality_Index -> numeric per-distributor multiplier.

    Method: average monthly_volume per (Distributor_ID, Seasonality_Index level),
    divided by overall distributor mean. Multiplier of 1.0 = average month.
    """
    merged = panel.merge(seasonality, on=["Distributor_ID", "Year", "Month"], how="left")

    # Distributor-level mean monthly volume (baseline)
    baseline = merged.groupby("Distributor_ID")["monthly_volume"].mean().rename("baseline_mean")

    # Mean per (Distributor, Index level)
    by_level = merged.groupby(["Distributor_ID", "Seasonality_Index"])["monthly_volume"].mean()
    multipliers = by_level.unstack().div(baseline, axis=0)
    multipliers = multipliers.reset_index()
    multipliers.columns.name = None
    # Reorder columns: Distributor_ID, then levels
    cols = ["Distributor_ID"] + [c for c in multipliers.columns if c != "Distributor_ID"]
    multipliers = multipliers[cols]

    audit = config.AUDIT / "seasonality_multipliers.csv"
    multipliers.to_csv(audit, index=False)
    print(f"  seasonality multipliers saved: {audit}")
    return merged, multipliers


def extrapolate_jan_2026_seasonality(seasonality: pd.DataFrame) -> pd.DataFrame:
    """For each distributor, decide Jan-2026 Seasonality_Index using majority
    vote across (Jan 2023, Jan 2024, Jan 2025); fall back to most recent."""
    rows = []
    for dist, g in seasonality[seasonality["Month"] == 1].groupby("Distributor_ID"):
        by_year = dict(zip(g["Year"], g["Seasonality_Index"]))
        labels = [by_year.get(y) for y in (2023, 2024, 2025)]
        labels_clean = [l for l in labels if l is not None]

        counts = pd.Series(labels_clean).value_counts()
        if len(counts) == 1:
            decision, rule = counts.index[0], "all_agree"
        elif counts.iloc[0] > counts.iloc[1]:
            decision, rule = counts.index[0], "majority"
        else:
            decision, rule = by_year.get(2025, labels_clean[-1]), "use_most_recent"

        rows.append({
            "Distributor_ID": dist,
            "Jan_2023": by_year.get(2023),
            "Jan_2024": by_year.get(2024),
            "Jan_2025": by_year.get(2025),
            "Jan_2026_assumed": decision,
            "rule_applied": rule,
        })

    audit = pd.DataFrame(rows)
    out = config.AUDIT / "seasonality_extrapolation.csv"
    audit.to_csv(out, index=False)
    print(f"  Jan 2026 seasonality extrapolation saved: {out}")
    return audit


# ---------------------------------------------------------------------------
# Year-over-Year growth multiplier per distributor
# ---------------------------------------------------------------------------

def compute_yoy_growth(panel: pd.DataFrame) -> pd.DataFrame:
    """Geometric mean of Jan-over-Jan growth per distributor, clipped."""
    jan = (panel[panel["Month"] == 1]
           .groupby(["Distributor_ID", "Year"])["monthly_volume"]
           .sum()
           .unstack("Year"))
    g_24_23 = jan[2024] / jan[2023].replace(0, np.nan)
    g_25_24 = jan[2025] / jan[2024].replace(0, np.nan)
    yoy = np.sqrt(g_24_23 * g_25_24)
    lo, hi = config.YOY_CLIP
    yoy_clipped = yoy.clip(lo, hi)

    audit = pd.DataFrame({
        "Distributor_ID": jan.index,
        "Jan_2023_sum": jan[2023].values,
        "Jan_2024_sum": jan[2024].values,
        "Jan_2025_sum": jan[2025].values,
        "growth_24_23": g_24_23.values,
        "growth_25_24": g_25_24.values,
        "yoy_geom_mean": yoy.values,
        "yoy_clipped": yoy_clipped.values,
    })
    out = config.AUDIT / "yoy_growth_factors.csv"
    audit.to_csv(out, index=False)
    print(f"  YoY growth factors saved: {out}")
    return audit


# ---------------------------------------------------------------------------
# Per-outlet feature engineering
# ---------------------------------------------------------------------------

def _trend_slope(values: np.ndarray) -> float:
    """OLS slope of values vs index (months)."""
    n = len(values)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    x_mean = x.mean()
    y_mean = values.mean()
    denom = ((x - x_mean) ** 2).sum()
    if denom == 0:
        return 0.0
    return float(((x - x_mean) * (values - y_mean)).sum() / denom)


def build_outlet_features(panel: pd.DataFrame,
                          master: pd.DataFrame,
                          coords: pd.DataFrame,
                          poi: pd.DataFrame,
                          sku_mix: pd.DataFrame = None,
                          competitors: pd.DataFrame = None) -> pd.DataFrame:
    """One row per outlet with ~50 engineered features."""
    p = panel.sort_values(["Outlet_ID", "Year", "Month"])

    # ---- Volume stats per outlet ----
    print("    [features] aggregating volume stats per outlet ...")
    agg_funcs = {
        "monthly_volume": [
            "mean", "median", "std", "min", "max",
            ("q25", lambda x: np.quantile(x, 0.25)),
            ("q75", lambda x: np.quantile(x, 0.75)),
            ("q90", lambda x: np.quantile(x, 0.90)),
            ("q95", lambda x: np.quantile(x, 0.95)),
        ],
        "monthly_revenue": ["mean", "median"],
        "distinct_skus":   ["mean", "max"],
        "stockout_flag":   ["sum"],
    }
    stats = p.groupby("Outlet_ID").agg(agg_funcs)
    stats.columns = ["_".join(c).strip("_") if isinstance(c, tuple) else c
                     for c in stats.columns]
    stats = stats.reset_index()

    # ---- Activity / censoring signals ----
    print("    [features] computing activity & censoring signals ...")
    def per_outlet(g: pd.DataFrame) -> pd.Series:
        v = g["monthly_volume"].to_numpy()
        active = (v > 0).sum()
        return pd.Series({
            "active_months":         int(active),
            "active_share":          float(active / len(v)) if len(v) else 0.0,
            "zero_months_count":     int((v == 0).sum()),
            "zero_months_share":     float((v == 0).mean()),
            "monthly_cv":            float(v.std() / v.mean()) if v.mean() > 0 else 0.0,
            "trend_slope":           _trend_slope(v),
        })
    activity = p.groupby("Outlet_ID", group_keys=False).apply(per_outlet).reset_index()

    # max_consecutive_zeros computed separately for speed
    print("    [features] computing max consecutive zeros ...")
    def max_consec_zeros(g: pd.DataFrame) -> int:
        v = (g["monthly_volume"].to_numpy() == 0).astype(int)
        best = cur = 0
        for z in v:
            cur = cur + 1 if z else 0
            if cur > best:
                best = cur
        return best
    mcz = (p.groupby("Outlet_ID", group_keys=False)
             .apply(lambda g: pd.Series({"max_consecutive_zeros": max_consec_zeros(g)}))
             .reset_index())

    # ---- January-specific features (across 2023, 2024, 2025) ----
    print("    [features] January-specific stats ...")
    jan = p[p["Month"] == 1]
    jan_stats = (jan.groupby("Outlet_ID")
                 .agg(jan_mean=("monthly_volume", "mean"),
                      jan_max=("monthly_volume", "max"))
                 .reset_index())

    # ---- Merge with master, coords, POI ----
    print("    [features] merging master/coords/POI ...")
    master_subset = master[["Outlet_ID", "Outlet_Size", "Cooler_Count", "Outlet_Type"]]

    # Province from distributor mapping (need distributor per outlet from panel)
    dist_per_outlet = p[["Outlet_ID", "Distributor_ID"]].drop_duplicates(subset=["Outlet_ID"])
    dist_per_outlet["Province"] = dist_per_outlet["Distributor_ID"].map(config.DISTRIBUTOR_TO_PROVINCE)

    feats = (stats
             .merge(activity,        on="Outlet_ID")
             .merge(mcz,             on="Outlet_ID")
             .merge(jan_stats,       on="Outlet_ID")
             .merge(master_subset,   on="Outlet_ID", how="left")
             .merge(dist_per_outlet, on="Outlet_ID", how="left")
             .merge(coords[["Outlet_ID", "Latitude", "Longitude"]], on="Outlet_ID", how="left")
             .merge(poi.drop(columns=["Latitude", "Longitude"], errors="ignore"),
                    on="Outlet_ID", how="left"))

    if sku_mix is not None:
        feats = feats.merge(sku_mix, on="Outlet_ID", how="left")
        # Fill SKU mix nulls for outlets with no transactions (shouldn't happen but safe)
        for col in ["avg_price_per_liter", "mass_share", "mid_share",
                    "premium_share", "super_premium_share",
                    "sku_diversity", "top_sku_share"]:
            if col in feats.columns:
                feats[col] = feats[col].fillna(0)

    if competitors is not None:
        feats = feats.merge(competitors, on="Outlet_ID", how="left")
        for col in ["competitors_500m", "competitors_1km", "competitors_2km",
                    "same_type_competitors_500m", "same_type_competitors_1km",
                    "same_type_competitors_2km"]:
            if col in feats.columns:
                feats[col] = feats[col].fillna(0).astype(int)

    # Climate features (per-province January averages — beverages climate-sensitive)
    feats["climate_jan_temp_c"]    = feats["Province"].map(
        lambda p: config.PROVINCE_CLIMATE_JAN.get(p, {}).get("temp_c", 27.0))
    feats["climate_jan_humid_pct"] = feats["Province"].map(
        lambda p: config.PROVINCE_CLIMATE_JAN.get(p, {}).get("humidity_pct", 75))

    # Normalize POI scores and compute composite spatial demand signal
    poi_raw_cols = [
        "footfall_score",
        "school_score",
        "tourist_score",
        "health_score",
        "competitor_poi_score",
    ]
    for col in poi_raw_cols:
        if col in feats.columns:
            feats[col] = feats[col].fillna(0.0)
            max_val = float(feats[col].max()) if len(feats) else 0.0
            feats[f"{col}_norm"] = feats[col] / max_val if max_val > 0 else 0.0

    if "competitors_1km" in feats.columns:
        max_comp = float(feats["competitors_1km"].max()) if len(feats) else 0.0
        feats["competitor_density_norm"] = (
            feats["competitors_1km"] / max_comp if max_comp > 0 else 0.0
        )
        feats["is_isolated_market"] = (feats["competitors_1km"] < 3).astype(int)
        feats["is_dense_market"] = (feats["competitors_1km"] >= 15).astype(int)
    else:
        feats["competitor_density_norm"] = 0.0
        feats["is_isolated_market"] = 0
        feats["is_dense_market"] = 0

    foot = feats.get("footfall_score_norm", 0.0)
    school = feats.get("school_score_norm", 0.0)
    tourist = feats.get("tourist_score_norm", 0.0)
    health = feats.get("health_score_norm", 0.0)
    diversity = feats.get("poi_diversity_score", 0.0)
    feats["spatial_demand_score"] = (
        foot * 3.0 + school * 2.0 + tourist * 2.5 + health * 1.0 + diversity * 1.5
    ) / (3.0 + 2.0 + 2.5 + 1.0 + 1.5)

    print(f"  feature frame shape: {feats.shape}")
    return feats


def assign_poi_density_tier(feats: pd.DataFrame, q_cuts: tuple = (0.25, 0.5, 0.75)) -> pd.DataFrame:
    """Within each province, bucket outlets into POI-density quartiles using
    total POIs within 2km. This is the within-province percentile
    normalization that mitigates OSM rural sparsity bias.
    """
    total_col = "poi_total_2km"
    if total_col not in feats.columns:
        # fallback: sum all 2km columns
        cols = [c for c in feats.columns if c.endswith("_2km") and c.startswith("poi_")]
        feats[total_col] = feats[cols].sum(axis=1)

    # Compute per-province quantile cutoffs, then assign tier without
    # using groupby().apply() — avoids pandas 3.0+ grouping-column drop.
    feats = feats.copy()
    feats["poi_tier"] = 0
    for prov, idx in feats.groupby("Province").groups.items():
        sub = feats.loc[idx, total_col]
        if sub.nunique() <= 1:
            continue
        cuts = sub.quantile(list(q_cuts)).tolist()
        tier = pd.Series(0, index=idx)
        tier[sub > cuts[0]] = 1
        tier[sub > cuts[1]] = 2
        tier[sub > cuts[2]] = 3
        feats.loc[idx, "poi_tier"] = tier.values
    return feats


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def main() -> int:
    config.GOLD.mkdir(parents=True, exist_ok=True)

    # Load Silver layer
    print("\n== Loading silver layer ==")
    txns = pd.read_parquet(config.SILVER_CLEAN / "transactions_clean.parquet")
    master = pd.read_parquet(config.SILVER_CLEAN / "outlet_master_clean.parquet")
    coords = pd.read_parquet(config.SILVER_CLEAN / "outlet_coordinates_clean.parquet")
    season = pd.read_parquet(config.SILVER_CLEAN / "seasonality_clean.parquet")
    poi    = pd.read_parquet(config.SILVER_CLEAN / "poi_clean.parquet")
    print(f"  txns={txns.shape}  master={master.shape}  coords={coords.shape}  "
          f"season={season.shape}  poi={poi.shape}")

    outlets_with_coords = set(coords["Outlet_ID"]) & set(master["Outlet_ID"])
    print(f"  outlets with master AND coords: {len(outlets_with_coords):,}")

    # 1. Jan 2026 holidays
    print("\n== Writing Jan 2026 holidays ==")
    write_jan_2026_holidays()

    # 2. Outlet-month panel
    print("\n== Building outlet-month panel ==")
    panel = build_outlet_month_panel(txns, outlets_with_coords)
    panel = attach_distributor(panel, txns)
    panel = add_stockout_flag(panel)
    panel_out = config.GOLD / "outlet_month_panel.parquet"
    panel.to_parquet(panel_out, index=False)
    print(f"  -> {panel_out}")

    # 3. Forensics: stockouts, dead-then-resurrected (on panel)
    print("\n== Panel-level forensics ==")
    fx.detect_stockout_months(panel)
    fx.detect_dead_then_resurrected(panel, dormant_threshold=6)
    fx.write_findings()  # append to existing findings file

    # 4. Seasonality calibration + Jan-2026 extrapolation
    print("\n== Seasonality calibration ==")
    _, mult = calibrate_seasonality(panel, season)
    print(mult.to_string(index=False))
    extrapolate_jan_2026_seasonality(season)

    # 5. YoY growth
    print("\n== YoY growth ==")
    yoy = compute_yoy_growth(panel)
    print(yoy.to_string(index=False))

    # 6. SKU mix features (beverage-industry-specific)
    print("\n== Computing per-outlet SKU mix ==")
    sku_mix = compute_sku_mix(txns)
    print(f"  Per-outlet SKU mix: {sku_mix.shape}")
    print("  Tier share distribution (mean across outlets):")
    for col in ["mass_share", "mid_share", "premium_share", "super_premium_share"]:
        if col in sku_mix.columns:
            print(f"    {col}: {sku_mix[col].mean():.3f}")
    print(f"    avg_price_per_liter: {sku_mix['avg_price_per_liter'].mean():.2f} LKR")
    print(f"    sku_diversity (mean): {sku_mix['sku_diversity'].mean():.2f} of 10")

    # 7. Competitor density per outlet (BallTree on outlet coords)
    print("\n== Computing per-outlet competitor density ==")
    competitors = compute_competitor_density(coords, master)
    print(f"  Competitor density: {competitors.shape}")
    print(f"  Avg competitors within 500m / 1km / 2km: "
          f"{competitors.competitors_500m.mean():.1f} / "
          f"{competitors.competitors_1km.mean():.1f} / "
          f"{competitors.competitors_2km.mean():.1f}")

    # 8. Per-outlet features
    print("\n== Engineering per-outlet features ==")
    feats = build_outlet_features(panel, master, coords, poi, sku_mix=sku_mix,
                                   competitors=competitors)
    feats = assign_poi_density_tier(feats)

    feats_out = config.GOLD / "outlet_features.parquet"
    feats.to_parquet(feats_out, index=False)
    print(f"  -> {feats_out}  shape={feats.shape}")
    print(f"  columns: {feats.shape[1]} total")

    # 9. Compact POI feature frame for modeling / export
    poi_cols = [
        "Outlet_ID",
        "footfall_score",
        "school_score",
        "tourist_score",
        "health_score",
        "competitor_poi_score",
        "poi_diversity_score",
        "footfall_score_norm",
        "school_score_norm",
        "tourist_score_norm",
        "health_score_norm",
        "competitor_poi_score_norm",
        "spatial_demand_score",
        "competitor_density_norm",
        "is_isolated_market",
        "is_dense_market",
    ]
    poi_cols = [c for c in poi_cols if c in feats.columns]
    poi_out = feats.reindex(columns=poi_cols).copy().fillna(0.0)
    poi_out["internal_competitor_count"] = feats.get("competitors_1km", 0)
    poi_out_path = config.GOLD / "poi_features.csv"
    poi_out.to_csv(poi_out_path, index=False)
    print(f"  -> {poi_out_path}  rows={len(poi_out):,}")

    # Quick sanity print
    print("\nQuick feature sanity (first 3 outlets):")
    sample_cols = ["Outlet_ID", "Outlet_Type", "Outlet_Size", "Province",
                   "active_months", "monthly_volume_mean", "monthly_volume_q90",
                   "zero_months_count", "poi_tier", "jan_mean"]
    avail = [c for c in sample_cols if c in feats.columns]
    print(feats[avail].head(3).to_string(index=False))
    print("\nGold features: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
