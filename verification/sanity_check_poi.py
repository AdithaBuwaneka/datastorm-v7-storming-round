import pandas as pd
import numpy as np


def main() -> int:
    gold = pd.read_csv("data/gold/poi_features.csv")
    outlets = pd.read_parquet("data/silver/clean/outlet_coordinates_clean.parquet")
    full = gold.merge(outlets, on="Outlet_ID", how="left")

    # CHECK 1: Urban vs rural split
    # Colombo area outlets (Lat 6.8-7.0, Lon 79.8-80.0) should have
    # higher footfall and competitor density than rural Central province
    colombo = full[(full.Latitude.between(6.8, 7.0)) & (full.Longitude.between(79.8, 80.0))]
    rural = full[(full.Latitude.between(7.2, 8.0)) & (full.Longitude.between(80.4, 81.0))]
    competitor_col = (
        "competitor_count_500m"
        if "competitor_count_500m" in full.columns
        else "internal_competitor_count"
    )

    print("=== Urban vs Rural Sanity Check ===")
    print(f"Colombo avg footfall_score: {colombo['footfall_score'].mean():.4f}")
    print(f"Rural avg footfall_score:   {rural['footfall_score'].mean():.4f}")
    print(f"Colombo avg {competitor_col}: {colombo[competitor_col].mean():.1f}")
    print(f"Rural avg {competitor_col}:   {rural[competitor_col].mean():.1f}")

    # CHECK 2: Southern province should show higher tourist scores
    # Lat 5.9-6.4, Lon 79.9-81.5 (Galle, Matara, Mirissa area)
    southern = full[(full.Latitude.between(5.9, 6.4))]
    non_southern = full[(full.Latitude > 7.0)]
    print("\n=== Southern Tourist Score Check ===")
    print(f"Southern avg tourist_score:     {southern['tourist_score'].mean():.4f}")
    print(f"Non-southern avg tourist_score: {non_southern['tourist_score'].mean():.4f}")

    # CHECK 3: No outlet should have both near-zero competitor density
    # AND near-zero POI scores in Western Province (that would be suspicious)
    western = full[(full.Latitude.between(6.0, 7.5)) & (full.Longitude.between(79.8, 80.2))]
    completely_empty = western[
        (western["footfall_score"] == 0)
        & (western[competitor_col] == 0)
        & (western["school_score"] == 0)
    ]
    print(f"\nWestern province outlets with ALL zero spatial scores: {len(completely_empty)}")
    print("(Some is OK for isolated outlets, but >10% suggests a scraping problem)")

    # CHECK 4: Distribution of scores (should not be all zeros or all max)
    print("\n=== Score Distributions ===")
    for col in ["footfall_score", "school_score", "tourist_score", "competitor_poi_score"]:
        pct_zero = (full[col] == 0).mean() * 100
        print(f"{col}: mean={full[col].mean():.4f}, %zero={pct_zero:.1f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
