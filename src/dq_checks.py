"""Reusable, parameterizable Data Quality checks for the Silver layer.

Each check returns (clean_df, rejected_df) where rejected_df has an extra
`_rejection_reason` column. No row is silently dropped.

The `apply_check` wrapper persists rejected rows to a per-dataset quarantine
parquet and updates the quarantine summary CSV.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from src import config


REJECTION_COL = "_rejection_reason"
QUARANTINE_SUMMARY = config.QUARANTINE / "_quarantine_summary.csv"


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_duplicates(df: pd.DataFrame,
                     primary_keys: list[str],
                     dataset_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Flag rows with duplicate values across `primary_keys`.

    Both copies of a duplicate are kept in rejected (keep=False) so a reviewer
    can manually decide which to retain rather than us silently picking one.
    """
    missing = [c for c in primary_keys if c not in df.columns]
    if missing:
        raise KeyError(f"[{dataset_name}] primary_keys missing from df: {missing}")

    dup_mask = df.duplicated(subset=primary_keys, keep=False)
    clean = df.loc[~dup_mask].copy()
    rejected = df.loc[dup_mask].copy()
    if not rejected.empty:
        rejected[REJECTION_COL] = f"Duplicate on PK={primary_keys}"
    return clean, rejected


def check_nulls(df: pd.DataFrame,
                mandatory_columns: list[str],
                dataset_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reject rows where any mandatory column is null or empty string."""
    missing = [c for c in mandatory_columns if c not in df.columns]
    if missing:
        raise KeyError(f"[{dataset_name}] mandatory_columns missing from df: {missing}")

    rej_reasons = pd.Series("", index=df.index)
    for col in mandatory_columns:
        col_is_null = df[col].isna()
        if df[col].dtype == "object":
            col_is_null = col_is_null | (df[col].astype(str).str.strip() == "")
        rej_reasons = rej_reasons.where(~col_is_null,
                                        rej_reasons + f"Null/empty in {col}; ")

    bad = rej_reasons.str.len() > 0
    clean = df.loc[~bad].copy()
    rejected = df.loc[bad].copy()
    if not rejected.empty:
        rejected[REJECTION_COL] = rej_reasons[bad].str.rstrip("; ")
    return clean, rejected


def check_referential_integrity(df: pd.DataFrame,
                                fk_column: str,
                                valid_values: Iterable,
                                dataset_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reject rows whose `fk_column` value is not in `valid_values`."""
    if fk_column not in df.columns:
        raise KeyError(f"[{dataset_name}] fk_column '{fk_column}' missing")
    valid_set = set(valid_values)
    bad = ~df[fk_column].isin(valid_set)
    clean = df.loc[~bad].copy()
    rejected = df.loc[bad].copy()
    if not rejected.empty:
        rejected[REJECTION_COL] = f"{fk_column} not in reference set"
    return clean, rejected


def check_value_range(df: pd.DataFrame,
                      column: str,
                      min_val=None,
                      max_val=None,
                      dataset_name: str = "",
                      inclusive: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reject rows where `column` falls outside [min_val, max_val]."""
    if column not in df.columns:
        raise KeyError(f"[{dataset_name}] column '{column}' missing")
    numeric = pd.to_numeric(df[column], errors="coerce")
    bad = pd.Series(False, index=df.index)
    if min_val is not None:
        bad |= numeric < min_val if inclusive else numeric <= min_val
    if max_val is not None:
        bad |= numeric > max_val if inclusive else numeric >= max_val
    # also reject rows that could not be parsed as numeric
    bad |= numeric.isna() & df[column].notna()
    clean = df.loc[~bad].copy()
    rejected = df.loc[bad].copy()
    if not rejected.empty:
        rejected[REJECTION_COL] = (
            f"{column} outside [{min_val}, {max_val}] (inclusive={inclusive})"
        )
    return clean, rejected


def check_format(df: pd.DataFrame,
                 column: str,
                 validator,
                 dataset_name: str = "",
                 format_label: str = "") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reject rows whose `column` value fails `validator`.

    `validator` may be:
      - a compiled regex (uses .fullmatch)
      - a string regex (compiled internally, fullmatch)
      - a callable returning bool
    """
    if column not in df.columns:
        raise KeyError(f"[{dataset_name}] column '{column}' missing")

    if isinstance(validator, str):
        pattern = re.compile(validator)
        is_ok = df[column].astype(str).map(lambda v: bool(pattern.fullmatch(v)))
    elif isinstance(validator, re.Pattern):
        is_ok = df[column].astype(str).map(lambda v: bool(validator.fullmatch(v)))
    elif callable(validator):
        is_ok = df[column].map(validator)
    else:
        raise TypeError("validator must be regex (str/Pattern) or callable")

    bad = ~is_ok.fillna(False)
    clean = df.loc[~bad].copy()
    rejected = df.loc[bad].copy()
    if not rejected.empty:
        label = format_label or "format"
        rejected[REJECTION_COL] = f"Invalid {label} in {column}"
    return clean, rejected


def check_value_set(df: pd.DataFrame,
                    column: str,
                    valid_values: Iterable,
                    dataset_name: str = "",
                    case_insensitive: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reject rows where `column` value is not in `valid_values`.

    A convenience that pairs with referential check but for fixed value sets
    (e.g., Outlet_Size, Holiday_Type). Listed as part of the format-check family.
    """
    if column not in df.columns:
        raise KeyError(f"[{dataset_name}] column '{column}' missing")
    valid_set = set(valid_values)
    if case_insensitive:
        lower_valid = {v.lower() for v in valid_set if isinstance(v, str)}
        col_vals = df[column].astype(str).str.lower()
        bad = ~col_vals.isin(lower_valid)
    else:
        bad = ~df[column].isin(valid_set)
    clean = df.loc[~bad].copy()
    rejected = df.loc[bad].copy()
    if not rejected.empty:
        rejected[REJECTION_COL] = f"{column} not in allowed value set"
    return clean, rejected


# ---------------------------------------------------------------------------
# Quarantine persistence + summary
# ---------------------------------------------------------------------------

def persist_rejected(rejected: pd.DataFrame, dataset_name: str) -> None:
    """Append rejected rows to the dataset's quarantine parquet."""
    if rejected.empty:
        return
    config.QUARANTINE.mkdir(parents=True, exist_ok=True)
    path = config.QUARANTINE / f"{dataset_name}_rejected.parquet"
    if path.exists():
        existing = pd.read_parquet(path)
        combined = pd.concat([existing, rejected], ignore_index=True)
    else:
        combined = rejected
    combined.to_parquet(path, index=False)


def update_quarantine_summary(dataset_name: str,
                              check_name: str,
                              total_in: int,
                              n_rejected: int) -> None:
    """Append one row to the quarantine summary CSV."""
    config.QUARANTINE.mkdir(parents=True, exist_ok=True)
    row = pd.DataFrame([{
        "dataset": dataset_name,
        "check": check_name,
        "total_in": total_in,
        "rejected": n_rejected,
        "passed": total_in - n_rejected,
    }])
    if QUARANTINE_SUMMARY.exists():
        existing = pd.read_csv(QUARANTINE_SUMMARY)
        row = pd.concat([existing, row], ignore_index=True)
    row.to_csv(QUARANTINE_SUMMARY, index=False)


def apply_check(check_fn: Callable,
                df: pd.DataFrame,
                *args,
                dataset_name: str,
                check_name: str | None = None,
                **kwargs) -> pd.DataFrame:
    """Run `check_fn(df, *args, dataset_name=dataset_name, **kwargs)`,
    persist the rejected rows, update the summary, and return the clean df.
    """
    check_label = check_name or check_fn.__name__
    total_in = len(df)
    clean, rejected = check_fn(df, *args, dataset_name=dataset_name, **kwargs)
    if not rejected.empty:
        # tag the rejected rows with the check that caught them
        rejected = rejected.copy()
        rejected["_check_name"] = check_label
        rejected["_dataset"] = dataset_name
        persist_rejected(rejected, dataset_name)
    update_quarantine_summary(dataset_name, check_label, total_in, len(rejected))
    print(f"  [{dataset_name}] {check_label}: "
          f"{len(rejected)} rejected / {total_in} in ({len(rejected)/total_in*100:.2f}%)" if total_in else
          f"  [{dataset_name}] {check_label}: empty input")
    return clean


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    """Quick smoke test that each check returns the right shapes on toy data."""
    df = pd.DataFrame({
        "id":   ["A", "B", "B", "C", None],
        "val":  [1.0, 2.0, 2.0, -5.0, 3.0],
        "ref":  ["X", "Y", "Y", "Z", "X"],
        "code": ["AAA01", "AAA02", "BBB", "AAA04", "AAA05"],
    })

    c, r = check_duplicates(df, ["id"], "test")
    assert len(c) == 3 and len(r) == 2, f"duplicates: c={len(c)} r={len(r)}"

    c, r = check_nulls(df, ["id"], "test")
    assert len(c) == 4 and len(r) == 1, f"nulls: c={len(c)} r={len(r)}"

    c, r = check_referential_integrity(df, "ref", {"X", "Y"}, "test")
    assert len(c) == 4 and len(r) == 1, f"ref: c={len(c)} r={len(r)}"

    c, r = check_value_range(df, "val", min_val=0, dataset_name="test")
    assert len(c) == 4 and len(r) == 1, f"range: c={len(c)} r={len(r)}"

    c, r = check_format(df, "code", r"AAA\d{2}", dataset_name="test",
                        format_label="AAA-NN")
    assert len(c) == 4 and len(r) == 1, f"format: c={len(c)} r={len(r)}"

    c, r = check_value_set(df, "ref", {"X", "Y"}, dataset_name="test")
    assert len(c) == 4 and len(r) == 1, f"value_set: c={len(c)} r={len(r)}"

    print("dq_checks self-test: PASS")


if __name__ == "__main__":
    _self_test()
