"""
anomaly/stats.py — statistical outlier detection.

All baselines are computed on count_tier=A records only, then applied to the
full dataset.  This prevents OCR-corrupted values from distorting the mean/std
and masking genuine electoral anomalies.
"""
from __future__ import annotations

import pandas as pd


# ---------------------------------------------------------------------------
# Core statistical helpers
# ---------------------------------------------------------------------------

def z_flag(
    series: pd.Series, baseline_mask: pd.Series, threshold: float
) -> pd.Series:
    """Flag rows where |z-score| > threshold. Baseline computed from baseline_mask rows."""
    base = series[baseline_mask & series.notna()]
    if base.empty or base.std() == 0:
        return pd.Series(False, index=series.index)
    mu, sigma = base.mean(), base.std()
    return series.notna() & (((series - mu) / sigma).abs() > threshold)


def iqr_flag(
    series: pd.Series, baseline_mask: pd.Series, multiplier: float
) -> pd.Series:
    """Flag rows above Q3 + multiplier*IQR. Robust to right-skewed distributions."""
    base = series[baseline_mask & series.notna()]
    if base.empty:
        return pd.Series(False, index=series.index)
    q1, q3 = base.quantile(0.25), base.quantile(0.75)
    upper = q3 + multiplier * (q3 - q1)
    return series.notna() & (series > upper)


def _detect(series, baseline_mask, method, z, iqr):
    fn = z_flag if method == "z" else iqr_flag
    param = z if method == "z" else iqr
    return fn(series, baseline_mask, param)


# ---------------------------------------------------------------------------
# Per-metric stat checks
# ---------------------------------------------------------------------------

def stat_turnout(
    records: pd.DataFrame,
    tier_a: pd.Series,
    method: str,
    z: float,
    iqr: float,
) -> pd.Series:
    """Outlier turnout_rate.  Baseline: Tier A rows with both numerator and denominator."""
    baseline = tier_a & records["eligible_voters"].notna() & records["voter_turnout"].notna()
    return _detect(records["turnout_rate"], baseline, method, z, iqr)


def stat_void(
    records: pd.DataFrame,
    tier_a: pd.Series,
    method: str,
    z: float,
    iqr: float,
) -> pd.Series:
    """Outlier void_rate.  Baseline: Tier A rows with void_ballots and total_ballots."""
    baseline = tier_a & records["void_ballots"].notna() & records["total_ballots"].notna()
    return _detect(records["void_rate"], baseline, method, z, iqr)


def stat_spoil(
    records: pd.DataFrame,
    tier_a: pd.Series,
    method: str,
    z: float,
    iqr: float,
) -> pd.Series:
    """Outlier spoil_rate.  Baseline: Tier A rows with spoiled_ballots and total_ballots."""
    baseline = tier_a & records["spoiled_ballots"].notna() & records["total_ballots"].notna()
    return _detect(records["spoil_rate"], baseline, method, z, iqr)


# ---------------------------------------------------------------------------
# Party dominance
# ---------------------------------------------------------------------------

def compute_dominant_party_name(
    records: pd.DataFrame, candidates: pd.DataFrame
) -> pd.Series:
    """
    Return a Series (indexed like records) with the name of the party that holds
    the largest vote share at each station.  Only count_tier=A, non-withdrawn
    candidates are used.  NaN where data is insufficient.
    """
    active = candidates[
        (candidates["count_tier"] == "A")
        & ~candidates["withdrawn"]
        & candidates["votes"].notna()
    ]
    if active.empty:
        return pd.Series(pd.NA, index=records.index, dtype=object)

    party_votes = (
        active.groupby(["file_id", "ballot_type", "party"])["votes"]
        .sum()
        .rename("party_votes")
        .reset_index()
    )
    idx_max = party_votes.groupby(["file_id", "ballot_type"])["party_votes"].idxmax()
    top = party_votes.loc[idx_max.values, ["file_id", "ballot_type", "party"]].reset_index(drop=True)

    key = records[["file_id", "ballot_type"]].copy()
    key["_idx"] = records.index
    joined = key.merge(top, on=["file_id", "ballot_type"], how="left")
    joined = joined.drop_duplicates(subset="_idx")
    return joined.set_index("_idx")["party"].reindex(records.index)


def compute_dominant_party_share(
    records: pd.DataFrame, candidates: pd.DataFrame
) -> pd.Series:
    """
    For each ballot record, return the vote share held by the single largest
    party/candidate.  Only non-withdrawn, count_tier=A candidates are used.
    Returns a float Series indexed like records; NaN where data is insufficient.
    """
    active = candidates[
        (candidates["count_tier"] == "A")
        & ~candidates["withdrawn"]
        & candidates["votes"].notna()
    ]
    if active.empty:
        return pd.Series(pd.NA, index=records.index, dtype=float)

    station_total = (
        active.groupby(["file_id", "ballot_type"])["votes"]
        .sum()
        .rename("station_total")
    )
    party_votes = (
        active.groupby(["file_id", "ballot_type", "party"])["votes"]
        .sum()
        .rename("party_votes")
        .reset_index()
    )
    merged = party_votes.merge(
        station_total.reset_index(), on=["file_id", "ballot_type"]
    )
    merged["share"] = merged["party_votes"] / merged["station_total"].replace(0, float("nan"))

    max_share = (
        merged.groupby(["file_id", "ballot_type"])["share"]
        .max()
        .rename("max_share")
        .reset_index()
    )

    # Join back to records by original index
    key = records[["file_id", "ballot_type"]].copy()
    key["_idx"] = records.index
    joined = key.merge(max_share, on=["file_id", "ballot_type"], how="left")
    joined = joined.drop_duplicates(subset="_idx")
    return joined.set_index("_idx")["max_share"].reindex(records.index)


def stat_party_dominance(
    records: pd.DataFrame,
    candidates: pd.DataFrame,
    threshold: float = 0.90,
    z_threshold: float = 3.0,
) -> pd.Series:
    """
    Flag records where a single party/candidate dominates beyond threshold
    (absolute) OR is a statistical outlier across all stations (z-score).

    Uses count_tier=A candidates as baseline so OCR-corrupted values do not
    pull the reference distribution.
    """
    dom = compute_dominant_party_share(records, candidates)

    abs_flag = dom.notna() & (dom > threshold)

    tier_a = records["count_tier"] == "A"
    z_dom = z_flag(dom, tier_a & dom.notna(), z_threshold)

    return (abs_flag | z_dom).fillna(False)
