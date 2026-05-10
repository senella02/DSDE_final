"""
Data Quality tab — three sections:
  A: Failure mode analysis (frequency, null rates, co-occurrence, clustering)
  B: OCR accuracy vs official government results (aggregate + candidate level)
  C: Spot-check queue with CSV downloads
"""

import streamlit as st
import pandas as pd
import plotly.express as px

from lib import clean_subset, REPORTS_DIR

_HEADER_FIELDS = [
    "total_ballots", "valid_votes", "void_ballots", "spoiled_ballots",
    "eligible_voters", "voter_turnout", "station_number", "district", "subdistrict", "moo",
]
_BALLOT_FIELDS = ["valid_votes", "void_ballots", "spoiled_ballots", "total_ballots"]

# Minimum fraction of contributing records that must be tier-A for a candidate to "pass QA"
_QA_PASS_THRESHOLD = 0.5
# Absolute vote-count error considered "matches official"
_MATCH_THRESHOLD = 50


def _parse_modes(series: pd.Series) -> list[list[str]]:
    """Return list-of-lists of normalised mode base names from a pipe-separated column."""
    result: list[list[str]] = []
    for val in series:
        if not val or (isinstance(val, float) and pd.isna(val)):
            result.append([])
            continue
        modes: list[str] = []
        for raw in str(val).split("|"):
            raw = raw.strip()
            if not raw:
                continue
            # strip parenthetical: "candidate_sum_fail (sum=...)" → "candidate_sum_fail"
            base = raw.split("(")[0].strip()
            # strip bracket detail: "ocr_missed_candidates:[1,2]" → "ocr_missed_candidates"
            base = base.split("[")[0].strip().rstrip(":")
            if base:
                modes.append(base)
        result.append(modes)
    return result


def _off_total(official: pd.DataFrame, bt: str) -> dict:
    """Return official ballot totals for a given ballot_type."""
    rows = official[official["ballot_type"] == bt]
    if rows.empty:
        return {f: 0 for f in _BALLOT_FIELDS}
    r = rows.iloc[0]
    return {f: int(r.get(f"official_{f}", 0) or 0) for f in _BALLOT_FIELDS}


def render(
    records: pd.DataFrame,
    candidates: pd.DataFrame,
    pages: pd.DataFrame,
    official: pd.DataFrame,
) -> None:
    st.header("Data Quality")

    # ── Section A: Failure mode analysis ──────────────────────────────────
    st.subheader("A — Failure Mode Analysis")

    modes_lists = _parse_modes(records["failure_modes"])
    all_modes_flat = [m for lst in modes_lists for m in lst]
    unique_modes = sorted(set(all_modes_flat))

    # A1 — frequency bar (all records, sorted descending)
    mode_counts = (
        pd.Series(all_modes_flat)
        .value_counts()
        .reset_index()
        .rename(columns={"index": "mode", 0: "count", "count": "count"})
    )
    mode_counts.columns = ["mode", "count"]
    mode_counts["pct"] = (mode_counts["count"] / len(records) * 100).round(1)

    fig_a1 = px.bar(
        mode_counts,
        x="count", y="mode", orientation="h",
        text=mode_counts["pct"].map(lambda x: f"{x:.1f}%"),
        title=f"Failure Mode Frequency<br><sub>n={len(records)}/{len(records)} • all rows</sub>",
        labels={"count": "# Records affected", "mode": ""},
        color="count", color_continuous_scale="Reds",
    )
    fig_a1.update_layout(
        yaxis={"categoryorder": "total ascending"},
        coloraxis_showscale=False,
        margin={"l": 220},
    )
    fig_a1.update_traces(textposition="outside")
    st.plotly_chart(fig_a1, width='stretch')

    # A2 — null rate per header field (horizontal bar, sorted by count)
    null_df = (
        records[_HEADER_FIELDS].isnull().sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    null_df.columns = ["field", "null_count"]
    null_df["null_pct"] = (null_df["null_count"] / len(records) * 100).round(1)

    fig_a2 = px.bar(
        null_df,
        x="null_count", y="field", orientation="h",
        text=null_df["null_pct"].map(lambda x: f"{x:.1f}%"),
        title=f"Null Rate per Header Field<br><sub>n={len(records)}/{len(records)} • all rows</sub>",
        labels={"null_count": "# Null Records", "field": ""},
        color="null_count", color_continuous_scale="Oranges",
    )
    fig_a2.update_layout(
        yaxis={"categoryorder": "total ascending"},
        coloraxis_showscale=False,
        margin={"l": 160},
    )
    fig_a2.update_traces(textposition="outside")
    st.plotly_chart(fig_a2, width='stretch')

    col_a3, col_a4 = st.columns(2)

    # A3 — failures-per-record histogram
    with col_a3:
        fig_a3 = px.histogram(
            records, x="failure_mode_count",
            color_discrete_sequence=["#EF553B"],
            title=f"Failures per Record<br><sub>n={len(records)}/{len(records)} • all rows</sub>",
            labels={"failure_mode_count": "# Failure Modes", "count": "# Records"},
        )
        fig_a3.update_layout(bargap=0.15)
        st.plotly_chart(fig_a3, width='stretch')

    # A4 — co-occurrence heatmap
    with col_a4:
        if len(unique_modes) >= 2:
            cooccur = pd.DataFrame(0, index=unique_modes, columns=unique_modes, dtype=int)
            for lst in modes_lists:
                for i, a in enumerate(lst):
                    for b in lst[i:]:
                        cooccur.loc[a, b] += 1
                        if a != b:
                            cooccur.loc[b, a] += 1

            fig_a4 = px.imshow(
                cooccur, text_auto=True,
                title="Failure Mode Co-occurrence<br><sub>Cell = # records sharing both modes</sub>",
                color_continuous_scale="Blues", aspect="auto",
            )
            fig_a4.update_layout(margin={"l": 220, "b": 180})
            st.plotly_chart(fig_a4, width='stretch')
        else:
            st.info("Too few distinct failure modes for co-occurrence heatmap.")

    # Clustering table — do failures concentrate by ballot type / election type?
    st.markdown(
        "**Failure clustering by ballot type and election type.** "
        "Systematic concentration → physical scanning or printing issue, not random OCR noise."
    )
    cluster = (
        records.groupby(["ballot_type", "election_type"])
        .agg(
            n_records=("failure_mode_count", "count"),
            avg_failures=("failure_mode_count", "mean"),
            pct_any_failure=("failure_mode_count", lambda x: round((x > 0).mean() * 100, 1)),
            pct_tier_c=("count_tier", lambda x: round((x == "C").mean() * 100, 1)),
        )
        .reset_index()
    )
    st.dataframe(cluster, width='stretch', hide_index=True)

    st.divider()

    # ── Section B: OCR accuracy vs official ───────────────────────────────
    st.subheader("B — OCR Accuracy vs Official Government Results")
    st.caption(
        "Official results are constituency-level totals. "
        "OCR per-station records are summed and compared across three quality subsets: "
        "**All records**, **Tier A+B** (ballot math valid), and **Tier A** (all checks pass). "
        "A large shift between subsets means OCR failures are non-random."
    )

    # ── B1: Aggregate ballot-field comparison per ballot type ──────────────
    all_records, _ = clean_subset(records)
    ab_records, cap_ab = clean_subset(records, count_tier="AB")
    a_records, cap_a = clean_subset(records, count_tier="A")

    for bt in ["district", "partylist"]:
        st.write(f"**{bt.capitalize()} ballot**")

        off = _off_total(official, bt)
        r_all = all_records[all_records["ballot_type"] == bt]
        r_ab = ab_records[ab_records["ballot_type"] == bt]
        r_a = a_records[a_records["ballot_type"] == bt]

        cmp_rows = []
        for f in _BALLOT_FIELDS:
            ocr_all = int(r_all[f].sum(skipna=True))
            ocr_ab = int(r_ab[f].sum(skipna=True))
            ocr_a = int(r_a[f].sum(skipna=True))
            off_val = off[f]
            cmp_rows.append({
                "field": f,
                f"OCR all (n={len(r_all)})": ocr_all,
                f"OCR tier A+B (n={len(r_ab)})": ocr_ab,
                f"OCR tier A (n={len(r_a)})": ocr_a,
                "Official": off_val,
                "Error all %": round((ocr_all - off_val) / off_val * 100, 2) if off_val else None,
                "Error A+B %": round((ocr_ab - off_val) / off_val * 100, 2) if off_val else None,
            })

        cmp_df = pd.DataFrame(cmp_rows)
        st.dataframe(cmp_df, width='stretch', hide_index=True)

        melt = cmp_df.melt(
            id_vars="field",
            value_vars=[f"OCR all (n={len(r_all)})", f"OCR tier A+B (n={len(r_ab)})", "Official"],
            var_name="source", value_name="value",
        )
        fig_cmp = px.bar(
            melt, x="field", y="value", color="source", barmode="group",
            title=(
                f"{bt.capitalize()} ballot: OCR vs Official Ballot Counts"
                f"<br><sub>All n={len(r_all)} | A+B n={len(r_ab)} | Official (constituency total)</sub>"
            ),
            labels={"value": "Vote Count", "field": "Ballot Field", "source": ""},
        )
        st.plotly_chart(fig_cmp, width='stretch')

    # ── B2: Candidate-level comparison ─────────────────────────────────────
    st.write("**Per-Candidate Vote Error (OCR aggregate vs Official)**")

    # Sum OCR candidate votes across all contributing records (exclude withdrawn)
    cand_ocr = (
        candidates[candidates["votes"].notna() & (candidates["withdrawn"].fillna(False) == False)]
        .groupby(["ballot_type", "number"])["votes"]
        .sum()
        .reset_index()
        .rename(columns={"votes": "ocr_votes"})
    )
    cand_merged = cand_ocr.merge(
        official[["ballot_type", "number", "name", "party", "official_votes"]],
        on=["ballot_type", "number"], how="inner",
    )
    cand_merged["abs_error"] = (cand_merged["ocr_votes"] - cand_merged["official_votes"]).abs()
    cand_merged["signed_error"] = cand_merged["ocr_votes"] - cand_merged["official_votes"]
    cand_merged["rel_error_pct"] = (
        cand_merged["abs_error"] / cand_merged["official_votes"].clip(lower=1) * 100
    ).round(2)

    col_b1, col_b2 = st.columns(2)

    # Box plot: relative error by ballot_type
    with col_b1:
        fig_b1 = px.box(
            cand_merged, x="ballot_type", y="rel_error_pct",
            title=(
                f"Candidate Vote Error: OCR vs Official"
                f"<br><sub>n={len(cand_merged)}/{len(cand_merged)} • all candidates</sub>"
            ),
            labels={"rel_error_pct": "Abs. Error %", "ballot_type": "Ballot Type"},
            points="all",
            hover_data=["name", "party", "ocr_votes", "official_votes"],
        )
        st.plotly_chart(fig_b1, width='stretch')

    # Error magnitude buckets
    with col_b2:
        buckets = pd.cut(
            cand_merged["abs_error"],
            bins=[-1, 5, 50, 500, float("inf")],
            labels=["<5", "<50", "<500", "500+"],
        )
        bkt_df = (
            buckets.value_counts()
            .reindex(["<5", "<50", "<500", "500+"], fill_value=0)
            .reset_index()
        )
        bkt_df.columns = ["bucket", "count"]
        bkt_df["pct"] = (bkt_df["count"] / len(cand_merged) * 100).round(1)

        fig_b2 = px.bar(
            bkt_df, x="bucket", y="pct",
            text=bkt_df["pct"].map(lambda x: f"{x:.1f}%"),
            title=(
                "Error Magnitude Buckets"
                f"<br><sub>n={len(cand_merged)}/{len(cand_merged)} • all candidates</sub>"
            ),
            labels={"bucket": "Absolute Vote Error", "pct": "% of Candidates"},
            color="bucket",
            color_discrete_sequence=["#2ecc71", "#f39c12", "#e74c3c", "#8e44ad"],
        )
        fig_b2.update_layout(showlegend=False)
        fig_b2.update_traces(textposition="outside")
        st.plotly_chart(fig_b2, width='stretch')

    # ── B3: QA calibration 2×2 ─────────────────────────────────────────────
    st.write(
        f"**QA Flag Calibration** — "
        f"passes QA = majority of contributing OCR records are tier A; "
        f"matches official = |error| ≤ {_MATCH_THRESHOLD} votes."
    )

    # Fraction of tier-A records per (ballot_type, candidate number)
    cand_tiers = (
        candidates[candidates["withdrawn"].fillna(False) == False]
        .groupby(["ballot_type", "number"])["count_tier"]
        .apply(lambda x: (x == "A").mean())
        .reset_index()
        .rename(columns={"count_tier": "pct_tier_a"})
    )
    qa_df = cand_merged.merge(cand_tiers, on=["ballot_type", "number"], how="left")
    qa_df["passes_qa"] = qa_df["pct_tier_a"] >= _QA_PASS_THRESHOLD
    qa_df["matches_official"] = qa_df["abs_error"] <= _MATCH_THRESHOLD

    qa_matrix = (
        qa_df.groupby(["passes_qa", "matches_official"])
        .size()
        .unstack(fill_value=0)
        .rename(columns={True: "Matches official", False: "Differs from official"})
        .rename(index={True: "Passes QA", False: "Fails QA"})
    )

    # Ensure all four cells exist
    for col in ["Matches official", "Differs from official"]:
        if col not in qa_matrix.columns:
            qa_matrix[col] = 0
    for idx in ["Passes QA", "Fails QA"]:
        if idx not in qa_matrix.index:
            qa_matrix.loc[idx] = 0

    qa_matrix = qa_matrix.loc[["Passes QA", "Fails QA"], ["Matches official", "Differs from official"]]

    tp = qa_matrix.loc["Passes QA", "Matches official"]
    fn = qa_matrix.loc["Passes QA", "Differs from official"]
    fp = qa_matrix.loc["Fails QA", "Matches official"]
    tn = qa_matrix.loc["Fails QA", "Differs from official"]

    st.markdown(
        f"- **True Positives** (pass QA & match official): **{tp}**  \n"
        f"- **False Negatives** (pass QA but differ from official): **{fn}** ← QA misses these errors  \n"
        f"- **False Positives** (fail QA but match official): **{fp}** ← QA over-flags these  \n"
        f"- **True Negatives** (fail QA & differ from official): **{tn}**"
    )

    fig_b3 = px.imshow(
        qa_matrix, text_auto=True,
        title=(
            "QA Calibration: Pass/Fail × Matches/Differs Official"
            f"<br><sub>n={len(qa_df)}/{len(cand_merged)} • all candidates, threshold={_MATCH_THRESHOLD} votes</sub>"
        ),
        color_continuous_scale="Greens", aspect="auto",
        labels={"x": "", "y": ""},
    )
    st.plotly_chart(fig_b3, width='stretch')

    # ── B4: OCR latency by page role ───────────────────────────────────────
    sub_pages, cap_pages = clean_subset(pages, requires=["page_role", "ocr_latency_sec"])
    fig_b4 = px.box(
        sub_pages, x="page_role", y="ocr_latency_sec",
        title=f"OCR Latency by Page Role<br><sub>{cap_pages}</sub>",
        labels={"ocr_latency_sec": "Latency (sec)", "page_role": "Page Role"},
        points="outliers",
    )
    st.plotly_chart(fig_b4, width='stretch')

    # Export accuracy_report.csv
    REPORTS_DIR.mkdir(exist_ok=True)
    acc_csv = cand_merged.to_csv(index=False, encoding="utf-8-sig")
    (REPORTS_DIR / "accuracy_report.csv").write_bytes(acc_csv.encode("utf-8-sig"))

    st.download_button(
        "Download accuracy_report.csv",
        data=acc_csv.encode("utf-8-sig"),
        file_name="accuracy_report.csv",
        mime="text/csv",
    )

    st.divider()

    # ── Section C: Spot-check queue ────────────────────────────────────────
    st.subheader("C — Spot-Check Queue")

    spotcheck = (
        records[(records["count_tier"] == "C") | (records["failure_mode_count"] >= 3)]
        .sort_values("failure_mode_count", ascending=False)
        .reset_index(drop=True)
    )

    st.write(f"**{len(spotcheck)} records** flagged for manual review (count_tier=C or ≥3 failure modes)")

    show_cols = [
        "file_id", "ballot_type", "election_type",
        "district", "subdistrict", "station_number",
        "count_tier", "meta_tier", "failure_mode_count", "failure_modes", "imputed_fields",
    ]

    st.dataframe(spotcheck[show_cols], use_container_width=True, hide_index=True)

    # Export CSVs
    dq_csv = records.to_csv(index=False, encoding="utf-8-sig")
    sq_csv = spotcheck.to_csv(index=False, encoding="utf-8-sig")
    (REPORTS_DIR / "data_quality_report.csv").write_bytes(dq_csv.encode("utf-8-sig"))
    (REPORTS_DIR / "spotcheck_queue.csv").write_bytes(sq_csv.encode("utf-8-sig"))

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            "Download spotcheck_queue.csv",
            data=sq_csv.encode("utf-8-sig"),
            file_name="spotcheck_queue.csv",
            mime="text/csv",
        )
    with col_dl2:
        st.download_button(
            "Download data_quality_report.csv",
            data=dq_csv.encode("utf-8-sig"),
            file_name="data_quality_report.csv",
            mime="text/csv",
        )
