import streamlit as st
import pandas as pd


def render(records: pd.DataFrame, candidates: pd.DataFrame, pages: pd.DataFrame, official: pd.DataFrame) -> None:
    st.info("🚧 EDA tab — placeholder (assigned to another team member)")
import plotly.express as px
import plotly.graph_objects as go
from lib import clean_subset, color

import streamlit as st


def _side_by_side_hist(
    records: pd.DataFrame, col: str, xlabel: str, title_prefix: str, **gate_kw
) -> None:
    """Render full-data vs valid-only histograms side-by-side."""
    full, full_cap = clean_subset(records, **gate_kw)
    valid, valid_cap = clean_subset(records, count_tier="AB", **gate_kw)

    c1, c2 = st.columns(2)
    for sub, cap, col_obj, label in [
        (full, full_cap, c1, "ข้อมูลทั้งหมด"),
        (valid, valid_cap, c2, "เฉพาะ Tier AB"),
    ]:
        sub_clean = sub.dropna(subset=[col])
        fig = px.histogram(
            sub_clean,
            x=col,
            nbins=30,
            title=f"{title_prefix} — {label}<br><sub>{cap}</sub>",
            labels={col: xlabel, "count": "จำนวน"},
            color_discrete_sequence=["#3498db" if label == "ข้อมูลทั้งหมด" else "#2ecc71"],
        )
        col_obj.plotly_chart(fig, width="stretch")


def render(
    records: pd.DataFrame,
    candidates: pd.DataFrame,
    pages: pd.DataFrame,
    official: pd.DataFrame,
) -> None:

    # ══════════════════════════════════════════════════════════════
    # SECTION A — Distributions
    # ══════════════════════════════════════════════════════════════
    st.subheader("A · การกระจายของตัวชี้วัดหลัก")
    st.caption(
        "แต่ละเมตริกแสดงคู่: ข้อมูลทั้งหมด (ซ้าย) vs Tier AB เท่านั้น (ขวา) — ผลต่างบ่งบอก OCR bias"
    )

    _side_by_side_hist(
        records[records["election_type"] == "normal"],
        col="turnout_rate",
        xlabel="อัตราผู้ใช้สิทธิ์",
        title_prefix="Turnout Rate",
        requires=["turnout_rate"],
    )
    _side_by_side_hist(
        records[records["election_type"] == "normal"],
        col="void_rate",
        xlabel="สัดส่วนบัตรเสีย",
        title_prefix="Void Rate",
        requires=["void_rate"],
    )
    _side_by_side_hist(
        records[records["election_type"] == "normal"],
        col="spoil_rate",
        xlabel="สัดส่วนบัตรไม่เลือก",
        title_prefix="Spoil Rate",
        requires=["spoil_rate"],
    )

    st.divider()

    # District vote share by party (Tier A)
    dist_cand, dist_cap = clean_subset(
        candidates[candidates["ballot_type"] == "district"],
        count_tier="A",
        requires=["votes"],
    )
    if len(dist_cand) > 0:
        party_share = (
            dist_cand.groupby("party")["votes"]
            .sum()
            .reset_index()
            .sort_values("votes", ascending=False)
        )
        party_share["color"] = party_share["party"].map(color)
        fig_dist = px.bar(
            party_share.head(15),
            x="party",
            y="votes",
            color="party",
            color_discrete_map={p: color(p) for p in party_share["party"]},
            title=f"สัดส่วนคะแนนพรรค (บัตรเขต) — ทุกหน่วย<br><sub>{dist_cap}</sub>",
            labels={"party": "พรรค", "votes": "คะแนนรวม"},
        )
        fig_dist.update_layout(showlegend=False, xaxis_tickangle=-40)
        st.plotly_chart(fig_dist, width="stretch")

    # Partylist vote share by party (Tier A)
    pl_cand, pl_cap = clean_subset(
        candidates[candidates["ballot_type"] == "partylist"],
        count_tier="A",
        requires=["votes"],
    )
    if len(pl_cand) > 0:
        pl_share = (
            pl_cand.groupby("party")["votes"]
            .sum()
            .reset_index()
            .sort_values("votes", ascending=False)
        )
        fig_pl = px.bar(
            pl_share.head(15),
            x="party",
            y="votes",
            color="party",
            color_discrete_map={p: color(p) for p in pl_share["party"]},
            title=f"สัดส่วนคะแนนพรรค (บัตรบัญชีรายชื่อ)<br><sub>{pl_cap}</sub>",
            labels={"party": "พรรค", "votes": "คะแนนรวม"},
        )
        fig_pl.update_layout(showlegend=False, xaxis_tickangle=-40)
        st.plotly_chart(fig_pl, width="stretch")

    # Turnout vs void scatter colored by count_tier
    scatter_sub, scatter_cap = clean_subset(
        records, requires=["turnout_rate", "void_rate"]
    )
    if len(scatter_sub) > 0:
        fig_scatter = px.scatter(
            scatter_sub,
            x="turnout_rate",
            y="void_rate",
            color="count_tier",
            color_discrete_map={"A": "#2ecc71", "B": "#f39c12", "C": "#e74c3c"},
            hover_data=[
                "district",
                "subdistrict",
                "station_number",
                "ballot_type",
                "failure_modes",
            ],
            title=f"Turnout vs Void Rate — สีตาม Count Tier<br><sub>{scatter_cap}</sub>",
            labels={
                "turnout_rate": "อัตราผู้ใช้สิทธิ์",
                "void_rate": "สัดส่วนบัตรเสีย",
                "count_tier": "Count Tier",
            },
        )
        st.plotly_chart(fig_scatter, width="stretch")

    st.divider()

    # ══════════════════════════════════════════════════════════════
    # SECTION B — Rankings
    # ══════════════════════════════════════════════════════════════
    st.subheader("B · อันดับสถานี พรรค และผู้สมัคร")

    rank_sub, rank_cap = clean_subset(
        records[records["election_type"] == "normal"],
        count_tier="AB",
        meta_tier=["M0"],
        requires=["void_rate", "turnout_rate"],
    )

    col_v, col_t = st.columns(2)

    with col_v:
        top_void = rank_sub.nlargest(15, "void_rate")[
            [
                "district",
                "subdistrict",
                "station_number",
                "void_rate",
                "ballot_type",
                "count_tier",
                "meta_tier",
                "imputed_fields",
            ]
        ]
        st.markdown(
            f"**Top 15 หน่วยที่มีบัตรเสียสูงสุด** <sub>{rank_cap}</sub>", unsafe_allow_html=True
        )
        st.dataframe(
            top_void.rename(
                columns={
                    "district": "อำเภอ",
                    "subdistrict": "ตำบล",
                    "station_number": "หน่วย",
                    "void_rate": "% บัตรเสีย",
                    "ballot_type": "ประเภท",
                }
            ),
            width="stretch",
            height=400,
        )

    with col_t:
        bottom_turnout = rank_sub.nsmallest(15, "turnout_rate")[
            [
                "district",
                "subdistrict",
                "station_number",
                "turnout_rate",
                "ballot_type",
                "count_tier",
                "meta_tier",
                "imputed_fields",
            ]
        ]
        st.markdown(
            f"**Bottom 15 หน่วยที่อัตราผู้ใช้สิทธิ์ต่ำสุด** <sub>{rank_cap}</sub>",
            unsafe_allow_html=True,
        )
        st.dataframe(
            bottom_turnout.rename(
                columns={
                    "district": "อำเภอ",
                    "subdistrict": "ตำบล",
                    "station_number": "หน่วย",
                    "turnout_rate": "อัตราผู้ใช้สิทธิ์",
                    "ballot_type": "ประเภท",
                }
            ),
            width="stretch",
            height=400,
        )

    st.divider()

    # Top 10 candidates (district, Tier A)
    top_cand, top_cand_cap = clean_subset(
        candidates[
            (candidates["ballot_type"] == "district")
            & (~candidates["withdrawn"].fillna(False))
        ],
        count_tier="A",
        meta_tier=["M0"],
        requires=["votes"],
    )
    if len(top_cand) > 0:
        cand_rank = (
            top_cand.groupby(["number", "name", "party"])["votes"]
            .sum()
            .reset_index()
            .sort_values("votes", ascending=False)
            .head(10)
        )
        cand_rank["color"] = cand_rank["party"].map(color)
        fig_cand = px.bar(
            cand_rank,
            x="name",
            y="votes",
            color="party",
            color_discrete_map={p: color(p) for p in cand_rank["party"]},
            title=f"Top 10 ผู้สมัคร บัตรเขต (คะแนนรวมทุกหน่วย)<br><sub>{top_cand_cap}</sub>",
            labels={"name": "ชื่อ", "votes": "คะแนน", "party": "พรรค"},
            text="votes",
        )
        fig_cand.update_layout(showlegend=True, xaxis_tickangle=-30)
        fig_cand.update_traces(texttemplate="%{text:,}", textposition="outside")
        st.plotly_chart(fig_cand, width="stretch")

    # Party leaderboard (partylist, Tier A)
    pl_rank, pl_rank_cap = clean_subset(
        candidates[candidates["ballot_type"] == "partylist"],
        count_tier="A",
        requires=["votes"],
    )
    if len(pl_rank) > 0:
        party_lb = (
            pl_rank.groupby("party")["votes"]
            .sum()
            .reset_index()
            .sort_values("votes", ascending=False)
        )
        party_lb["rank"] = range(1, len(party_lb) + 1)
        total_v = party_lb["votes"].sum()
        party_lb["vote_share"] = (
            (party_lb["votes"] / total_v * 100).round(2) if total_v else 0
        )

        fig_lb = px.bar(
            party_lb.head(15),
            x="party",
            y="votes",
            color="party",
            color_discrete_map={p: color(p) for p in party_lb["party"]},
            title=f"Party Leaderboard — บัตรบัญชีรายชื่อ<br><sub>{pl_rank_cap}</sub>",
            labels={"party": "พรรค", "votes": "คะแนนรวม"},
            text="vote_share",
        )
        fig_lb.update_layout(showlegend=False, xaxis_tickangle=-40)
        fig_lb.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        st.plotly_chart(fig_lb, width="stretch")
