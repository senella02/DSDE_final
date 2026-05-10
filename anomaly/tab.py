
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from anomaly import run_all
from lib import clean_subset, load_data

REPORTS_DIR = Path(__file__).parent.parent / "reports"

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

_FLAG_TYPE = {c: ("Rule-based" if c.startswith("RULE_") else "Statistical") for c in _FLAG_COLS}

_FLAG_LABEL = {
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



# Cached detection — keyed on threshold scalars so DataFrames are not the key


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



# Public entry point


def render(
    records: pd.DataFrame,
    candidates: pd.DataFrame,
    pages: pd.DataFrame,
    official: pd.DataFrame,
) -> None:
    st.header("Anomaly Detection")


    # In-tab settings (expander keeps controls scoped to this tab only)

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


    # Section A — Metric cards

    st.subheader("Summary")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Anomalous records", n_anomalous, f"{n_anomalous/n_total:.1%} of all")
    col2.metric("High-confidence (Tier A)", n_high_conf, f"{n_high_conf/n_total:.1%} of all")
    col3.metric("Most common flag", top_flag)
    col4.metric("Clean records", n_total - n_anomalous,
                f"{(n_total - n_anomalous)/n_total:.1%} of all")

    st.divider()


    # Data tier explanation

    st.subheader("Data quality tiers")
    ta, tb, tc = st.columns(3)
    with ta:
        st.markdown("**Tier A High confidence**")
        st.markdown(
            "Both ballot checks pass: "
            "valid + void + spoiled = total ballots *and* "
            "sum of candidate votes = valid votes. "
            
        )
    with tb:
        st.markdown("**Tier B Partial confidence**")
        st.markdown(
            "The ballot totals balance (valid + void + spoiled = total ballots), "
            "but candidate-vote rows don't sum to valid votes which may be the misread by OCR"
        )
    with tc:
        st.markdown("**Tier C Low confidence**")
        st.markdown(
            "The main ballot totals don't balance a header field (eligible voters, "
            "total ballots) was likely misread by OCR."
        )

    st.divider()


    # Section B — Flag frequency + dominant-party breakdown

    st.subheader("Flag frequency")

    _FREQ_EXCLUDE = {
        "RULE_SINGLE_CANDIDATE_SWEEP",
        "RULE_NEGATIVE_RATE",
        "RULE_ALL_ZERO_VOTES",
        "RULE_ZERO_TOTAL_BALLOTS",
        "RULE_PERFECT_TURNOUT",
    }
    _freq_keys = [k for k in _FLAG_LABEL if k not in _FREQ_EXCLUDE]
    freq = (
        pd.DataFrame({
            "flag":  [_FLAG_LABEL[k] for k in _freq_keys],
            "key":   _freq_keys,
            "count": [int(flags[k].sum()) for k in _freq_keys],
            "type":  [_FLAG_TYPE[k] for k in _freq_keys],
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

    st.divider()


    # Section C — Scatter plot

    st.subheader("Turnout vs void rate scatter")

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

    _CAT_COLOR = {
        "Anomaly (Tier A — high confidence)": "#E74C3C",
        "Anomaly (Tier B/C — verify OCR)":    "#F1948A",
        "Normal":                              "#AAAAAA",
    }
    # circle-open for Tier B/C (in-range); solid triangle for all out-of-range
    _CAT_SYMBOL_IN = {
        "Anomaly (Tier A — high confidence)": "circle",
        "Anomaly (Tier B/C — verify OCR)":    "circle-open",
        "Normal":                              "circle",
    }

    SC_X_MAX, SC_Y_MAX = 10.0, 0.2

    def _oor_symbol_scatter(row):
        """Triangle pointing inward from the axis edge that was exceeded."""
        if row["void_rate"] > SC_Y_MAX:
            return "triangle-down"
        return "triangle-left"   # turnout_rate > SC_X_MAX

    import plotly.graph_objects as go_sc
    fig_scatter = go_sc.Figure()

    _HOVER_TMPL = (
        "<b>%{customdata[0]}</b> · %{customdata[1]}<br>"
        "Turnout: %{customdata[6]:.3f} · Void: %{customdata[7]:.3f}<br>"
        "Tier: %{customdata[2]} · Meta: %{customdata[3]}<br>"
        "Score: %{customdata[4]} · Flags: %{customdata[5]}<br>"
        "Party: %{customdata[8]} · Imputed: %{customdata[9]}<br>"
        "OCR failures: %{customdata[10]}<extra></extra>"
    )
    _CD_COLS = [
        "station_display", "subdistrict_display", "count_tier", "meta_tier",
        "anomaly_score", "flags_triggered",
        "turnout_rate", "void_rate",
        "dominant_party_display", "imputed_display", "failure_modes",
    ]

    for cat in ["Normal",
                "Anomaly (Tier B/C — verify OCR)",
                "Anomaly (Tier A — high confidence)"]:
        sub = scatter_df[scatter_df["category"] == cat].copy()
        if sub.empty:
            continue

        clr = _CAT_COLOR[cat]
        in_range = (
            sub["turnout_rate"].between(0, SC_X_MAX)
            & sub["void_rate"].between(0, SC_Y_MAX)
        )
        sub_in  = sub[in_range]
        sub_out = sub[~in_range].copy()

        # In-range: circles (open for Tier B/C)
        if not sub_in.empty:
            fig_scatter.add_trace(go_sc.Scatter(
                x=sub_in["turnout_rate"], y=sub_in["void_rate"],
                mode="markers",
                name=cat,
                legendgroup=cat,
                marker=dict(
                    color=clr, size=9,
                    symbol=_CAT_SYMBOL_IN[cat],
                    line=dict(color=clr, width=1.5),
                ),
                hovertemplate=_HOVER_TMPL,
                customdata=sub_in[_CD_COLS].values,
            ))

        # Out-of-range: clipped to axis edge, triangle pointing inward
        if not sub_out.empty:
            sub_out["_xc"] = sub_out["turnout_rate"].clip(0, SC_X_MAX)
            sub_out["_yc"] = sub_out["void_rate"].clip(0, SC_Y_MAX)
            sub_out["_sym"] = sub_out.apply(_oor_symbol_scatter, axis=1)
            fig_scatter.add_trace(go_sc.Scatter(
                x=sub_out["_xc"], y=sub_out["_yc"],
                mode="markers",
                name=f"{cat} (outside range)",
                legendgroup=cat,
                showlegend=True,
                marker=dict(
                    color=clr, size=11, opacity=0.75,
                    symbol=sub_out["_sym"].tolist(),
                    line=dict(color="white", width=1),
                ),
                hovertemplate=(
                    "<b>Outside display range</b><br>"
                    + _HOVER_TMPL
                ),
                customdata=sub_out[_CD_COLS].values,
            ))

    n_oor_sc = int((
        ~scatter_df["turnout_rate"].between(0, SC_X_MAX)
        | ~scatter_df["void_rate"].between(0, SC_Y_MAX)
    ).sum())
    oor_sc_note = f" · {n_oor_sc} point(s) outside range shown as ▼/◀ at axis edge" if n_oor_sc else ""

    fig_scatter.update_layout(
        title=(
            f"Turnout rate vs void rate<br>"
            f"<sub>{scatter_cap} </sub>"
        ),
        xaxis=dict(title="Turnout rate", range=[0, SC_X_MAX]),
        yaxis=dict(title="Void rate",    range=[0, SC_Y_MAX]),
        legend_title_text="",
        height=500,
    )
    st.plotly_chart(fig_scatter, use_container_width=True)


    # Station cluster view

    st.subheader("Station clusters")

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

        _, clust_cap = clean_subset(
            cluster_plot[cluster_plot["cluster_label"].notna()],
            count_tier="A", meta_tier=["M0"],
        )

        # --- Compute short descriptive name for each cluster ---
        def _cluster_name(lbl, sub):
            if len(sub) == 1:
                return f"Isolated Outlier (k={lbl})"
            mt = sub["turnout_rate"].mean()
            mv = sub["void_rate"].mean()
            if mt > 1.0:
                t_desc = "OCR-Error Turnout"
            elif mt > 0.75:
                t_desc = "High Turnout"
            elif mt > 0.55:
                t_desc = "Average Turnout"
            else:
                t_desc = "Low Turnout"
            if mv > 0.12:
                v_desc = "High Void"
            elif mv > 0.05:
                v_desc = "Moderate Void"
            else:
                v_desc = "Low Void"
            return f"{t_desc} · {v_desc} (k={lbl})"

        unique_labels = sorted(
            cluster_plot["cluster_label"].dropna().unique().astype(int)
        )

        # Plotly default qualitative palette (circles only)
        _PLOTLY_COLORS = ["#636EFA", "#EF553B", "#00CC96",
                           "#AB63FA", "#FFA15A", "#19D3F3"]

        # Axis display bounds
        X_MIN, X_MAX = 0.4, 1.0
        Y_MIN, Y_MAX = 0.0, 0.2

        import plotly.graph_objects as go_mod
        fig_clust = go_mod.Figure()

        # --- Not-clustered: split into in-range and out-of-range ---
        nc = cluster_plot[cluster_plot["cluster_label"].isna()].copy()
        if not nc.empty:
            in_range = (
                nc["turnout_rate"].between(X_MIN, X_MAX)
                & nc["void_rate"].between(Y_MIN, Y_MAX)
            )
            nc_in  = nc[in_range]
            nc_out = nc[~in_range].copy()

            # In-range not-clustered: grey dots, semi-transparent
            if not nc_in.empty:
                fig_clust.add_trace(go_mod.Scatter(
                    x=nc_in["turnout_rate"], y=nc_in["void_rate"],
                    mode="markers",
                    name="Outside fitting subset",
                    legendgroup="nc",
                    marker=dict(color="#BBBBBB", size=7, opacity=0.45,
                                symbol="circle"),
                    hovertemplate=(
                        "<b>Outside fitting subset</b> · %{customdata[0]}<br>"
                        "Turnout: %{x:.3f} · Void: %{y:.3f}<br>"
                        "Tier: %{customdata[1]} · Meta: %{customdata[2]}"
                        "<extra></extra>"
                    ),
                    customdata=nc_in[["station_display","count_tier","meta_tier"]].values,
                ))

            # Out-of-range not-clustered: clipped to axis boundary, triangle
            # pointing toward the interior so users know the real value is beyond the edge
            if not nc_out.empty:
                nc_out["_xc"] = nc_out["turnout_rate"].clip(X_MIN, X_MAX)
                nc_out["_yc"] = nc_out["void_rate"].clip(Y_MIN, Y_MAX)

                def _oor_symbol(row):
                    if row["void_rate"] > Y_MAX:
                        return "triangle-down"
                    if row["turnout_rate"] < X_MIN:
                        return "triangle-right"
                    return "triangle-left"

                nc_out["_sym"] = nc_out.apply(_oor_symbol, axis=1)
                fig_clust.add_trace(go_mod.Scatter(
                    x=nc_out["_xc"], y=nc_out["_yc"],
                    mode="markers",
                    name="Outside display range",
                    legendgroup="nc",
                    showlegend=True,
                    marker=dict(
                        color="#BBBBBB", opacity=0.6, size=9,
                        symbol=nc_out["_sym"].tolist(),
                        line=dict(color="#888888", width=1),
                    ),
                    hovertemplate=(
                        "<b>Outside display range</b> · %{customdata[0]}<br>"
                        "Actual turnout: %{customdata[3]:.3f} · "
                        "Actual void: %{customdata[4]:.3f}<br>"
                        "Tier: %{customdata[1]} · Meta: %{customdata[2]}"
                        "<extra></extra>"
                    ),
                    customdata=nc_out[[
                        "station_display","count_tier","meta_tier",
                        "turnout_rate","void_rate",
                    ]].values,
                ))

        # --- One trace per cluster: circle dots, Plotly default colors ---
        for i, lbl in enumerate(unique_labels):
            sub = cluster_plot[cluster_plot["cluster_label"] == lbl]
            name = _cluster_name(lbl, sub)
            clr  = _PLOTLY_COLORS[i % len(_PLOTLY_COLORS)]
            fig_clust.add_trace(go_mod.Scatter(
                x=sub["turnout_rate"], y=sub["void_rate"],
                mode="markers",
                name=name,
                marker=dict(color=clr, symbol="circle", size=10,
                            line=dict(color="white", width=1)),
                hovertemplate=(
                    f"<b>{name}</b> · %{{customdata[0]}}<br>"
                    "Turnout: %{x:.3f} · Void: %{y:.3f}<br>"
                    "Tier: %{customdata[1]} · Party: %{customdata[2]}<br>"
                    "Imputed: %{customdata[3]}<extra></extra>"
                ),
                customdata=sub[[
                    "station_display","count_tier",
                    "dominant_party_display","imputed_display",
                ]].values,
            ))

        n_oor = int((~nc["turnout_rate"].between(X_MIN, X_MAX)
                     | ~nc["void_rate"].between(Y_MIN, Y_MAX)).sum()) if not nc.empty else 0

        fig_clust.update_layout(
            title=(
                f"Station clusters (KMeans, k chosen by silhouette)<br>"
                f"<sub>fitted: {clust_cap}</sub>"
            ),
            xaxis=dict(title="Turnout rate", range=[X_MIN, X_MAX]),
            yaxis=dict(title="Void rate",    range=[Y_MIN, Y_MAX]),
            legend_title="",
            height=500,
        )
        st.plotly_chart(fig_clust, use_container_width=True)

    st.divider()

    # -----------------------------------------------------------------------
    # Section D — Detail table
    # -----------------------------------------------------------------------
    st.subheader("Anomalous records detail")

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
