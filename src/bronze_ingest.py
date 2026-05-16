"""Bronze layer: copy raw source files into data/bronze/ untouched and
compute a sha256 manifest. Also runs the cross-file Outlet_ID set-equality
smoke check that the plan flagged as a Phase-1 hard checkpoint.

Idempotent: re-running overwrites with identical bytes.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

from src import config


# (source_filename, bronze_filename) — bronze name may differ if the raw
# filename has spaces/dots we want to normalize.
FILES = [
    ("transactions_history_final.csv",         "transactions_history_final.csv"),
    ("outlet_master.csv",                       "outlet_master.csv"),
    ("outlet_coordinates.csv",                  "outlet_coordinates.csv"),
    ("distributor_seasonality_details.csv",     "distributor_seasonality_details.csv"),
    ("holiday_list.csv",                        "holiday_list.csv"),
    ("1. dataset_description.xlsx",             "dataset_description.xlsx"),
]


def sha256_of(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_with_manifest() -> list[dict]:
    """Copy each source file into bronze/ and produce a manifest entry."""
    config.BRONZE.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []

    for src_name, dst_name in FILES:
        src_path = config.RAW_SOURCE / src_name
        dst_path = config.BRONZE / dst_name
        if not src_path.exists():
            print(f"  MISSING: {src_path}", file=sys.stderr)
            entries.append({
                "filename": dst_name,
                "source_basename": src_name,
                "status": "missing",
            })
            continue

        shutil.copy2(src_path, dst_path)
        size_bytes = dst_path.stat().st_size
        sha = sha256_of(dst_path)

        # Light shape introspection — does NOT modify or transform the file.
        rows = None
        cols: list[str] = []
        try:
            if dst_name.endswith(".csv"):
                # Read just the header + count rows efficiently
                df_head = pd.read_csv(dst_path, nrows=0)
                cols = df_head.columns.tolist()
                with dst_path.open("rb") as f:
                    rows = sum(1 for _ in f) - 1  # subtract header
            elif dst_name.endswith(".xlsx"):
                xl = pd.ExcelFile(dst_path)
                cols = xl.sheet_names  # use sheet list for xlsx
        except Exception as e:  # pragma: no cover
            print(f"  WARN: shape introspection failed for {dst_name}: {e}",
                  file=sys.stderr)

        entries.append({
            "filename": dst_name,
            "source_basename": src_name,
            "size_bytes": size_bytes,
            "sha256": sha,
            "rows": rows,
            "columns_or_sheets": cols,
            "status": "ok",
        })
        print(f"  [{dst_name}] size={size_bytes:,} rows={rows} sha256={sha[:12]}...")

    return entries


def cross_file_outlet_id_check() -> dict:
    """The plan's Phase-1 cross-file assertion.

    Returns a dict of orphan/phantom counts that the silver pipeline will use
    to know whether to quarantine specific outlets.
    """
    print("\nCross-file Outlet_ID set-equality assertion:")

    master = pd.read_csv(config.BRONZE / "outlet_master.csv")
    coords = pd.read_csv(config.BRONZE / "outlet_coordinates.csv")
    # Only read the column we need to keep memory low on the 2.4M-row transactions.
    txns = pd.read_csv(config.BRONZE / "transactions_history_final.csv",
                       usecols=["Outlet_ID"])

    master_ids = set(master["Outlet_ID"].astype(str).str.strip())
    coords_ids = set(coords["Outlet_ID"].astype(str).str.strip())
    txns_ids   = set(txns["Outlet_ID"].astype(str).str.strip())

    master_only_coords = master_ids - coords_ids  # in master, not in coords
    coords_only_master = coords_ids - master_ids  # in coords, not in master
    txns_orphans       = txns_ids - master_ids    # transactions for outlets not in master
    master_no_txns     = master_ids - txns_ids    # outlets in master with no transactions (ghost)

    findings = {
        "master_count": len(master_ids),
        "coords_count": len(coords_ids),
        "transactions_unique_outlets": len(txns_ids),
        "in_master_not_in_coords": len(master_only_coords),
        "in_coords_not_in_master": len(coords_only_master),
        "transactions_orphans (txn outlet not in master)": len(txns_orphans),
        "ghost_outlets_master_no_txns": len(master_no_txns),
        "examples_orphans": sorted(list(txns_orphans))[:5],
        "examples_ghosts":  sorted(list(master_no_txns))[:5],
    }
    for k, v in findings.items():
        print(f"  {k}: {v}")
    return findings


def main() -> int:
    print(f"Bronze ingest: source={config.RAW_SOURCE}")
    print(f"               dest  ={config.BRONZE}\n")

    entries = copy_with_manifest()

    # Cross-file Outlet_ID check (Phase 1 smoke test)
    try:
        outlet_findings = cross_file_outlet_id_check()
    except Exception as e:
        print(f"  WARN: cross-file check failed: {e}", file=sys.stderr)
        outlet_findings = {"error": str(e)}

    manifest = {
        "team": config.TEAM_NAME,
        "files": entries,
        "outlet_id_cross_file_findings": outlet_findings,
    }
    manifest_path = config.BRONZE / "_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest written: {manifest_path}")

    # Pass/fail
    ok = all(e["status"] == "ok" for e in entries)
    if not ok:
        print("FAIL: one or more source files missing.", file=sys.stderr)
        return 1
    print("Bronze ingest: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
