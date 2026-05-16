"""End-to-end pipeline orchestrator.

Runs the data + modeling pipeline from raw ingest to final predictions:

  Phase 1  Bronze ingest (copy raw + sha256 manifest)
  Phase 2  Silver clean + forensics
  Phase 3  POI scraping (Overpass) + BallTree per-outlet counts
  Phase 4  Gold features (outlet-month panel + per-outlet features)
  Phase 5  Potential modeling (peer-Q90 + cross-check + validation)

Each phase's main() is invoked in order. Re-running is idempotent: bronze
overwrites with same bytes; silver wipes the quarantine summary; POI scraping
uses cached JSON; gold/model overwrite parquet outputs.

Usage:
    python -m src.run_pipeline
    # or
    python src/run_pipeline.py
"""
from __future__ import annotations

import sys
import time

from src import bronze_ingest, silver_clean, poi_scraper, gold_features
from src import potential_model


PHASES = [
    ("Bronze ingest",           bronze_ingest.main),
    ("Silver clean + forensics", silver_clean.main),
    ("POI scraping",            poi_scraper.main),
    ("Gold features",           gold_features.main),
    ("Potential modeling",      potential_model.main),
]


def main() -> int:
    total_start = time.time()
    for i, (label, fn) in enumerate(PHASES, 1):
        print("=" * 70)
        print(f"Phase {i}/{len(PHASES)}: {label}")
        print("=" * 70)
        t0 = time.time()
        rc = fn()
        elapsed = time.time() - t0
        if rc != 0:
            print(f"FAILED at {label} (rc={rc})", file=sys.stderr)
            return rc
        print(f"-- {label} OK ({elapsed:.1f}s)")
    print("=" * 70)
    print(f"Pipeline complete in {time.time() - total_start:.1f}s")
    print(f"Deliverable:  outputs/DataX_predictions.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
