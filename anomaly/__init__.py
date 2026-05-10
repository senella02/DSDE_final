
from __future__ import annotations

from pathlib import Path

import pandas as pd

from lib import load_data as _load_data
from .rules import (
    rule_perfect_turnout,
    rule_zero_total_ballots,
    rule_high_void_rate,
    rule_high_spoil_rate,
    rule_negative_rate,
    rule_all_zero_votes,
    rule_single_candidate_sweep,
)
from .stats import stat_turnout, stat_void, stat_spoil, stat_party_dominance, compute_dominant_party_name
from .cluster import run_clustering

_HERE = Path(__file__).parent.parent
DATA_DIR = _HERE / "data"
REPORTS_DIR = _HERE / "reports"

_FLAG_COLS = [
    "RULE_PERFECT_TURNOUT",
    "RULE_ZERO_TOTAL_BALLOTS",
    "RULE_HIGH_VOID_RATE",
    "RULE_HIGH_SPOIL_RATE",
    "RULE_NEGATIVE_RATE",
    "RULE_ALL_ZERO_VOTES",
    "RULE_SINGLE_CANDIDATE_SWEEP",
    "STAT_TURNOUT_Z",
    "STAT_VOID_Z",
    "STAT_SPOIL_Z",
    "STAT_PARTY_DOMINANCE",
]

_DEFAULTS: dict = {
    "z_threshold": 3.0,
    "iqr_multiplier": 3.0,
    "high_void_rate": 0.10,
    "high_spoil_rate": 0.10,
    "party_dominance": 0.90,
    "method": "z",
}


def run_all(
    records: pd.DataFrame,
    candidates: pd.DataFrame,
    thresholds: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run all anomaly checks and return (anomaly_flags_df, cluster_labels_df).
    Writes reports/anomaly_flags.csv and reports/cluster_labels.csv as side effects.

    thresholds keys (all optional):
        z_threshold     float  3.0   — z-score cutoff for STAT_* flags
        iqr_multiplier  float  3.0   — IQR multiplier when method="iqr"
        high_void_rate  float  0.10  — RULE_HIGH_VOID_RATE cutoff
        high_spoil_rate float  0.10  — RULE_HIGH_SPOIL_RATE cutoff
        party_dominance float  0.90  — STAT_PARTY_DOMINANCE absolute cutoff
        method          str    "z"   — "z" or "iqr" for STAT_* checks
    """
    cfg = {**_DEFAULTS, **(thresholds or {})}

    flags = records[
        ["file_id", "ballot_type", "station_number", "subdistrict",
         "count_tier", "meta_tier", "imputed_fields", "failure_modes",
         "turnout_rate", "void_rate", "spoil_rate"]
    ].copy()
    flags["dominant_party"] = compute_dominant_party_name(records, candidates).values

    # --- Rule checks ---
    flags["RULE_PERFECT_TURNOUT"] = rule_perfect_turnout(records)
    flags["RULE_ZERO_TOTAL_BALLOTS"] = rule_zero_total_ballots(records)
    flags["RULE_HIGH_VOID_RATE"] = rule_high_void_rate(records, cfg["high_void_rate"])
    flags["RULE_HIGH_SPOIL_RATE"] = rule_high_spoil_rate(records, cfg["high_spoil_rate"])
    flags["RULE_NEGATIVE_RATE"] = rule_negative_rate(records)
    flags["RULE_ALL_ZERO_VOTES"] = rule_all_zero_votes(records, candidates)
    flags["RULE_SINGLE_CANDIDATE_SWEEP"] = rule_single_candidate_sweep(records, candidates)

    # --- Statistical checks (baselines computed on Tier A only) ---
    tier_a = records["count_tier"] == "A"
    method = cfg["method"]
    z = float(cfg["z_threshold"])
    iqr = float(cfg["iqr_multiplier"])

    flags["STAT_TURNOUT_Z"] = stat_turnout(records, tier_a, method, z, iqr)
    flags["STAT_VOID_Z"] = stat_void(records, tier_a, method, z, iqr)
    flags["STAT_SPOIL_Z"] = stat_spoil(records, tier_a, method, z, iqr)
    flags["STAT_PARTY_DOMINANCE"] = stat_party_dominance(
        records, candidates, cfg["party_dominance"], z
    )

    # --- Composite score ---
    flags["anomaly_score"] = flags[_FLAG_COLS].sum(axis=1)
    flags["is_anomalous"] = flags["anomaly_score"] >= 1

    REPORTS_DIR.mkdir(exist_ok=True)
    flags.to_csv(REPORTS_DIR / "anomaly_flags.csv", index=False, encoding="utf-8-sig")

    cluster_labels = run_clustering(records, candidates)

    return flags, cluster_labels


def load_flags() -> pd.DataFrame:
    """Read cached anomaly_flags.csv. Runs detection with defaults if file is missing."""
    csv = REPORTS_DIR / "anomaly_flags.csv"
    if csv.exists():
        return pd.read_csv(csv)
    records, candidates, _, _ = _load_data()
    flags, _ = run_all(records, candidates)
    return flags
