"""End-to-end pipeline orchestrator.

Runs the data + modeling pipeline from raw ingest to final predictions
and business analytics:

  Phase 1  Bronze ingest (copy raw + sha256 manifest)
  Phase 2  Silver clean + forensics
  Phase 3  POI scraping (Overpass) + BallTree per-outlet counts
  Phase 4  Gold features (outlet-month panel + per-outlet features)
  Phase 5  Potential modeling (peer-Q90 + cross-check + validation)
  Phase 6  Western Province trade-spend allocation (LKR 5M)
  Phase 7  Feature attribution (SHAP surrogate) + counterfactuals
  Phase 8  Cooler-deployment ROI analytics
  Phase 9  Outlet action cards
  Phase 10 Dormancy-risk early warning
  Phase 11 Distributor scorecard
  Phase 12 Geographic territory clustering (HDBSCAN)

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
from src import potential_model, budget_optimization
from src import xai_attribution, cooler_roi, outlet_actions, dormancy_risk
from src import distributor_scorecard, spatial_clusters


def _wrap(fn):
    """Modules with main() returning None: coerce to 0 for the orchestrator."""
    def runner():
        rc = fn()
        return 0 if rc is None else rc
    return runner


PHASES = [
    ("Bronze ingest",                         bronze_ingest.main),
    ("Silver clean + forensics",              silver_clean.main),
    ("POI scraping",                          poi_scraper.main),
    ("Gold features",                         gold_features.main),
    ("Potential modeling",                    potential_model.main),
    ("Budget allocation (Western Province)",  _wrap(budget_optimization.main)),
    ("XAI attribution + counterfactuals",     _wrap(xai_attribution.main)),
    ("Cooler-deployment ROI",                 _wrap(cooler_roi.main)),
    ("Outlet action cards",                   _wrap(outlet_actions.main)),
    ("Dormancy-risk early warning",           _wrap(dormancy_risk.main)),
    ("Distributor scorecard",                 _wrap(distributor_scorecard.main)),
    ("Geographic territory clustering",       _wrap(spatial_clusters.main)),
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
    print(f"Outputs:")
    print(f"  outputs/DataX_predictions.csv")
    print(f"  outputs/DataX_budget_allocations.csv")
    print(f"  outputs/audit/cooler_roi_top100.csv")
    print(f"  outputs/audit/outlet_actions_top3.csv")
    print(f"  outputs/audit/dormancy_top200_at_risk.csv")
    print(f"  outputs/audit/distributor_scorecard.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
