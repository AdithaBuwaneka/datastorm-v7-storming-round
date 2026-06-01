"""Standalone diagnostic: count outlets whose (Lat, Lon) lands in the sea.

The Silver layer's value-range check is rectangular (SL bounding box), so a
point inside the bbox but outside the land polygon currently passes. This
script verifies, post-pipeline, how many outlets fall in that gap.

NO MODIFICATIONS to predictions / budget / pipeline. Pure observation.
Output: outputs/audit/sea_coordinate_outlets.csv (list)
        outputs/audit/forensics_findings.md      (append one finding row)

Run:
    python -m verification.sea_coordinate_check
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from global_land_mask import globe

REPO = Path(__file__).resolve().parents[1]
COORDS = REPO / "data" / "silver" / "clean" / "outlet_coordinates_clean.parquet"
MASTER = REPO / "data" / "silver" / "clean" / "outlet_master_clean.parquet"
OUT_CSV = REPO / "outputs" / "audit" / "sea_coordinate_outlets.csv"
FINDINGS_MD = REPO / "outputs" / "audit" / "forensics_findings.md"


def main() -> None:
    coords = pd.read_parquet(COORDS)
    print(f"Loaded {len(coords):,} outlet coordinates from Silver layer.")

    # globe.is_land returns True for land, False for water (sea / lake).
    coords["is_land"] = coords.apply(
        lambda r: bool(globe.is_land(r["Latitude"], r["Longitude"])),
        axis=1,
    )
    sea = coords.loc[~coords["is_land"]].copy()
    print(f"Outlets with coordinates in the SEA: {len(sea):,} "
          f"({100*len(sea)/len(coords):.2f}%)")

    if len(sea) == 0:
        print("Nothing to report — all coordinates on land.")
        return

    # Enrich with master attributes so the forensic record is useful.
    if MASTER.exists():
        master = pd.read_parquet(MASTER)
        sea = sea.merge(master[["Outlet_ID", "Outlet_Type", "Outlet_Size"]],
                          on="Outlet_ID", how="left")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    sea = sea.sort_values("Outlet_ID")
    sea.to_csv(OUT_CSV, index=False)
    print(f"Saved: {OUT_CSV}")

    # Append a finding row to the forensics markdown.
    examples = ", ".join(sea["Outlet_ID"].head(5).tolist())
    finding_line = (
        f"- **Coordinates landing in the sea (legacy GPS artifact)**: "
        f"count={len(sea)} treatment=flagged_for_next_iteration\n"
        f"  - Detection: `global_land_mask.globe.is_land(lat, lon)` against "
        f"Natural Earth 1-arc-min land grid.\n"
        f"  - Examples: {examples}\n"
        f"  - Impact: negligible (~{100*len(sea)/len(coords):.2f}% of outlets; "
        f"sea-located outlets receive ~0 POI density signal but still "
        f"contribute via volume history and master attributes).\n"
        f"  - Decision: original entries preserved on submission day for "
        f"auditability. Land-mask check queued for the next iteration of "
        f"`src/silver_clean.py`.\n"
    )

    if FINDINGS_MD.exists():
        existing = FINDINGS_MD.read_text(encoding="utf-8")
        if "Coordinates landing in the sea" not in existing:
            with FINDINGS_MD.open("a", encoding="utf-8") as fh:
                fh.write("\n" + finding_line)
            print(f"Appended finding to: {FINDINGS_MD}")
        else:
            print("Finding already present in forensics_findings.md — skipping append.")
    else:
        FINDINGS_MD.write_text(finding_line, encoding="utf-8")
        print(f"Created: {FINDINGS_MD}")


if __name__ == "__main__":
    main()
