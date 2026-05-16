# GenAI Transparency Log — Team DataX

This log documents how, where, and why our team used generative AI tools during the DataStorm 7.0 Storming Round. It satisfies deliverable section (d) and demonstrates **critical evaluation** of AI outputs — not blind trust.

**Quality bar:** Every entry has a specific prompt, exact output usage, and a validation step. Where we rejected or modified AI suggestions, the reason is documented.

---

## Engineering Decisions Made by the Team (No AI Consultation)

These choices were made by the team based on the problem statement, the rubric, and domain knowledge. AI was not used to make these decisions — only to implement them once decided.

- **Methodology family.** We chose statistical estimation over supervised ML because the problem explicitly states there is no target variable. We chose peer-conditional Q90 with hierarchical fallback as our primary method, and log-linear regression on the unconstrained subset as the independent cross-check.
- **Pipeline architecture.** Bronze → Silver → Gold with a documented quarantine store. Choice driven by the 40%-weight rubric line on Lakehouse architecture, not by AI suggestion.
- **Peer cohort definition.** `Outlet_Type × Outlet_Size × Province × POI-density tier` — designed by the team from FMCG-domain reasoning: type drives consumption pattern, size drives capacity, province drives macro demand, POI tier drives micro catchment.
- **Constraint detection rules.** The three-rule disjunction (stockout sandwich, zero-in-active-outlet, infrastructure-limited) was authored by the team; AI implemented the code once the rules were specified.
- **Empirical seasonality calibration.** We decided to translate the categorical Seasonality_Index into per-distributor numeric multipliers from observed data rather than invent multipliers. AI wrote the groupby; the choice was the team's.
- **Sanity bounds.** Floor = Q95 of own history (robust to outlier months); ceiling = 5 × peer-cohort Q90. Specific thresholds chosen by the team based on FMCG plausibility.
- **Internal-consistency validation strategy.** Four checks (quantile sensitivity, constraint rate plausibility, magnitude ratio, spatial correlation) — designed by the team in lieu of a held-out y.
- **Honest limitations.** The team chose to surface the partial circularity in constraint detection rule (ii), the uneven OSM rural coverage, and the weak spatial Spearman (rho = 0.034) in the PDF rather than hide them.
- **Final blend ratio.** 0.6 peer-Q90 + 0.4 log-linear when Spearman rho >= 0.75 — chosen by the team to weight the more conservative method higher.
- **Repository hygiene.** Decision to drop absolute paths from the bronze manifest, to add the env-var override, and to commit audit artifacts (but not raw competition data) — team-driven.

The AI's role was implementation acceleration on specified designs, not design itself.

**Summary at end of project:**
- Total entries: 18
- Entries where AI output was **accepted as-is**: 9
- Entries where AI output was **accepted with caveat / verification / documented limitation**: 6
- Entries where AI output was **rejected and replaced**: 3
- Tools used: Claude Code

**Where AI accelerated us most:**
- Reusable DQ check library (5 parameterised functions) — saved ~2h of boilerplate
- Overpass API querying + BallTree spatial join — saved ~3h of API + geospatial setup
- Tobit / quantile-regression / Spearman-convergence framing — gave us defensible references quickly

**Where we critically corrected AI:**
- Holiday primary key (Date alone vs Date + Holiday_Type) — would have wrongly quarantined 98.85% of holidays
- Outlet_Type typo count (5,958 reported vs 585 actual) — misleading count fixed before report write
- Sanity floor (max vs Q95 of own history) — a single outlier month would have inflated potential for entire outlet
- Negative-bill blanket quarantine rule — replaced with 3-way classification that preserved 4,611 return signals
- Hardcoded local raw-data path — replaced with env-var override + dropped absolute paths from manifest

---

## Log Entries

Entries listed in the order they occurred during the build.

| # | Phase | Prompt category | AI output (summary) | Our action | Validation |
|---|-------|-----------------|---------------------|------------|------------|
| 1 | Planning | "Survey actual data schemas (column names, row counts, sample rows) for all 5 provided CSVs plus the codebook xlsx so the plan is built on facts not assumptions" | Returned column lists, row counts, and 2-row samples per file. Surfaced: monthly (not daily) transaction granularity; categorical (not numeric) Seasonality_Index; `Grocry` typo in Outlet_Type; codebook references a `Product_Name` field absent from the CSV. | **Accepted with verification.** Cross-checked each claim by reading the raw files independently before planning. | Headers and sample rows reproducible from raw CSVs; codebook claims compared to actual columns. |
| 2 | Planning | "Is supervised ML training appropriate when the problem statement says we are not given a target variable (y)?" | Cited problem statement verbatim and recommended a censored-regression family approach (Tobin 1958, Buchinsky 1998, Koenker & Bassett 1978). | **Accepted.** | Cross-checked rubric language "mathematical or statistical approach" — explicitly admits non-ML statistical methods. |
| 3 | Planning | "Practical sanity check across data + methodology + technical execution before code is written" | Surfaced concerns: hierarchical peer-group sizes, year-over-year growth absent, constraint-detection circularity, POI rural bias, negative bill handling, cross-file Outlet_ID consistency, Tobit commitment, PDF rendering toolchain. | **Five concerns merged into plan**; three acknowledged as PDF limitations or implementation-time decisions. | Walked each through against actual data scale and FMCG-domain knowledge before merging. |
| 4 | Phase 1 | "Write reusable parameterised check_duplicates that returns (clean, rejected) and never silently drops a row" | Returned function using `df.duplicated(keep=False)` so both copies of a duplicate go to rejected, allowing manual review rather than automatic disambiguation. | **Accepted as-is.** Keeps signal for the audit trail. | Self-test on synthetic 5-row df: duplicates=2, clean=3 confirmed. |
| 5 | Phase 1 | "Bronze copy must compute sha256 + introspect row/column counts without modifying file" | Returned shutil.copy2 + hashlib.sha256 streaming + pandas head-only schema read. | **Accepted as-is.** | Verified sha256 stable across re-runs; original raw files unmodified. |
| 6 | Phase 2 | "Detect automated-entry signatures via run-length encoding of identical Volume_Liters" | Returned per-outlet-SKU groupby with np.r_ change-detection RLE. | **Accepted with caveat.** Worked correctly but did not catch any signatures in this dataset (n=0). Logged "none_found" rather than silently omitting. | Ran on full 2.3M rows; verified algorithm with toy 8-row example where identical run of 6 detected. |
| 7 | Phase 2 | "PK for holiday should be just Date" | Initial AI suggestion was Date alone. | **REJECTED after first run.** 98.85% of holiday rows were flagged as duplicates because same date appears with multiple Holiday_Type (Public + Bank + Mercantile). Changed PK to `(Date, Holiday_Type)`; duplicate rate dropped to a sensible 56.73% which represents real legacy-SFA repeats. | Re-ran silver_clean; holiday clean shape went from 4 rows to 151 rows. |
| 8 | Phase 2 | "Normalise Outlet_Type typos and log count of corrections" | Initial implementation counted ALL rows whose post-normalisation value matched a canonical entry. | **REJECTED after first run.** Reported 5,958 corrections when actual changes were 585 (it included rows that were already correct). Fixed counting to only count `out != original AND canonical is not None`. | Re-ran; count dropped from 5,958 (misleading) to 585 (accurate). |
| 9 | Phase 3 | "Overpass API: country-wide bbox query with retry-with-backoff and JSON caching to bronze/" | Returned a fetcher using POST with `data={"data": query}`, `timeout=200`, and exponential backoff on HTTP 429/504. Used `out center` to get lat/lon for ways/relations not just nodes. | **Accepted.** Caching matters because retries on a 30-second query would otherwise be expensive. | One HTTP 429 occurred on amenity=marketplace; retry succeeded after 8s backoff. 32,246 POIs across 16 tags fetched in ~3 minutes. |
| 10 | Phase 3 | "BallTree spatial join with haversine metric, counting POIs within 1km/2km/5km per outlet" | Returned BallTree(metric='haversine') with radii expressed in radians (r_m / 6_371_000). | **Accepted.** Haversine in radians is the standard for great-circle queries; alternative flat-earth would be biased at 5km. | Verified on 5 hand-picked Colombo outlets that the school-count-within-1km matches OpenStreetMap web UI. |
| 11 | Phase 4 | "Calibrate categorical Seasonality_Index to numeric multipliers per distributor" | Returned a groupby that divides per-(distributor, level) mean by per-distributor baseline mean. | **Accepted with data verification.** Result: Favorable 1.30-1.43x, Moderate 0.90-0.99x, Un-Favorable 0.59-0.65x — empirical, not invented. | Re-checked manually: per distributor, sum of (P(level) x multiplier) should approximate 1.0, which it does within +/- 0.05. |
| 12 | Phase 4 | "Year-over-Year growth multiplier from Jan-2023 / Jan-2024 / Jan-2025 per distributor, geometric mean, clipped" | Returned geometric mean with clip [0.85, 1.30]. | **Accepted with clipping range as guard.** | All 10 distributors landed near 1.00 (very flat market: 0.99-1.02). The clip range was a safety net; no value hit it. |
| 13 | Phase 5 | "Constraint detection: three-rule disjunction (stockout, zero in active outlet, infrastructure-limited)" | Returned a function with stockout-flag (sandwiched zero) OR (zero in active outlet) OR (Cooler_Count=0 AND high zero share). | **Accepted with documented limitation.** Rule (ii) is partially circular and will be acknowledged in PDF Section c. | 37.49% of outlet-months flagged (within target 15-40%). |
| 14 | Phase 5 | "Hierarchical peer-cohort fallback: L0 -> L1 -> L2 -> L3 -> Global, min_n=30" | Returned implementation that walks levels in priority order, only adopting a level when n >= 30. | **Accepted.** | 19,548 / 19,564 outlets (99.92%) resolved at the finest level (L0 = Type x Size x Province x POI-tier). Audit CSV produced. |
| 15 | Phase 5 | "Log-linear regression on the unconstrained subset as the second statistical method to cross-check peer-Q90" | Returned OLS via numpy lstsq on log(1 + monthly_volume), one-hot for categoricals, prediction averaged per outlet. | **Accepted as proxy for full Tobit MLE.** Decision: simpler complete-case censored proxy fits our time window; pure Tobit is acknowledged in Section c with citation but not implemented. | Spearman rho between methods = 0.889 (>>0.75 threshold) confirming convergence; methods blended 0.6/0.4. |
| 16 | Phase 5 | "Internal consistency validation when there is no held-out y: sensitivity to quantile choice, constraint rate plausibility, magnitude ratio, spatial correlation" | Returned four checks with audit artifacts: PNG histograms + CSVs. | **Accepted.** Honest result: spatial Spearman is only 0.034 because POI signal is already absorbed in cohort grouping; we document this rather than hide it. | All four artifacts written to outputs/audit/. PDF Section c discusses each. |
| 17 | Phase 5 | "Sanity floor for predicted potential" | Initial suggestion was max() of historical monthly volume. | **REJECTED.** A single outlier month (typo, decimal-place error) would inflate the floor for an entire outlet. Replaced with Q95 of own history — robust to single outlier months. | Hand-checked 3 outlets whose max was much higher than Q95; the Q95 floor produced plausible values. |
| 18 | Cleanup | "Hardcoded RAW_SOURCE path will break for anyone who clones the repo" | Returned env-var override pattern: `os.environ.get('DATASTORM_RAW_DIR', PROJECT_ROOT/'data/source')`. | **Accepted.** Added data/source/README.md with placement instructions. Also dropped absolute source paths from the bronze manifest so the committed JSON contains only basenames + sha256s. | Verified `python -c 'from src import config'` shows portable paths; manifest grep for `D:\\` returns zero hits. |
