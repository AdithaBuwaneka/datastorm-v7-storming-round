"""Silver layer: run DQ checks + forensics on each Bronze dataset.

Outputs:
  data/silver/clean/{dataset}_clean.parquet  — cleaned data
  data/silver/quarantine/{dataset}_rejected.parquet — rejected rows + reasons
  data/silver/quarantine/_quarantine_summary.csv — per-check counts
  outputs/audit/forensics_findings.{md,csv}  — legacy-SFA findings
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src import dq_checks as dq
from src import forensics as fx


def _ensure_dirs() -> None:
    config.SILVER_CLEAN.mkdir(parents=True, exist_ok=True)
    config.QUARANTINE.mkdir(parents=True, exist_ok=True)
    config.AUDIT.mkdir(parents=True, exist_ok=True)
    # Wipe any prior summary so we don't double-count across re-runs.
    summary_path = config.QUARANTINE / "_quarantine_summary.csv"
    if summary_path.exists():
        summary_path.unlink()


# ---------------------------------------------------------------------------
# Per-dataset cleaning
# ---------------------------------------------------------------------------

def clean_outlet_master() -> pd.DataFrame:
    print("\n== outlet_master.csv ==")
    df = pd.read_csv(config.BRONZE / "outlet_master.csv")
    df["Outlet_ID"] = df["Outlet_ID"].astype(str).str.strip()

    df = dq.apply_check(dq.check_duplicates, df, ["Outlet_ID"],
                        dataset_name="outlet_master", check_name="duplicates_PK")
    df = dq.apply_check(dq.check_nulls, df,
                        ["Outlet_ID", "Outlet_Size", "Cooler_Count", "Outlet_Type"],
                        dataset_name="outlet_master", check_name="nulls_mandatory")
    df = dq.apply_check(dq.check_value_set, df, "Outlet_Size",
                        config.VALID_OUTLET_SIZES,
                        dataset_name="outlet_master", check_name="outlet_size_value_set",
                        case_insensitive=True)

    # Cooler_Count integer coercion: quarantine non-integer rows
    coerced = pd.to_numeric(df["Cooler_Count"], errors="coerce")
    bad = coerced.isna()
    if bad.any():
        rejected = df.loc[bad].copy()
        rejected["_rejection_reason"] = "Cooler_Count not integer-coercible"
        rejected["_check_name"] = "cooler_count_type"
        rejected["_dataset"] = "outlet_master"
        dq.persist_rejected(rejected, "outlet_master")
        dq.update_quarantine_summary("outlet_master", "cooler_count_type",
                                     len(df), int(bad.sum()))
        df = df.loc[~bad].copy()
    df["Cooler_Count"] = coerced[~bad].astype(int)

    # Forensic: normalize Outlet_Type typos ("Grocry" -> "Grocery", etc.)
    df = fx.normalise_outlet_type(df, "Outlet_Type")

    out = config.SILVER_CLEAN / "outlet_master_clean.parquet"
    df.to_parquet(out, index=False)
    print(f"  -> {out}  shape={df.shape}")
    return df


def clean_outlet_coordinates(master_ids: set[str]) -> pd.DataFrame:
    print("\n== outlet_coordinates.csv ==")
    df = pd.read_csv(config.BRONZE / "outlet_coordinates.csv")
    df["Outlet_ID"] = df["Outlet_ID"].astype(str).str.strip()

    df = dq.apply_check(dq.check_duplicates, df, ["Outlet_ID"],
                        dataset_name="outlet_coordinates", check_name="duplicates_PK")
    df = dq.apply_check(dq.check_nulls, df, ["Outlet_ID", "Latitude", "Longitude"],
                        dataset_name="outlet_coordinates", check_name="nulls_mandatory")
    df = dq.apply_check(dq.check_referential_integrity, df, "Outlet_ID", master_ids,
                        dataset_name="outlet_coordinates", check_name="ref_outlet_master")

    # ------------------------------------------------------------------------
    # Recover swapped Latitude/Longitude before bbox quarantine.
    # ~240 outlets in the raw data have Lat / Lon transposed (e.g., Lat=79.9,
    # Lon=7.1 — clearly Sri Lankan magnitudes but wrong columns). Swapping
    # restores them to the SL bbox. Genuine GPS errors like (0, 0) are NOT
    # recoverable and fall through to the range check.
    # ------------------------------------------------------------------------
    lat_in_sl = df["Latitude"].between(*config.SL_LAT_BOUNDS)
    lon_in_sl = df["Longitude"].between(*config.SL_LON_BOUNDS)
    # Candidate-for-swap: lat is in Lon range AND lon is in Lat range
    lat_looks_like_lon = df["Latitude"].between(*config.SL_LON_BOUNDS)
    lon_looks_like_lat = df["Longitude"].between(*config.SL_LAT_BOUNDS)
    swap_mask = (~lat_in_sl) & (~lon_in_sl) & lat_looks_like_lon & lon_looks_like_lat
    n_swapped = int(swap_mask.sum())
    if n_swapped:
        print(f"  RECOVERY: swapping Lat/Lon for {n_swapped} outlets "
              f"(Lat/Lon were transposed in source).")
        new_lat = df["Latitude"].copy()
        new_lon = df["Longitude"].copy()
        new_lat[swap_mask] = df.loc[swap_mask, "Longitude"].values
        new_lon[swap_mask] = df.loc[swap_mask, "Latitude"].values
        df["Latitude"]  = new_lat
        df["Longitude"] = new_lon

        # Persist a forensic CSV of the recovery actions
        config.AUDIT.mkdir(parents=True, exist_ok=True)
        df.loc[swap_mask, ["Outlet_ID", "Latitude", "Longitude"]] \
          .to_csv(config.AUDIT / "coords_swapped_recovered.csv", index=False)
        # Log to forensics
        fx._log(
            "Lat/Lon swapped values recovered",
            count=n_swapped,
            examples=df.loc[swap_mask, "Outlet_ID"].head(5).tolist(),
            treatment="cleaned",
            detail="Source had Latitude and Longitude column values transposed. "
                   "Swap was deterministic and recoverable (both values land in "
                   "Sri Lanka after swap). 1.2% of outlets reclaimed.",
        )

    df = dq.apply_check(dq.check_value_range, df, "Latitude",
                        min_val=config.SL_LAT_BOUNDS[0], max_val=config.SL_LAT_BOUNDS[1],
                        dataset_name="outlet_coordinates", check_name="lat_range_SL")
    df = dq.apply_check(dq.check_value_range, df, "Longitude",
                        min_val=config.SL_LON_BOUNDS[0], max_val=config.SL_LON_BOUNDS[1],
                        dataset_name="outlet_coordinates", check_name="lon_range_SL")

    out = config.SILVER_CLEAN / "outlet_coordinates_clean.parquet"
    df.to_parquet(out, index=False)
    print(f"  -> {out}  shape={df.shape}")
    return df


def clean_seasonality() -> pd.DataFrame:
    print("\n== distributor_seasonality_details.csv ==")
    df = pd.read_csv(config.BRONZE / "distributor_seasonality_details.csv")
    df["Distributor_ID"] = df["Distributor_ID"].astype(str).str.strip()
    df["Seasonality_Index"] = df["Seasonality_Index"].astype(str).str.strip()

    df = dq.apply_check(dq.check_duplicates, df,
                        ["Distributor_ID", "Year", "Month"],
                        dataset_name="seasonality", check_name="duplicates_PK")
    df = dq.apply_check(dq.check_nulls, df,
                        ["Distributor_ID", "Year", "Month", "Seasonality_Index"],
                        dataset_name="seasonality", check_name="nulls_mandatory")
    df = dq.apply_check(dq.check_referential_integrity, df, "Distributor_ID",
                        config.VALID_DISTRIBUTOR_IDS,
                        dataset_name="seasonality", check_name="ref_distributor")
    df = dq.apply_check(dq.check_value_set, df, "Seasonality_Index",
                        config.VALID_SEASONALITY,
                        dataset_name="seasonality", check_name="index_value_set")
    df = dq.apply_check(dq.check_value_range, df, "Month",
                        min_val=1, max_val=12,
                        dataset_name="seasonality", check_name="month_range")
    df = dq.apply_check(dq.check_value_range, df, "Year",
                        min_val=2023, max_val=2025,
                        dataset_name="seasonality", check_name="year_range")

    # Completeness: expect 10 * 3 * 12 = 360 rows
    expected = len(config.VALID_DISTRIBUTOR_IDS) * 3 * 12
    if len(df) != expected:
        print(f"  WARN: completeness expected {expected}, got {len(df)} "
              f"(diff={len(df)-expected})")

    out = config.SILVER_CLEAN / "seasonality_clean.parquet"
    df.to_parquet(out, index=False)
    print(f"  -> {out}  shape={df.shape}")
    return df


def clean_holidays() -> pd.DataFrame:
    print("\n== holiday_list.csv ==")
    df = pd.read_csv(config.BRONZE / "holiday_list.csv")
    df["Holiday_Type"] = df["Holiday_Type"].astype(str).str.strip()

    # Parse ISO 8601 with timezone
    df["Date_parsed"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
    bad_date = df["Date_parsed"].isna() & df["Date"].notna()
    if bad_date.any():
        rejected = df.loc[bad_date].copy()
        rejected["_rejection_reason"] = "Unparseable Date"
        rejected["_check_name"] = "date_iso8601_parse"
        rejected["_dataset"] = "holiday"
        dq.persist_rejected(rejected, "holiday")
        dq.update_quarantine_summary("holiday", "date_iso8601_parse",
                                     len(df), int(bad_date.sum()))
        df = df.loc[~bad_date].copy()
    df["Date"] = df["Date_parsed"].dt.tz_convert(None).dt.normalize()
    df = df.drop(columns=["Date_parsed"])

    df = dq.apply_check(dq.check_duplicates, df, ["Date", "Holiday_Type"],
                        dataset_name="holiday", check_name="duplicates_PK")
    df = dq.apply_check(dq.check_nulls, df, ["Date", "Holiday_Name"],
                        dataset_name="holiday", check_name="nulls_mandatory")
    df = dq.apply_check(dq.check_value_set, df, "Holiday_Type",
                        config.VALID_HOLIDAY_TYPES,
                        dataset_name="holiday", check_name="type_value_set",
                        case_insensitive=False)

    out = config.SILVER_CLEAN / "holiday_clean.parquet"
    df.to_parquet(out, index=False)
    print(f"  -> {out}  shape={df.shape}")
    return df


def clean_transactions(master_ids: set[str]) -> pd.DataFrame:
    print("\n== transactions_history_final.csv ==")
    df = pd.read_csv(config.BRONZE / "transactions_history_final.csv")
    print(f"  loaded shape={df.shape}")
    df["Outlet_ID"]      = df["Outlet_ID"].astype(str).str.strip()
    df["Distributor_ID"] = df["Distributor_ID"].astype(str).str.strip()
    df["SKU_ID"]         = df["SKU_ID"].astype(str).str.strip()

    df = dq.apply_check(dq.check_duplicates, df,
                        ["Outlet_ID", "Year", "Month", "SKU_ID"],
                        dataset_name="transactions", check_name="duplicates_PK")
    df = dq.apply_check(dq.check_nulls, df,
                        ["Outlet_ID", "Year", "Month", "Distributor_ID",
                         "SKU_ID", "Volume_Liters"],
                        dataset_name="transactions", check_name="nulls_mandatory")
    df = dq.apply_check(dq.check_referential_integrity, df, "Outlet_ID", master_ids,
                        dataset_name="transactions", check_name="ref_outlet_master")
    df = dq.apply_check(dq.check_referential_integrity, df, "Distributor_ID",
                        config.VALID_DISTRIBUTOR_IDS,
                        dataset_name="transactions", check_name="ref_distributor")
    df = dq.apply_check(dq.check_value_range, df, "Year",
                        min_val=2023, max_val=2025,
                        dataset_name="transactions", check_name="year_range")
    df = dq.apply_check(dq.check_value_range, df, "Month",
                        min_val=1, max_val=12,
                        dataset_name="transactions", check_name="month_range")

    # Forensics: 3-way classify negative/zero values BEFORE blanket range check
    df = fx.classify_negative_or_zero_values(df)

    # Quarantine impossible combinations (data_error + null_row)
    bad_tag = df["txn_tag"].isin({"data_error", "null_row"})
    if bad_tag.any():
        rejected = df.loc[bad_tag].copy()
        rejected["_rejection_reason"] = "txn_tag=" + rejected["txn_tag"]
        rejected["_check_name"] = "txn_value_classification"
        rejected["_dataset"] = "transactions"
        dq.persist_rejected(rejected, "transactions")
        dq.update_quarantine_summary("transactions", "txn_value_classification",
                                     len(df), int(bad_tag.sum()))
        df = df.loc[~bad_tag].copy()

    # Per-SKU outlier quarantine (Q99.5 x 5)
    q995 = df.groupby("SKU_ID")["Volume_Liters"].transform(lambda s: s.abs().quantile(0.995))
    outlier_mask = df["Volume_Liters"].abs() > 5 * q995
    if outlier_mask.any():
        rejected = df.loc[outlier_mask].copy()
        rejected["_rejection_reason"] = "Volume > 5x SKU Q99.5 (likely typo)"
        rejected["_check_name"] = "per_sku_volume_outlier"
        rejected["_dataset"] = "transactions"
        dq.persist_rejected(rejected, "transactions")
        dq.update_quarantine_summary("transactions", "per_sku_volume_outlier",
                                     len(df), int(outlier_mask.sum()))
        df = df.loc[~outlier_mask].copy()

    out = config.SILVER_CLEAN / "transactions_clean.parquet"
    df.to_parquet(out, index=False)
    print(f"  -> {out}  shape={df.shape}")
    return df


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def main() -> int:
    _ensure_dirs()

    # Bronze manifest produces the cross-file findings we want to log first.
    manifest_path = config.BRONZE / "_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        fx.record_cross_file_findings(
            manifest.get("outlet_id_cross_file_findings", {})
        )

    # 1. Outlet master first — needed for referential checks on everything else
    master_df = clean_outlet_master()
    master_ids = set(master_df["Outlet_ID"].astype(str))

    # 2. Outlet coordinates
    clean_outlet_coordinates(master_ids)

    # 3. Seasonality
    clean_seasonality()

    # 4. Holidays
    clean_holidays()

    # 5. Transactions (largest; SKU mix etc.)
    txn_df = clean_transactions(master_ids)

    # Forensics: codebook mismatches
    fx.check_codebook_mismatches(txn_df.columns.tolist())

    # Forensics: automated-entry signatures + per-SKU outliers already logged
    fx.detect_automated_entries(txn_df, min_repeats=6)

    # Persist all forensic findings
    fx.write_findings()

    print("\nSilver clean: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
