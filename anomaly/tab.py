"""
anomaly/tab.py — Streamlit tab renderer for the Anomaly Detection section.

Contract: one public render(records, candidates, pages, official) function.
No module-level st calls.

Sections:
  A — Summary metric cards
  B — Flag frequency bar chart + dominant-party chart (lib.color())
  C — Scatter plot (turnout vs void, red = anomalous) + cluster view
  D — Styled detail table + download
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from anomaly import run_all
from lib import clean_subset, color, load_data

REPORTS_DIR = Path(__file__).parent.parent / "reports"

_FLAG_COLS = [
    "RULE_TURNOUT_BALLOT_MISMATCH",
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

_FLAG_TYPE = {c: ("Rule-based" if c.startswith("RULE_") else "Statistical") for c in _FLAG_COLS}

_FLAG_LABEL = {
    "RULE_TURNOUT_BALLOT_MISMATCH": "Turnout ≠ Ballots",
    "RULE_PERFECT_TURNOUT":         "100% Turnout",
    "RULE_ZERO_TOTAL_BALLOTS":      "Zero Total Ballots",
    "RULE_HIGH_VOID_RATE":          "High Void Rate",
    "RULE_HIGH_SPOIL_RATE":         "High Spoil Rate",
    "RULE_NEGATIVE_RATE":           "Negative Rate",
    "RULE_ALL_ZERO_VOTES":          "All Votes Zero",
    "RULE_SINGLE_CANDIDATE_SWEEP":  "Single-Candidate Sweep",
    "STAT_TURNOUT_Z":               "Turnout Outlier (stat)",
    "STAT_VOID_Z":                  "Void Rate Outlier (stat)",
    "STAT_SPOIL_Z":                 "Spoil Rate Outlier (stat)",
    "STAT_PARTY_DOMINANCE":         "Party Dominance (stat)",
}

_DISPLAY_COLS = (
    ["station_number", "subdistrict", "ballot_type",
     "count_tier", "meta_tier", "imputed_fields", "anomaly_score"]
    + _FLAG_COLS
    + ["dominant_party", "turnout_rate", "void_rate", "spoil_rate", "failure_modes"]
)


# ---------------------------------------------------------------------------
# Cached detection — keyed on threshold scalars so DataFrames are not the key
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Running anomaly detection…")
def _get_flags(
    z_threshold: float,
    void_cut: float,
    spoil_cut: float,
    dom_cut: float,
    method: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    records, candidates, _, _ = load_data()
    thresholds = {
        "z_threshold": z_threshold,
        "high_void_rate": void_cut,
        "high_spoil_rate": spoil_cut,
        "party_dominance": dom_cut,
        "method": method,
    }
    return run_all(records, candidates, thresholds)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render(
    records: pd.DataFrame,
    candidates: pd.DataFrame,
    pages: pd.DataFrame,
    official: pd.DataFrame,
) -> None:
    st.header("Anomaly Detection")
    st.caption(
        "Identifies unusual electoral patterns in the ballot-count data. "
        "**Rule-based** flags are deterministic; **statistical** flags are relative "
        "to a baseline computed on Tier A (OCR-verified) records only. "
        "A flag on a Tier B/C record may be an OCR artefact — verify the scan before drawing conclusions."
    )

    # -----------------------------------------------------------------------
    # In-tab settings (expander keeps controls scoped to this tab only)
    # -----------------------------------------------------------------------
    with st.expander("Settings", expanded=False):
        c1, c2, c3, c4, c5 = st.columns(5)
        method = c1.radio(
            "Outlier method", ["Z-score", "IQR"],
            key="anom_method",
            help="Method used for STAT_* flags. IQR is more robust for skewed distributions.",
        )
        method_str = "z" if method == "Z-score" else "iqr"
        z_thresh = c2.slider(
            "Z-score threshold", 1.5, 5.0, 3.0, 0.5,
            key="anom_z",
            help="Rows further than this many standard deviations from the Tier-A mean are flagged.",
        )
        void_cut = c3.slider(
            "High void/spoil rate cutoff", 0.05, 0.30, 0.10, 0.01,
            key="anom_void", format="%.2f",
            help="RULE_HIGH_VOID_RATE and RULE_HIGH_SPOIL_RATE threshold.",
        )
        dom_cut = c4.slider(
            "Party dominance cutoff", 0.70, 1.00, 0.90, 0.05,
            key="anom_dom", format="%.2f",
            help="One party holding more than this share of valid votes is flagged.",
        )
        show_low_tier = c5.checkbox(
            "Include Tier B/C records in table", False,
            key="anom_tier",
            help="Tier B/C records may have OCR errors — treat their flags with caution.",
        )

    flags, clusters = _get_flags(z_thresh, void_cut, void_cut, dom_cut, method_str)

    n_total = len(flags)
    n_anomalous = int(flags["is_anomalous"].sum())
    n_high_conf = int((flags["is_anomalous"] & (flags["count_tier"] == "A")).sum())
    flag_counts = flags[_FLAG_COLS].sum().sort_values(ascending=False)
    top_flag = _FLAG_LABEL.get(str(flag_counts.idxmax()), flag_counts.idxmax()) if n_anomalous > 0 else "—"

    # -----------------------------------------------------------------------
    # Section A — Metric cards
    # -----------------------------------------------------------------------
    st.subheader("A · Summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Anomalous records", n_anomalous, f"{n_anomalous/n_total:.1%} of all")
    col2.metric("High-confidence (Tier A)", n_high_conf, f"{n_high_conf/n_total:.1%} of all")
    col3.metric("Most common flag", top_flag)
    col4.metric("Clean records", n_total - n_anomalous,
                f"{(n_total - n_anomalous)/n_total:.1%} of all")

    st.divider()

    # -----------------------------------------------------------------------
    # Section B — Flag frequency + dominant-party breakdown
    # -----------------------------------------------------------------------
    st.subheader("B · Flag frequency")

    freq = (
        pd.DataFrame({
            "flag":  list(_FLAG_LABEL.values()),
            "key":   list(_FLAG_LABEL.keys()),
            "count": [int(flags[k].sum()) for k in _FLAG_LABEL],
            "type":  [_FLAG_TYPE[k] for k in _FLAG_LABEL],
        })
        .sort_values("count", ascending=True)
    )

    fig_freq = px.bar(
        freq, x="count", y="flag", color="type", orientation="h",
        color_discrete_map={"Rule-based": "#3498DB", "Statistical": "#E67E22"},
        title=f"Anomaly flag frequency<br><sub>n={n_total} • all records</sub>",
        labels={"count": "Records flagged", "flag": "", "type": "Flag type"},
    )
    fig_freq.update_layout(legend_title_text="", height=420)
    st.plotly_chart(fig_freq, use_container_width=True)

    # Dominant-party chart — uses lib.color() for the shared party palette
    dom_flagged = flags[flags["STAT_PARTY_DOMINANCE"] & flags["dominant_party"].notna()]
    if not dom_flagged.empty:
        party_counts = (
            dom_flagged.groupby("dominant_party")
            .size()
            .reset_index(name="stations")
            .sort_values("stations", ascending=True)
        )
        party_counts["hex"] = party_counts["dominant_party"].apply(color)
        _, dom_cap = clean_subset(flags, requires=["dominant_party"])

        fig_dom = px.bar(
            party_counts, x="stations", y="dominant_party", orientation="h",
            color="dominant_party",
            color_discrete_map=dict(zip(party_counts["dominant_party"], party_counts["hex"])),
            title=f"Dominant parties among STAT_PARTY_DOMINANCE flagged records<br><sub>{dom_cap}</sub>",
            labels={"stations": "Flagged stations", "dominant_party": ""},
        )
        fig_dom.update_layout(showlegend=False, height=max(200, 40 * len(party_counts)))
        st.plotly_chart(fig_dom, use_container_width=True)

    st.divider()

    # -----------------------------------------------------------------------
    # Section C — Scatter plot
    # -----------------------------------------------------------------------
    st.subheader("C · Turnout vs void rate scatter")

    # clean_subset produces the standard gate caption for the chart title
    scatter_df, scatter_cap = clean_subset(flags, requires=["turnout_rate", "void_rate"])

    scatter_df = scatter_df.copy()
    scatter_df["station_display"] = scatter_df["station_number"].apply(
        lambda x: f"Station {int(x)}" if pd.notna(x) else "Unknown station"
    )
    scatter_df["subdistrict_display"] = scatter_df["subdistrict"].fillna("—")
    scatter_df["dominant_party_display"] = scatter_df["dominant_party"].fillna("—")
    scatter_df["imputed_display"] = scatter_df["imputed_fields"].fillna("none")
    scatter_df["flags_triggered"] = scatter_df[_FLAG_COLS].apply(
        lambda row: ", ".join(_FLAG_LABEL[k] for k in _FLAG_COLS if row[k]), axis=1
    ).replace("", "none")

    def _category(row):
        if row["is_anomalous"] and row["count_tier"] == "A":
            return "Anomaly (Tier A — high confidence)"
        if row["is_anomalous"]:
            return "Anomaly (Tier B/C — verify OCR)"
        return "Normal"

    scatter_df["category"] = scatter_df.apply(_category, axis=1)

    color_map = {
        "Anomaly (Tier A — high confidence)": "#E74C3C",
        "Anomaly (Tier B/C — verify OCR)":    "#F1948A",
        "Normal":                              "#AAAAAA",
    }
    symbol_map = {
        "Anomaly (Tier A — high confidence)": "circle",
        "Anomaly (Tier B/C — verify OCR)":    "circle-open",
        "Normal":                              "circle",
    }

    fig_scatter = px.scatter(
        scatter_df,
        x="turnout_rate", y="void_rate",
        color="category", symbol="category",
        color_discrete_map=color_map,
        symbol_map=symbol_map,
        hover_data={
            "station_display":       True,
            "subdistrict_display":   True,
            "ballot_type":           True,
            "count_tier":            True,
            "meta_tier":             True,
            "anomaly_score":         True,
            "flags_triggered":       True,
            "dominant_party_display":True,
            "imputed_display":       True,
            "failure_modes":         True,
            "turnout_rate":          ":.3f",
            "void_rate":             ":.3f",
            "category":              False,
        },
        title=(
            f"Turnout rate vs void rate<br>"
            f"<sub>{scatter_cap} • baseline: count∈{{A}} (stat flags)</sub>"
        ),
        labels={
            "turnout_rate": "Turnout rate",
            "void_rate":    "Void rate",
            "category":     "Status",
        },
    )
    fig_scatter.update_traces(marker_size=8, marker_line_width=1.5)
    fig_scatter.update_layout(height=500, legend_title_text="")
    st.plotly_chart(fig_scatter, use_container_width=True)

    # Cluster view
    with st.expander("Cluster view (exploratory pattern groups — not a definitive anomaly label)"):
        cluster_plot = scatter_df.merge(
            clusters[["file_id", "ballot_type", "cluster_label"]],
            on=["file_id", "ballot_type"], how="left",
        )
        has_clusters = cluster_plot["cluster_label"].notna().any()

        if not has_clusters:
            st.info("Clustering requires scikit-learn and at least 4 Tier-A / M0 records with all features present.")
        else:
            cluster_plot = cluster_plot[
                cluster_plot["turnout_rate"].notna() & cluster_plot["void_rate"].notna()
            ].copy()
            cluster_plot["cluster_str"] = cluster_plot["cluster_label"].apply(
                lambda x: f"Cluster {int(x)}" if pd.notna(x) else "Not clustered"
            )
            _, clust_cap = clean_subset(
                cluster_plot[cluster_plot["cluster_label"].notna()],
                count_tier="A", meta_tier=["M0"],
            )
            fig_clust = px.scatter(
                cluster_plot,
                x="turnout_rate", y="void_rate",
                color="cluster_str",
                hover_data={
                    "station_display":        True,
                    "ballot_type":            True,
                    "count_tier":             True,
                    "meta_tier":              True,
                    "dominant_party_display": True,
                    "imputed_display":        True,
                },
                title=(
                    f"Station clusters (KMeans, k chosen by silhouette)<br>"
                    f"<sub>fitted: {clust_cap} • greyed = outside fitting subset</sub>"
                ),
                labels={"turnout_rate": "Turnout rate", "void_rate": "Void rate",
                        "cluster_str": "Cluster"},
            )
            fig_clust.update_traces(marker_size=8)
            fig_clust.update_layout(height=460)
            st.plotly_chart(fig_clust, use_container_width=True)

    st.divider()

    # -----------------------------------------------------------------------
    # Section D — Detail table
    # -----------------------------------------------------------------------
    st.subheader("D · Anomalous records detail")

    if not show_low_tier:
        table_df, table_cap = clean_subset(
            flags[flags["is_anomalous"]].copy(), count_tier="A"
        )
    else:
        table_df = flags[flags["is_anomalous"]].copy()
        table_cap = f"n={len(table_df)}/{n_total} • all tiers"

    table_df = table_df.sort_values("anomaly_score", ascending=False).reset_index(drop=True)

    for rate_col in ["turnout_rate", "void_rate", "spoil_rate"]:
        table_df[rate_col] = table_df[rate_col].apply(
            lambda x: f"{x:.3f}" if pd.notna(x) else "—"
        )
    table_df["station_number"] = table_df["station_number"].apply(
        lambda x: int(x) if pd.notna(x) else "—"
    )
    table_df["imputed_fields"] = table_df["imputed_fields"].fillna("—")
    table_df["dominant_party"] = table_df["dominant_party"].fillna("—")
    table_df["failure_modes"] = table_df["failure_modes"].fillna("—")

    st.caption(f"{table_cap} • sorted by anomaly score ↓")

    show_df = table_df[_DISPLAY_COLS].reset_index(drop=True)

    def _all_red(row):
        return ["background-color: #FFCCCC"] * len(row)

    try:
        styled = show_df.style.apply(_all_red, axis=1)
        st.dataframe(styled, use_container_width=True, height=420)
    except Exception:
        st.dataframe(show_df, use_container_width=True, height=420)

    csv_bytes = (
        flags[_DISPLAY_COLS + ["is_anomalous"]]
        .to_csv(index=False, encoding="utf-8-sig")
        .encode("utf-8-sig")
    )
    st.download_button(
        "Download anomaly_flags.csv",
        data=csv_bytes,
        file_name="anomaly_flags.csv",
        mime="text/csv",
        key="anom_dl",
    )
