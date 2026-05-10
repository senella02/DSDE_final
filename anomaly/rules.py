"""
anomaly/rules.py — deterministic rule-based anomaly checks.

Each public function takes records (and optionally candidates) and returns a
boolean pd.Series aligned to records.index (True = anomalous).

All checks are null-safe: missing values never raise, they produce False.
"""
from __future__ import annotations

import pandas as pd


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _join_to_records(records: pd.DataFrame, flag_df: pd.DataFrame) -> pd.Series:
    """
    Merge a (file_id, ballot_type, flag:bool) frame back onto records by
    original index position.  Handles the edge case where one PDF produces
    more than two records (duplicate file_id+ballot_type pairs).
    """
    key = records[["file_id", "ballot_type"]].copy()
    key["_idx"] = records.index
    merged = key.merge(flag_df[["file_id", "ballot_type", "flag"]],
                       on=["file_id", "ballot_type"], how="left")
    # In case of duplicates in records, drop_duplicates on _idx keeps first match
    merged = merged.drop_duplicates(subset="_idx")
    # Compare == True so that NaN rows become False without triggering
    # the pandas FutureWarning about object-dtype downcasting in fillna.
    return (merged.set_index("_idx")["flag"].reindex(records.index) == True)  # noqa: E712


# ---------------------------------------------------------------------------
# Ballot arithmetic rules
# ---------------------------------------------------------------------------

def rule_turnout_ballot_mismatch(records: pd.DataFrame) -> pd.Series:
    """voter_turnout and total_ballots differ by more than 1."""
    vt = records["voter_turnout"]
    tb = records["total_ballots"]
    both = vt.notna() & tb.notna()
    return (both & ((vt - tb).abs() > 1)).fillna(False)


def rule_perfect_turnout(records: pd.DataFrame) -> pd.Series:
    """turnout_rate == 1.0 exactly (100% — near-impossible in practice)."""
    tr = records["turnout_rate"]
    return (tr.notna() & (tr == 1.0))


def rule_zero_total_ballots(records: pd.DataFrame) -> pd.Series:
    """Station has eligible voters but total_ballots == 0."""
    tb = records["total_ballots"]
    ev = records["eligible_voters"]
    return (tb.notna() & (tb == 0) & ev.notna() & (ev > 0))


# ---------------------------------------------------------------------------
# Rate-based rules
# ---------------------------------------------------------------------------

def rule_high_void_rate(records: pd.DataFrame, threshold: float = 0.10) -> pd.Series:
    """void_rate exceeds threshold (default 10%)."""
    vr = records["void_rate"]
    return (vr.notna() & (vr > threshold))


def rule_high_spoil_rate(records: pd.DataFrame, threshold: float = 0.10) -> pd.Series:
    """spoil_rate exceeds threshold (default 10%)."""
    sr = records["spoil_rate"]
    return (sr.notna() & (sr > threshold))


def rule_negative_rate(records: pd.DataFrame) -> pd.Series:
    """Any rate column is negative — an arithmetic impossibility from OCR."""
    flag = pd.Series(False, index=records.index)
    for col in ["turnout_rate", "void_rate", "spoil_rate"]:
        s = records[col]
        flag = flag | (s.notna() & (s < 0))
    return flag


# ---------------------------------------------------------------------------
# Candidate-level rules  (require count_tier=A candidates)
# ---------------------------------------------------------------------------

def rule_all_zero_votes(
    records: pd.DataFrame, candidates: pd.DataFrame
) -> pd.Series:
    """
    All non-withdrawn candidates at a station report 0 votes.
    Only evaluated for count_tier=A records where OCR is trustworthy.
    """
    active = candidates[
        (candidates["count_tier"] == "A") & ~candidates["withdrawn"]
    ]
    if active.empty:
        return pd.Series(False, index=records.index)

    grp = (
        active.groupby(["file_id", "ballot_type"])
        .agg(
            has_votes=("votes", lambda v: v.notna().any()),
            has_nonzero=("votes", lambda v: (v.notna() & (v > 0)).any()),
        )
        .reset_index()
    )
    grp["flag"] = grp["has_votes"] & ~grp["has_nonzero"]
    return _join_to_records(records, grp[grp["flag"]])


def rule_single_candidate_sweep(
    records: pd.DataFrame,
    candidates: pd.DataFrame,
    threshold: float = 0.95,
) -> pd.Series:
    """
    One candidate holds >= threshold share of valid votes while at least one
    other candidate also has votes > 0.  Evaluated on count_tier=A only.
    """
    active = candidates[
        (candidates["count_tier"] == "A")
        & ~candidates["withdrawn"]
        & candidates["votes"].notna()
    ]
    if active.empty:
        return pd.Series(False, index=records.index)

    station_total = (
        active.groupby(["file_id", "ballot_type"])["votes"]
        .sum()
        .rename("station_total")
    )
    station_max = (
        active.groupby(["file_id", "ballot_type"])["votes"]
        .max()
        .rename("station_max")
    )
    nonzero_count = (
        active[active["votes"] > 0]
        .groupby(["file_id", "ballot_type"])["votes"]
        .count()
        .rename("nonzero_count")
    )

    m = (
        station_total.to_frame()
        .join(station_max)
        .join(nonzero_count)
        .fillna({"nonzero_count": 0})
        .reset_index()
    )
    m["share"] = m["station_max"] / m["station_total"].replace(0, float("nan"))

    flagged = m[(m["share"] >= threshold) & (m["nonzero_count"] >= 2)][
        ["file_id", "ballot_type"]
    ].copy()
    flagged["flag"] = True
    return _join_to_records(records, flagged)
