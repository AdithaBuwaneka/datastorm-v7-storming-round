# Outlet Intelligence — Team DataX

End-to-end decision-support system for the **January 2026 Maximum Monthly
Purchase Potential** of 20,000 traditional-trade beverage outlets in Sri
Lanka, plus the trade-marketing tools that act on those numbers.

The problem has **no target variable**: the observed monthly volume is the
censored minimum of true demand and systemic constraints (credit, stockout,
cooler capacity, delivery cap). The repository contains a 12-phase pipeline
that uncaps that latent demand, a budget optimiser that turns predictions
into a concrete LKR allocation, and a web application that lets a sales
manager browse, filter, and ask an LLM to explain any outlet on the network.

## Highlights

- 5-method censored-demand ensemble (peer-Q90 anchor + log-linear + Tobit
  MLE + half-normal SFA + Phase-3 business formula) with hold-out Spearman
  rho ≈ 0.79 over ~11,200 outlets.
- 9-category Gaussian / gravity distance-decay POI scoring over 43,000 OSM
  POIs, plus HHI, Voronoi-style territory radius, and type-weighted
  competition pressure.
- Concave water-filling LP allocates LKR 4,999,955.90 of trade spend
  across 8,989 Western Province outlets, split into discount /
  merchandising / promotional channels.
- Per-outlet SHAP attribution + monotone-constrained counterfactuals
  (add a cooler, remove competition) feeding a Gemini 2.5 Flash narrative.
- Dormancy-risk classifier (5-fold CV AUC ≈ 0.879) for sales-rep
  early warning, distributor scorecard, HDBSCAN sales territories,
  and a per-outlet Top-100 cooler ROI ranking.
- Next.js 14 + FastAPI web app with paginated outlet browser, drill-
  down with AI explanation, and a tabbed insights workspace.

## Architecture

```
data/
├── source/      Raw competition CSVs (placed by user; NOT committed)
├── bronze/      Immutable copies + sha256 manifest (cross-file integrity)
├── silver/
│   ├── clean/   DQ-passed datasets (parquet)
│   └── quarantine/  Rejected rows with documented `_rejection_reason`
└── gold/        Outlet-month panel, per-outlet feature frame, SHAP values,
                 counterfactuals, dormancy scores, action cards, clusters

src/             Canonical 12-phase Python pipeline
notebooks/       00_demo_end_to_end.ipynb (EDA + pipeline walk-through)
outputs/         DataX_predictions.csv + DataX_budget_allocations.csv +
                 ~35 audit artifacts (CSV + PNG)
report/          Technical paper + executive pitch deck
docs/            genai_log.md
webapp/
├── backend/     FastAPI service: 18 endpoints + Gemini XAI
└── frontend/    Next.js 14 + Tailwind + shadcn-style UI
```

## Prerequisites

- Python 3.10 or newer
- Node.js 20 or newer + npm (web app only)
- pip
- A Google Gemini API key, free tier works (web app XAI endpoint only) —
  get one at <https://aistudio.google.com/app/apikey>

## Setup

### 1. Clone

```bash
git clone https://github.com/AdithaBuwaneka/datastorm-v7-storming-round.git
cd datastorm-v7-storming-round
```

### 2. Python environment

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
source .venv/bin/activate       # bash / Linux / macOS

pip install -r requirements.txt
```

### 3. Raw data

Place the six raw files from the dataset into `data/source/`:

```
data/source/
├── transactions_history_final.csv
├── outlet_master.csv
├── outlet_coordinates.csv
├── distributor_seasonality_details.csv
├── holiday_list.csv
└── dataset_description.xlsx
```

`data/source/*` is gitignored — raw data is never committed.

## Run the pipeline

```bash
python -m src.run_pipeline
```

Twelve phases run end to end. Each is idempotent and can also be invoked
alone:

```bash
python -m src.bronze_ingest        # 1.  Copy raw + sha256 manifest
python -m src.silver_clean         # 2.  DQ checks + forensics + quarantine
python -m src.poi_scraper          # 3.  Overpass POI fetch + BallTree join
python -m src.gold_features        # 4.  Outlet-month panel + 229 features
python -m src.potential_model      # 5.  5-method ensemble + predictions
python -m src.budget_optimization  # 6.  LKR 5M Western Province LP
python -m src.xai_attribution      # 7.  XGBoost surrogate + SHAP + counterfactuals
python -m src.cooler_roi           # 8.  Per-outlet cooler deployment business case
python -m src.outlet_actions       # 9.  Top-3 prescriptive interventions
python -m src.dormancy_risk        # 10. XGBoost dormancy classifier
python -m src.distributor_scorecard # 11. 10-distributor benchmark
python -m src.spatial_clusters     # 12. HDBSCAN sub-province territories
```

## Run the web app

The web app reads the parquet and audit CSVs produced by the pipeline, so
run the pipeline at least once first.

### Backend (FastAPI on :8000)

```bash
cd webapp/backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=<your_key>
python -m uvicorn main:app --port 8000
```

Confirm by opening <http://127.0.0.1:8000/health>.

### Frontend (Next.js on :3000)

In a second terminal:

```bash
cd webapp/frontend
npm install
npm run dev
```

Open <http://localhost:3000>. The frontend defaults to the backend at
`http://127.0.0.1:8000`; override with `NEXT_PUBLIC_API_BASE`.

Web app routes:

| Route | Purpose |
|---|---|
| `/` | Dashboard — KPI tiles, province breakdown, quick links |
| `/outlets` | Paginated browser of all 20,000 outlets with filters and sort |
| `/outlets/[id]` | Drill-down with SHAP drivers, counterfactual deltas, recommended actions, cooler ROI, and a Gemini-generated narrative |
| `/insights?view=budget` | LKR 5M Western Province allocation: tiles, distributor bars, channel split, top outlets |
| `/insights?view=cooler-roi` | Top-100 cooler deployment with NPV, payback, greenfield flag |
| `/insights?view=dormancy` | Risk bands + top-200 at-risk outlets |
| `/insights?view=scorecard` | 10-distributor health scorecard |
| `/insights?view=territories` | HDBSCAN territories on an interactive Leaflet map |
| `/insights?view=forensics` | Beyond-DQ forensic findings table |

More setup detail at [`webapp/README.md`](webapp/README.md).

## Deliverables

| # | Path | Description |
|---|---|---|
| 1 | `outputs/DataX_predictions.csv` | 20,000 × 2 (Outlet_ID, Maximum_Monthly_Liters) |
| 2 | `outputs/DataX_budget_allocations.csv` | 8,989 × 2 (Outlet_ID, Trade_Spend_LKR) — Western Province |
| 3 | this repository | Bronze→Silver→Gold pipeline + business modules + web app |
| 4 | `webapp/` | Next.js + FastAPI app with Gemini-powered XAI per outlet |
| 5 | `report/` | Technical paper |
| 6 | `report/` | Executive pitch deck |

Audit artifacts produced by the pipeline live under `outputs/audit/` and
`data/gold/`. Notable files:

| File | Content |
|---|---|
| `outputs/audit/method_convergence.csv` | Pairwise Spearman of all five methods |
| `outputs/audit/holdout_validation_jan2025.csv` | Hold-out Jan 2025 evaluation |
| `outputs/audit/cooler_roi_top100.csv` | Top-100 outlets ranked by 24-month NPV |
| `outputs/audit/dormancy_top200_at_risk.csv` | Sales-rep intervention shortlist |
| `outputs/audit/budget_allocation_by_channel.csv` | Per-outlet discount / merch / promo split |
| `outputs/audit/distributor_scorecard.csv` | 10-distributor benchmark |
| `outputs/audit/territory_clusters_summary.csv` | 96 HDBSCAN sales territories |
| `outputs/audit/shap_top_drivers_per_outlet.csv` | Top-5 +/- SHAP drivers per outlet |
| `outputs/audit/forensics_findings.csv` | Beyond-DQ findings with treatment |
| `data/bronze/_manifest.json` | sha256 + row counts of the six raw files |

## Methodology summary

1. **Constraint detection** per outlet-month: four OR-combined rules
   (stockout sandwich, zero-in-active outlet, no-cooler + high-zero,
   no-cooler + low-volume below own Q90/3).
2. **Peer-conditional Q90 ceiling** with hierarchical fallback
   (Type × Size × Province × POI-tier → … → Global; min 30 unconstrained
   observations per cohort).
3. **Base potential** = `max(own Q90 of unconstrained months, peer Q90)`.
4. **January 2026 projection** = base × distributor seasonality × YoY
   growth × holiday multiplier (consistent `nunique(Date)` counting on
   both sides).
5. **Sanity bounds** — floor = own Q95, ceiling = 5 × peer Q99.
6. **Phase-3 business-formula benchmark** — auditable cross-check using
   historical peak (Q95), outlet type / size multipliers, January
   seasonality, holiday multiplier, distance-decay POI lift, and
   competitor drag.
7. **Three independent parametric cross-checks**
   - Log-linear regression on the unconstrained subset (ρ vs peer ≈ 0.86)
   - Tobit Type I MLE, right-censored at observed when constrained
     (ρ vs peer ≈ 0.84; ρ vs log-linear ≈ 0.92)
   - Aigner–Lovell–Schmidt half-normal SFA
     (ρ vs peer ≈ 0.85)
8. **Five-method ensemble** when all pairwise Spearman ≥ 0.75:
   `final = 0.40 peer + 0.18 log-linear + 0.18 Tobit + 0.16 SFA + 0.08 Phase-3`.
9. **Hold-out validation** — re-fit on 2023 + 2024 only, predict
   January 2025 unconstrained values, compare. Spearman ≈ 0.79.
10. **Spatial features** — Gaussian decay for 8 demand-driver POI
    categories, gravity decay for competitor POIs, plus HHI,
    Voronoi-style territory radius and type-weighted competition.
11. **Replenishment friction** = `stockout_flag_sum / active_months`
    proxies the cooler-replenishment-cycle constraint.
12. **Business-decision modules** — cooler-deployment ROI, top-3 action
    cards per outlet, dormancy-risk classifier, distributor scorecard,
    HDBSCAN territories.
13. **XAI** — XGBoost surrogate of the ensemble (Spearman ≈ 0.97 vs
    ensemble) feeds TreeExplainer for per-outlet SHAP attribution and
    two monotone-constrained counterfactuals (add a cooler, remove
    competition). The structured payload is rendered into a
    business-friendly narrative by Gemini 2.5 Flash inside the web app.

## Reproducibility

- Bronze sha256 manifest verifies raw bytes were not modified between runs.
- All randomness is seeded (`random_state = 42`).
- Tobit and SFA MLE use deterministic row samples (300k and 120k
  respectively) so re-runs produce identical estimates.
- POI scraping caches Overpass JSON in `data/bronze/poi_raw/`; re-runs
  are network-free unless the cache is cleared.
- Parquet for intermediate storage, CSV for final deliverables.
- One config file (`src/config.py`) is the source of truth for paths,
  POI categories, decay parameters, ensemble weights, etc.

## Key numbers

| Metric | Value |
|---|---|
| Raw transactions ingested | 2,376,389 |
| Rows quarantined with reason | 73,285 (3.08%) |
| Outlets recovered via Lat/Lon swap fix | 200 |
| Outlet_Type typos normalised | 979 (Bakry, Grocry, " Eatery ", Eatry) |
| Outlets surviving Silver | 19,960 (20,000 master ∩ coordinates − rejects) |
| OpenStreetMap POIs scraped | 43,023 across 36 tag combinations / 9 categories |
| Engineered features per outlet | 229 |
| Constraint-detection rules | 4 (OR-combined) |
| Statistical methods cross-checked | 5 |
| Pairwise method Spearman | all ≥ 0.83 |
| Hold-out Spearman (Jan 2025 from 2023-24) | 0.794 (n = 11,256) |
| LKR 5M budget actually allocated | 4,999,955.90 across 8,803 funded outlets |
| Channel split | Discount 35% / Merchandising 42% / Promotional 23% |
| Cooler Top-100 24-month margin uplift | LKR 33,629,125 (net 28,629,125 of LKR 5M capex) |
| Cooler Top-100 median payback | 3.6 months |
| Dormancy classifier 5-fold CV AUC | 0.879 ± 0.006 |
| HDBSCAN sub-province territories | 96 |
| Predicted potential (median / mean) | 175.0 L / 307.2 L per outlet-month |

## Repository layout in detail

```
src/
├── bronze_ingest.py            sha256 + cross-file integrity
├── silver_clean.py             6 reusable DQ checks + apply_check wrapper
├── dq_checks.py                check_duplicates, check_nulls, check_referential_integrity,
│                                check_value_range, check_format, check_value_set
├── forensics.py                Beyond-DQ findings (typo map, Lat/Lon swap, size inference, ...)
├── poi_scraper.py              Overpass bbox queries + BallTree haversine join
├── competition_features.py     HHI / territory radius / type-weighted pressure
├── gold_features.py            229-column outlet feature frame
├── potential_model.py          5-method ensemble + hold-out + audit artifacts
├── budget_optimization.py      Concave water-fill LP + channel split + sensitivity sweep
├── xai_attribution.py          XGBoost surrogate + SHAP + counterfactuals
├── cooler_roi.py               LKR 50k cooler business case + Top-100 NPV ranking
├── outlet_actions.py           Top-3 prescriptive interventions per outlet
├── dormancy_risk.py            Lapse classifier + Top-200 at-risk list
├── distributor_scorecard.py    10-distributor benchmark + composite health
├── spatial_clusters.py         HDBSCAN sub-province territories
├── run_pipeline.py             12-phase orchestrator
└── config.py                   single source of truth

webapp/
├── backend/
│   ├── main.py                 FastAPI app + CORS + lifespan-loaded cache
│   ├── services/
│   │   ├── data_loader.py      In-memory cache of gold parquets + audit CSVs
│   │   └── gemini_xai.py       Gemini 2.5 Flash wrapper
│   └── routers/                outlets, dashboards, xai
└── frontend/
    ├── app/                    Dashboard, /outlets, /outlets/[id], /insights
    ├── components/             Card, Button, Badge, KpiTile, PaginationBar, NavSidebar
    └── lib/                    api.ts, types.ts, utils.ts
```

## License & acknowledgements

Code is internal competition work for Team DataX. POI data is © OpenStreetMap
contributors (ODbL). Sri Lankan public-holiday dates are curated from
public government calendars.
