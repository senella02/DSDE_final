"""
anomaly/cluster.py — KMeans pattern discovery.

Groups polling stations into behavioural clusters using four features:
    turnout_rate, void_rate, spoil_rate, dominant_party_share

Only count_tier=A / meta_tier=M0 records with all four features present are
used for fitting.  All other records receive cluster_label=NaN.

Results are written to reports/cluster_labels.csv and returned as a DataFrame.

Note: clustering output is exploratory — not a definitive anomaly label.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .stats import compute_dominant_party_share

_HERE = Path(__file__).parent.parent
REPORTS_DIR = _HERE / "reports"

try:
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score, silhouette_samples
    from sklearn.preprocessing import StandardScaler
    _SKLEARN = True
except ImportError:
    _SKLEARN = False

_FEATURE_COLS = ["turnout_rate", "void_rate", "spoil_rate", "dominant_party_share"]


def run_clustering(
    records: pd.DataFrame,
    candidates: pd.DataFrame,
    max_k: int = 6,
) -> pd.DataFrame:
    """
    Fit KMeans on qualifying stations; choose k by silhouette score.
    Returns a DataFrame with columns [file_id, ballot_type, cluster_label,
    silhouette_score] indexed like records.  Writes cluster_labels.csv.
    """
    result = records[["file_id", "ballot_type"]].copy()
    result["cluster_label"] = pd.NA
    result["silhouette_score"] = pd.NA

    if not _SKLEARN:
        _write(result)
        return result

    dom = compute_dominant_party_share(records, candidates)

    feat = records[["count_tier", "meta_tier", "turnout_rate",
                    "void_rate", "spoil_rate"]].copy()
    feat["dominant_party_share"] = dom.values

    mask = (
        (feat["count_tier"] == "A")
        & (feat["meta_tier"] == "M0")
        & feat[_FEATURE_COLS].notna().all(axis=1)
    )
    sub_idx = records.index[mask]

    if len(sub_idx) < max(4, max_k):
        _write(result)
        return result

    X = feat.loc[sub_idx, _FEATURE_COLS].values
    X_scaled = StandardScaler().fit_transform(X)

    best_k, best_score, best_labels = 2, -1.0, None
    for k in range(2, min(max_k + 1, len(sub_idx))):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X_scaled)
        if len(set(labels)) < 2:
            continue
        score = float(silhouette_score(X_scaled, labels))
        if score > best_score:
            best_k, best_score, best_labels = k, score, labels

    if best_labels is None:
        _write(result)
        return result

    per_sample = silhouette_samples(X_scaled, best_labels)
    result.loc[sub_idx, "cluster_label"] = best_labels
    result.loc[sub_idx, "silhouette_score"] = per_sample

    _write(result)
    return result


def _write(df: pd.DataFrame) -> None:
    REPORTS_DIR.mkdir(exist_ok=True)
    df.to_csv(REPORTS_DIR / "cluster_labels.csv", index=False, encoding="utf-8-sig")
