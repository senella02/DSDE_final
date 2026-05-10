"""
EDA tab — two sections:
  A: Distributions (full vs valid-only side-by-side, highlighting OCR bias)
  B: Rankings (top/bottom stations, top candidates, party leaderboard)
"""

import streamlit as st
import pandas as pd
import plotly.express as px

from lib import clean_subset, color


# ── helpers ────────────────────────────────────────────────────────────────


def _cand_base(candidates: pd.DataFrame, ballot_type: str) -> pd.DataFrame:
    """Non-withdrawn candidates with non-null votes for a ballot type."""
    mask = (
        (candidates["ballot_type"] == ballot_type)
        & candidates["votes"].notna()
        & (candidates["withdrawn"].fillna(False) == False)
    )
    return candidates[mask]


def _party_bar(df: pd.DataFrame, cap: str, title: str) -> None:
    party_totals = (
        df.groupby("party")["votes"]
        .sum()
        .sort_values(ascending=True)
        .reset_index()
    )
    cmap = {p: color(p) for p in party_totals["party"].unique()}
    fig = px.bar(
        party_totals, x="votes", y="party", orientation="h",
        title=f"{title}<br><sub>{cap}</sub>",
        labels={"votes": "Total Votes", "party": ""},
        color="party", color_discrete_map=cmap,
        text=party_totals["votes"].map(lambda x: f"{x:,.0f}"),
    )
    fig.update_layout(showlegend=False, margin={"l": 200})
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)


def render(
    records: pd.DataFrame,
    candidates: pd.DataFrame,
    pages: pd.DataFrame,
    official: pd.DataFrame,
) -> None:
    st.header("Exploratory Data Analysis")

    # ── Section A: Distributions ──────────────────────────────────────────
    st.subheader("A — Distributions")
    st.caption(
        "Each metric shown **side-by-side**: all records with that field (left) vs "
        "Tier A+B only (right). A meaningful shift means OCR failures are non-random "
        "and bias the result — that difference is itself a finding."
    )

    # A1 — Turnout rate
    st.markdown("**Turnout Rate**")
    col_l, col_r = st.columns(2)
    full_t, cap_full_t = clean_subset(records, requires=["turnout_rate"])
    valid_t, cap_valid_t = clean_subset(records, count_tier="AB", requires=["turnout_rate"])
    with col_l:
        fig = px.histogram(
            full_t, x="turnout_rate", nbins=40,
            title=f"Turnout Rate — All<br><sub>{cap_full_t}</sub>",
            labels={"turnout_rate": "Turnout Rate"},
            hover_data=["count_tier", "meta_tier", "failure_modes"],
        )
        st.plotly_chart(fig, use_container_width=True)
    with col_r:
        fig = px.histogram(
            valid_t, x="turnout_rate", nbins=40,
            title=f"Turnout Rate — Tier A+B<br><sub>{cap_valid_t}</sub>",
            labels={"turnout_rate": "Turnout Rate"},
            color_discrete_sequence=["#2ecc71"],
            hover_data=["count_tier", "meta_tier", "failure_modes"],
        )
        st.plotly_chart(fig, use_container_width=True)

    # A2 — Void rate
    st.markdown("**Void Rate (บัตรเสีย / total)**")
    col_l, col_r = st.columns(2)
    full_v, cap_full_v = clean_subset(records, requires=["void_rate"])
    valid_v, cap_valid_v = clean_subset(records, count_tier="AB", requires=["void_rate"])
    with col_l:
        fig = px.histogram(
            full_v, x="void_rate", nbins=40,
            title=f"Void Rate — All<br><sub>{cap_full_v}</sub>",
            labels={"void_rate": "Void Rate"},
            color_discrete_sequence=["#e74c3c"],
            hover_data=["count_tier", "meta_tier", "failure_modes"],
        )
        st.plotly_chart(fig, use_container_width=True)
    with col_r:
        fig = px.histogram(
            valid_v, x="void_rate", nbins=40,
            title=f"Void Rate — Tier A+B<br><sub>{cap_valid_v}</sub>",
            labels={"void_rate": "Void Rate"},
            color_discrete_sequence=["#e74c3c"],
            hover_data=["count_tier", "meta_tier", "failure_modes"],
        )
        st.plotly_chart(fig, use_container_width=True)

    # A3 — Spoil rate
    st.markdown("**Spoil Rate (งดออกเสียง / total)**")
    col_l, col_r = st.columns(2)
    full_s, cap_full_s = clean_subset(records, requires=["spoil_rate"])
    valid_s, cap_valid_s = clean_subset(records, count_tier="AB", requires=["spoil_rate"])
    with col_l:
        fig = px.histogram(
            full_s, x="spoil_rate", nbins=40,
            title=f"Spoil Rate — All<br><sub>{cap_full_s}</sub>",
            labels={"spoil_rate": "Spoil Rate"},
            color_discrete_sequence=["#f39c12"],
            hover_data=["count_tier", "meta_tier", "failure_modes"],
        )
        st.plotly_chart(fig, use_container_width=True)
    with col_r:
        fig = px.histogram(
            valid_s, x="spoil_rate", nbins=40,
            title=f"Spoil Rate — Tier A+B<br><sub>{cap_valid_s}</sub>",
            labels={"spoil_rate": "Spoil Rate"},
            color_discrete_sequence=["#f39c12"],
            hover_data=["count_tier", "meta_tier", "failure_modes"],
        )
        st.plotly_chart(fig, use_container_width=True)

    # A4 — District vote share by party
    st.markdown("**District Vote Share by Party**")
    dist_base = _cand_base(candidates, "district")
    full_d, cap_full_d = clean_subset(dist_base)
    valid_d, cap_valid_d = clean_subset(dist_base, count_tier="A")
    col_l, col_r = st.columns(2)
    with col_l:
        _party_bar(full_d, cap_full_d, "District Vote Share — All Tiers")
    with col_r:
        _party_bar(valid_d, cap_valid_d, "District Vote Share — Tier A Only")

    # A5 — Partylist vote share by party
    st.markdown("**Partylist Vote Share by Party**")
    pl_base = _cand_base(candidates, "partylist")
    full_p, cap_full_p = clean_subset(pl_base)
    valid_p, cap_valid_p = clean_subset(pl_base, count_tier="A")
    col_l, col_r = st.columns(2)
    with col_l:
        _party_bar(full_p, cap_full_p, "Partylist Vote Share — All Tiers")
    with col_r:
        _party_bar(valid_p, cap_valid_p, "Partylist Vote Share — Tier A Only")

    # A6 — Turnout vs void scatter colored by count_tier
    scat_sub, scat_cap = clean_subset(records, requires=["turnout_rate", "void_rate"])
    tier_colors = {"A": "#2ecc71", "B": "#f39c12", "C": "#e74c3c"}
    fig_scat = px.scatter(
        scat_sub, x="turnout_rate", y="void_rate",
        color="count_tier", color_discrete_map=tier_colors,
        title=f"Turnout vs Void Rate by Count Tier<br><sub>{scat_cap}</sub>",
        labels={
            "turnout_rate": "Turnout Rate",
            "void_rate": "Void Rate",
            "count_tier": "Count Tier",
        },
        hover_data=["ballot_type", "election_type", "meta_tier", "failure_modes"],
    )
    st.plotly_chart(fig_scat, use_container_width=True)

    st.divider()

    # ── Section B: Rankings ───────────────────────────────────────────────
    st.subheader("B — Rankings")
    st.caption(
        "All ranking tables include `count_tier`, `meta_tier`, and `imputed_fields` "
        "so you can judge OCR trustworthiness at a glance."
    )

    _STATION_COLS = [
        "station_number", "subdistrict", "district",
        "ballot_type", "election_type",
        "count_tier", "meta_tier", "imputed_fields", "failure_mode_count",
    ]

    # B1 — Top/bottom 15 stations by void rate
    st.markdown("**Top & Bottom 15 Stations by Void Rate (Tier A+B, M0)**")
    void_sub, void_cap = clean_subset(
        records,
        count_tier="AB",
        meta_tier=["M0"],
        requires=["void_rate"],
    )
    st.caption(void_cap)
    if len(void_sub) >= 2:
        top_void = void_sub.nlargest(15, "void_rate")[_STATION_COLS + ["void_rate"]].sort_values("void_rate", ascending=False)
        bot_void = void_sub.nsmallest(15, "void_rate")[_STATION_COLS + ["void_rate"]].sort_values("void_rate")
        col_l, col_r = st.columns(2)
        with col_l:
            st.write("Top 15 — highest void rate")
            st.dataframe(top_void, use_container_width=True, hide_index=True)
        with col_r:
            st.write("Bottom 15 — lowest void rate")
            st.dataframe(bot_void, use_container_width=True, hide_index=True)
    else:
        st.info("Too few valid M0 records to rank stations by void rate.")

    # B2 — Top/bottom 15 stations by turnout rate
    st.markdown("**Top & Bottom 15 Stations by Turnout Rate (Tier A+B, M0)**")
    turn_sub, turn_cap = clean_subset(
        records,
        count_tier="AB",
        meta_tier=["M0"],
        requires=["turnout_rate"],
    )
    st.caption(turn_cap)
    if len(turn_sub) >= 2:
        top_turn = turn_sub.nlargest(15, "turnout_rate")[_STATION_COLS + ["turnout_rate"]].sort_values("turnout_rate", ascending=False)
        bot_turn = turn_sub.nsmallest(15, "turnout_rate")[_STATION_COLS + ["turnout_rate"]].sort_values("turnout_rate")
        col_l, col_r = st.columns(2)
        with col_l:
            st.write("Top 15 — highest turnout")
            st.dataframe(top_turn, use_container_width=True, hide_index=True)
        with col_r:
            st.write("Bottom 15 — lowest turnout")
            st.dataframe(bot_turn, use_container_width=True, hide_index=True)
    else:
        st.info("Too few valid M0 records to rank stations by turnout rate.")

    # B3 — Top 10 candidates by votes (district, Tier A)
    st.markdown("**Top 10 District Candidates by Votes (Tier A)**")
    dist_a, cap_dist_a = clean_subset(_cand_base(candidates, "district"), count_tier="A")
    top_cands = (
        dist_a.groupby(["number", "name", "party"])["votes"]
        .sum()
        .reset_index()
        .nlargest(10, "votes")
        .sort_values("votes", ascending=True)
    )
    cmap_c = {p: color(p) for p in top_cands["party"].unique()}
    fig_b3 = px.bar(
        top_cands, x="votes", y="name", orientation="h",
        title=f"Top 10 District Candidates by Votes<br><sub>{cap_dist_a}</sub>",
        labels={"votes": "Total Votes", "name": "Candidate"},
        color="party", color_discrete_map=cmap_c,
        text=top_cands["votes"].map(lambda x: f"{x:,.0f}"),
        hover_data=["party", "number"],
    )
    fig_b3.update_layout(margin={"l": 160})
    fig_b3.update_traces(textposition="outside")
    st.plotly_chart(fig_b3, use_container_width=True)

    cand_table = top_cands.sort_values("votes", ascending=False).copy()
    cand_table["rank"] = range(1, len(cand_table) + 1)
    cand_table["votes"] = cand_table["votes"].map(lambda x: f"{x:,.0f}")
    cand_table = cand_table[["rank", "number", "name", "party", "votes"]]
    cand_table.columns = ["Rank", "#", "Name", "Party", "Votes (Tier A)"]
    st.dataframe(cand_table, use_container_width=True, hide_index=True)

    # B4 — Party leaderboard (partylist, Tier A)
    st.markdown("**Party Leaderboard — Partylist (Tier A)**")
    pl_a, cap_pl_a = clean_subset(_cand_base(candidates, "partylist"), count_tier="A")
    party_board = (
        pl_a.groupby("party")["votes"]
        .sum()
        .reset_index()
        .sort_values("votes", ascending=False)
        .reset_index(drop=True)
    )
    party_board["rank"] = party_board.index + 1
    total_pl = party_board["votes"].sum()
    party_board["pct"] = (party_board["votes"] / total_pl * 100).round(2) if total_pl else 0.0

    cmap_p = {p: color(p) for p in party_board["party"].unique()}
    fig_b4 = px.bar(
        party_board.sort_values("votes", ascending=True),
        x="votes", y="party", orientation="h",
        title=f"Partylist Votes by Party<br><sub>{cap_pl_a}</sub>",
        labels={"votes": "Total Votes", "party": ""},
        color="party", color_discrete_map=cmap_p,
        text=party_board.sort_values("votes", ascending=True)["pct"].map(lambda x: f"{x:.1f}%"),
    )
    fig_b4.update_layout(showlegend=False, margin={"l": 200})
    fig_b4.update_traces(textposition="outside")
    st.plotly_chart(fig_b4, use_container_width=True)

    pl_table = party_board[["rank", "party", "votes", "pct"]].copy()
    pl_table["votes"] = pl_table["votes"].map(lambda x: f"{x:,.0f}")
    pl_table["pct"] = pl_table["pct"].map(lambda x: f"{x:.2f}%")
    pl_table.columns = ["Rank", "Party", "Votes (Tier A)", "% of Valid Partylist Votes"]
    st.dataframe(pl_table, use_container_width=True, hide_index=True)
