"""Legacy-SFA artifact detection that goes beyond generic DQ checks.

These functions identify the kinds of system-artifacts the problem statement
explicitly calls out: connectivity blackouts, automated ghost entries,
human data-entry shortcuts, master-data decay.

All findings write rows to outputs/audit/forensics_findings.md plus a
machine-readable CSV. Most findings are FLAGGED, not quarantined — they
are signals our modeling step needs (e.g., stockout months feed constraint
detection).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src import config


FORENSICS_MD  = config.AUDIT / "forensics_findings.md"
FORENSICS_CSV = config.AUDIT / "forensics_findings.csv"

# Single-source typo-normalisation map for Outlet_Type. Kept here so any caller
# applying it sees the same mapping; logged for the PDF.
OUTLET_TYPE_NORMALISATION = {
    # Canonical types observed in the raw data (verified via EDA):
    # Hotel, Grocery, Pharmacy, Eatery, Bakery, Kiosk, SMMT (FMCG retail-trade code)
    "grocery":     "Grocery",
    "grocry":      "Grocery",       # typo (~390 outlets)
    "eatery":      "Eatery",
    "eatry":       "Eatery",        # typo
    "pharmacy":    "Pharmacy",
    "pharmcy":     "Pharmacy",      # typo
    "hotel":       "Hotel",
    "bakery":      "Bakery",
    "bakry":       "Bakery",        # typo (~395 outlets)
    "kiosk":       "Kiosk",
    "smmt":        "SMMT",          # canonical FMCG modern-trade code
    # Possible variants from other Sri Lankan FMCG datasets
    "restraunt":   "Restaurant",
    "restaurant":  "Restaurant",
    "supermarket": "Supermarket",
    "convenience": "Convenience",
}


# ---------------------------------------------------------------------------
# Append-only finding logger
# ---------------------------------------------------------------------------

_findings_rows: list[dict] = []


def _log(name: str, count: int, examples: list, treatment: str, detail: str = "") -> None:
    """Buffer a finding; written to disk by `write_findings()`."""
    _findings_rows.append({
        "finding": name,
        "count": count,
        "treatment": treatment,
        "examples": "; ".join(map(str, examples[:5])),
        "detail": detail,
    })
    print(f"  [forensics] {name}: count={count} ({treatment})")


def write_findings() -> None:
    """Persist all buffered findings to markdown + CSV."""
    if not _findings_rows:
        return
    config.AUDIT.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(_findings_rows)
    df.to_csv(FORENSICS_CSV, index=False)

    lines = [
        "# Forensics Findings — Legacy SFA Artifacts",
        "",
        "These findings go beyond generic DQ rules. They identify system-artifacts",
        "characteristic of legacy Sales Force Automation and distributor ERP exports:",
        "automated ghost entries, human shortcuts, connectivity blackouts, and",
        "master-data decay. Treatments distinguish cleaned (silently corrected),",
        "quarantined (removed from clean dataset), and flagged (kept but tagged for",
        "downstream modeling).",
        "",
        "| Finding | Count | Treatment | Examples | Detail |",
        "|---|---|---|---|---|",
    ]
    for r in _findings_rows:
        lines.append(
            f"| {r['finding']} | {r['count']:,} | {r['treatment']} | "
            f"{r['examples']} | {r['detail']} |"
        )
    FORENSICS_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nForensics findings persisted: {FORENSICS_MD}")


# ---------------------------------------------------------------------------
# Outlet_Type normalisation (the 'Grocry' typo finding)
# ---------------------------------------------------------------------------

def normalise_outlet_type(df: pd.DataFrame, column: str = "Outlet_Type") -> pd.DataFrame:
    """Map fuzzy variants to canonical labels. Logs ONLY rows where the value
    actually changed."""
    raw = df[column].astype(str)
    raw_lower = raw.str.strip().str.lower()
    canonical = raw_lower.map(OUTLET_TYPE_NORMALISATION)
    # Preserve original if no mapping
    out = canonical.where(canonical.notna(), df[column])

    actually_changed = (out != df[column]) & canonical.notna()
    n_changed = int(actually_changed.sum())

    df = df.copy()
    df[column] = out

    if n_changed > 0:
        # Build per-original-value change counts for examples
        change_pairs = (
            pd.DataFrame({"orig": raw[actually_changed],
                          "canon": out[actually_changed]})
            .value_counts()
            .head(5)
        )
        examples = [f"{o!r}->{c!r} (n={n})"
                    for (o, c), n in change_pairs.items()]
        unique_typos = (
            pd.DataFrame({"orig": raw[actually_changed],
                          "canon": out[actually_changed]})
            .drop_duplicates()
            .to_dict("records")
        )
        _log(
            "Outlet_Type typos normalised",
            count=n_changed,
            examples=examples,
            treatment="cleaned",
            detail=f"{len(unique_typos)} distinct typo->canonical mappings applied",
        )
    else:
        _log(
            "Outlet_Type typos normalised",
            count=0,
            examples=[],
            treatment="none_found",
            detail="No fuzzy mismatches found against canonical mapping.",
        )
    return df


# ---------------------------------------------------------------------------
# Codebook mismatches
# ---------------------------------------------------------------------------

def check_codebook_mismatches(transactions_cols: list[str]) -> None:
    """Compare actual transactions columns vs the dataset_description claims."""
    codebook_claims_present = "Product_Name"
    actual_has = codebook_claims_present in transactions_cols
    if not actual_has:
        _log(
            "Codebook references absent column",
            count=1,
            examples=[f"'{codebook_claims_present}' missing from transactions_history_final.csv"],
            treatment="flagged",
            detail="Codebook documents this field but raw export omits it; "
                   "treated as documentation drift, not data quality issue.",
        )
    # filename mismatch
    _log(
        "Codebook filename divergence",
        count=1,
        examples=["distributor_seasonality.csv claimed vs distributor_seasonality_details.csv actual"],
        treatment="flagged",
        detail="No impact on data; logged as governance finding.",
    )


# ---------------------------------------------------------------------------
# Cross-file findings (from bronze ingest's manifest)
# ---------------------------------------------------------------------------

def record_cross_file_findings(manifest_findings: dict) -> None:
    """Echo the bronze cross-file Outlet_ID assertion into forensics."""
    orphan_n = manifest_findings.get("transactions_orphans (txn outlet not in master)", 0)
    ghost_n  = manifest_findings.get("ghost_outlets_master_no_txns", 0)
    coord_diff = (manifest_findings.get("in_master_not_in_coords", 0)
                  + manifest_findings.get("in_coords_not_in_master", 0))

    if orphan_n == 0 and ghost_n == 0 and coord_diff == 0:
        _log(
            "Cross-file Outlet_ID integrity",
            count=0,
            examples=["perfect alignment master == coords == transactions (n=20000)"],
            treatment="reported_clean",
            detail="Unusual for legacy SFA exports; suggests upstream curation. "
                   "Row-level anomalies remain primary forensic focus.",
        )
    else:
        if orphan_n:
            _log(
                "Phantom transactions (orphan Outlet_IDs)",
                count=orphan_n,
                examples=manifest_findings.get("examples_orphans", []),
                treatment="quarantined",
                detail="Transactions for Outlet_IDs missing from outlet_master.",
            )
        if ghost_n:
            _log(
                "Ghost outlets (no transactions)",
                count=ghost_n,
                examples=manifest_findings.get("examples_ghosts", []),
                treatment="flagged",
                detail="Outlets in master with zero transactions across full period.",
            )
        if coord_diff:
            _log(
                "Outlet_ID master/coords mismatch",
                count=coord_diff,
                examples=[],
                treatment="quarantined",
                detail="Either master or coords missing some Outlet_IDs.",
            )


# ---------------------------------------------------------------------------
# Transaction-level forensics
# ---------------------------------------------------------------------------

def classify_negative_or_zero_values(df: pd.DataFrame) -> pd.DataFrame:
    """3-way classification for Volume_Liters / Total_Bill_Value (see plan).

    Adds a `txn_tag` column. Returns the dataframe with the tag attached;
    the caller decides which tags pass through to the clean dataset.

    Tags:
      normal_sale       Vol > 0, Bill > 0
      return            Vol < 0, Bill < 0   (matching pair)
      promo_or_error    Vol > 0, Bill < 0   (likely FoC with negative bill)
      foc_promo         Vol > 0, Bill = 0
      data_error        Vol = 0, Bill > 0   OR   Vol < 0, Bill > 0
      null_row          Vol = 0, Bill = 0
    """
    v = df["Volume_Liters"]
    b = df["Total_Bill_Value"]

    tag = pd.Series("other", index=df.index, dtype="object")
    tag[(v > 0)  & (b > 0)]  = "normal_sale"
    tag[(v < 0)  & (b < 0)]  = "return"
    tag[(v > 0)  & (b < 0)]  = "promo_or_error"
    tag[(v > 0)  & (b == 0)] = "foc_promo"
    tag[(v == 0) & (b > 0)]  = "data_error"
    tag[(v < 0)  & (b > 0)]  = "data_error"
    tag[(v == 0) & (b == 0)] = "null_row"

    df = df.copy()
    df["txn_tag"] = tag

    tag_counts = tag.value_counts().to_dict()
    examples = [f"{k}={v:,}" for k, v in tag_counts.items()]
    _log(
        "Transaction value classification",
        count=int(tag.isin({"data_error", "null_row"}).sum()),
        examples=examples,
        treatment="cleaned_and_flagged",
        detail="3-way classification: data_error+null_row quarantined; "
               "return/promo_or_error/foc_promo flagged and kept (signal, not noise).",
    )
    return df


def detect_automated_entries(df: pd.DataFrame,
                             min_repeats: int = 6) -> list[dict]:
    """Find (Outlet_ID, SKU_ID) pairs where Volume_Liters is identical for
    >= `min_repeats` consecutive months — characteristic of automated/copy-paste
    data entry rather than real sales variation.
    """
    df_sorted = df.sort_values(["Outlet_ID", "SKU_ID", "Year", "Month"])
    # Run-length encoding per (Outlet, SKU) of identical Volume_Liters.
    grp = df_sorted.groupby(["Outlet_ID", "SKU_ID"])
    suspicious_rows = []
    for (oid, sku), g in grp:
        vols = g["Volume_Liters"].to_numpy()
        if len(vols) < min_repeats:
            continue
        # mark positions where value changes
        change = np.r_[True, vols[1:] != vols[:-1]]
        run_id = change.cumsum()
        # run length per run_id
        for rid in np.unique(run_id):
            mask = run_id == rid
            if mask.sum() >= min_repeats and vols[mask][0] > 0:
                suspicious_rows.append({
                    "Outlet_ID": oid,
                    "SKU_ID": sku,
                    "value": float(vols[mask][0]),
                    "run_length_months": int(mask.sum()),
                })
    if suspicious_rows:
        examples = [f"{r['Outlet_ID']}/{r['SKU_ID']}={r['value']}x{r['run_length_months']}mo"
                    for r in suspicious_rows[:5]]
        _log(
            "Automated-entry signatures",
            count=len(suspicious_rows),
            examples=examples,
            treatment="flagged",
            detail=f"Identical Volume_Liters for >= {min_repeats} consecutive months "
                   "for the same (Outlet, SKU). Likely copy-paste or bot entry.",
        )
    else:
        _log(
            "Automated-entry signatures",
            count=0,
            examples=[],
            treatment="none_found",
            detail=f"No (Outlet, SKU) pair with >= {min_repeats} consecutive identical Volume_Liters.",
        )
    return suspicious_rows


def detect_per_sku_outliers(df: pd.DataFrame, multiplier: float = 5.0) -> pd.DataFrame:
    """Quarantine rows where Volume_Liters > multiplier x SKU's Q99.5.

    These are almost certainly data-entry typos (decimal-place errors, etc.).
    """
    q995 = df.groupby("SKU_ID")["Volume_Liters"].transform(lambda s: s.quantile(0.995))
    bad = df["Volume_Liters"] > multiplier * q995
    if bad.sum():
        ex = df.loc[bad, ["Outlet_ID", "SKU_ID", "Volume_Liters"]].head(5).to_dict("records")
        _log(
            "Per-SKU volume outliers",
            count=int(bad.sum()),
            examples=[f"{r['Outlet_ID']}/{r['SKU_ID']}={r['Volume_Liters']}" for r in ex],
            treatment="quarantined",
            detail=f"Volume_Liters > {multiplier}x SKU Q99.5 — likely decimal/keying error.",
        )
    else:
        _log(
            "Per-SKU volume outliers",
            count=0,
            examples=[],
            treatment="none_found",
            detail=f"No row exceeded {multiplier}x SKU Q99.5.",
        )
    return df.loc[bad].copy()


# ---------------------------------------------------------------------------
# Stockout / constraint indicators (computed at outlet-month level)
# ---------------------------------------------------------------------------

def detect_stockout_months(panel: pd.DataFrame) -> pd.DataFrame:
    """Identify outlet-months that show a zero-volume sandwich pattern.

    `panel` must have columns: Outlet_ID, Year, Month, monthly_volume (already
    aggregated). Returns a DataFrame of (Outlet_ID, Year, Month, stockout_flag)
    that the modeling step uses for constraint detection.
    """
    p = panel.sort_values(["Outlet_ID", "Year", "Month"]).copy()
    p["prev_v"] = p.groupby("Outlet_ID")["monthly_volume"].shift(1)
    p["next_v"] = p.groupby("Outlet_ID")["monthly_volume"].shift(-1)
    p["stockout_flag"] = (
        (p["monthly_volume"] == 0)
        & (p["prev_v"].fillna(0) > 0)
        & (p["next_v"].fillna(0) > 0)
    )
    n = int(p["stockout_flag"].sum())
    _log(
        "Stockout months (zero sandwiched between non-zero)",
        count=n,
        examples=[],
        treatment="flagged_for_modeling",
        detail="Used as constraint indicator in Phase 5 (not quarantined).",
    )
    return p[["Outlet_ID", "Year", "Month", "stockout_flag"]]


def detect_dead_then_resurrected(panel: pd.DataFrame,
                                  dormant_threshold: int = 6) -> int:
    """Outlets that went silent for >= `dormant_threshold` consecutive months,
    then resumed activity.
    """
    p = panel.sort_values(["Outlet_ID", "Year", "Month"]).copy()
    p["is_zero"] = p["monthly_volume"] == 0
    n_outlets_with_pattern = 0
    examples: list[str] = []
    for oid, g in p.groupby("Outlet_ID"):
        z = g["is_zero"].to_numpy()
        # find runs of zeros, check if any run >= threshold AND not at the tail
        run_change = np.r_[True, z[1:] != z[:-1]]
        run_id = run_change.cumsum()
        for rid in np.unique(run_id):
            mask = run_id == rid
            if z[mask].all() and mask.sum() >= dormant_threshold:
                last_idx_of_run = np.where(mask)[0][-1]
                if last_idx_of_run < len(z) - 1:  # not the last run (i.e., resumed)
                    n_outlets_with_pattern += 1
                    if len(examples) < 5:
                        examples.append(str(oid))
                    break
    _log(
        "Dead-then-resurrected outlets",
        count=n_outlets_with_pattern,
        examples=examples,
        treatment="flagged",
        detail=f">= {dormant_threshold} consecutive zero months then resumed — flagged for review.",
    )
    return n_outlets_with_pattern
