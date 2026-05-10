"""
Tab 4 — Geospatial Analysis (instruction.txt: คนที่ 2 - เปรม)
- Choropleth turnout by subdistrict
- Winner markers per subdistrict
- Area type analysis (agricultural / tourist / industrial)
- Policy vs vote analysis
- Export map_data.geojson
"""

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
from lib import _HERE, clean_subset, color

import streamlit as st

try:
    import folium
    from streamlit_folium import st_folium

    HAS_GEO = True
except ImportError:
    HAS_GEO = False

try:
    from rapidfuzz import process as fuzz_process

    HAS_FUZZY = True
except ImportError:
    HAS_FUZZY = False

# ── Constants ─────────────────────────────────────────────────────────────────

# Path to tha_admin3.geojson (in parent dir of DSDE_final/)
_GEOJSON_PATH = _HERE.parent / "tha_admin3.geojson"

# Constituency 5 districts (without อำเภอ prefix — GeoJSON field names)
_C5_DISTRICTS = {"โนนสูง", "พิมาย", "เฉลิมพระเกียรติ"}

# Economic classification
AREA_TYPES: dict[str, str] = {
    "อำเภอโนนสูง": "agricultural",
    "อำเภอพิมาย": "tourist/historical",
    "อำเภอเฉลิมพระเกียรติ": "agricultural",
}

AREA_DESCRIPTIONS = {
    "agricultural": "ชนบท / เกษตรกรรม — ข้าว, มันสำปะหลัง, อ้อย",
    "tourist/historical": "ท่องเที่ยว / ประวัติศาสตร์ — อุทยานประวัติศาสตร์พิมาย (ปราสาทขอม)",
    "other": "ไม่ระบุ",
}


# ── GeoJSON helpers ───────────────────────────────────────────────────────────


def _strip_prefix(name: str, prefix: str) -> str:
    if isinstance(name, str) and name.startswith(prefix):
        return name[len(prefix) :]
    return name or ""


def _load_c5_features() -> list[dict]:
    """Load tha_admin3.geojson and filter to constituency 5 subdistricts."""
    if not _GEOJSON_PATH.exists():
        return []
    try:
        with open(_GEOJSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return [
            feat
            for feat in data["features"]
            if feat["properties"].get("adm2_name1") in _C5_DISTRICTS
            and feat["properties"].get("adm1_name1") == "นครราชสีมา"
        ]
    except Exception:
        return []


def _feature_centroid(feat: dict) -> tuple[float, float] | None:
    """Return (lat, lon) centroid from a GeoJSON feature."""
    lat = feat["properties"].get("center_lat")
    lon = feat["properties"].get("center_lon")
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    return None


def _fuzzy_match(name: str, candidates: list[str]) -> str:
    if HAS_FUZZY and candidates:
        result = fuzz_process.extractOne(name, candidates, score_cutoff=55)
        return result[0] if result else name
    return name


# ── Data preparation ──────────────────────────────────────────────────────────


def _subdistrict_stats(records: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate records to subdistrict level.
    Strip ตำบล prefix for GeoJSON join.
    """
    rec_norm = records[records["election_type"] == "normal"].copy()
    rec_norm["sub_clean"] = rec_norm["subdistrict"].apply(
        lambda s: _strip_prefix(str(s) if pd.notna(s) else "", "ตำบล")
    )
    rec_norm["dist_clean"] = rec_norm["district"].apply(
        lambda s: _strip_prefix(str(s) if pd.notna(s) else "", "อำเภอ")
    )

    agg = (
        rec_norm.groupby(["dist_clean", "sub_clean"])
        .agg(
            eligible_voters=("eligible_voters", "sum"),
            voter_turnout=("voter_turnout", "sum"),
            total_ballots=("total_ballots", "sum"),
            valid_votes=("valid_votes", "sum"),
            void_ballots=("void_ballots", "sum"),
            station_count=("file_id", "count"),
        )
        .reset_index()
    )
    agg["turnout_rate"] = agg["voter_turnout"] / agg["eligible_voters"].replace(
        0, float("nan")
    )

    # Winner per subdistrict (district ballot, Tier A candidates)
    dist_cand, _ = clean_subset(
        candidates[
            (candidates["ballot_type"] == "district")
            & (~candidates["withdrawn"].fillna(False))
        ],
        count_tier="A",
        requires=["votes"],
    )
    if len(dist_cand) > 0:
        dist_cand = dist_cand.copy()
        dist_cand["sub_clean"] = dist_cand["subdistrict"].apply(
            lambda s: _strip_prefix(str(s) if pd.notna(s) else "", "ตำบล")
        )
        winner = (
            dist_cand.sort_values("votes", ascending=False)
            .groupby("sub_clean")
            .first()
            .reset_index()[["sub_clean", "party", "name", "votes"]]
            .rename(
                columns={
                    "party": "winner_party",
                    "name": "winner_name",
                    "votes": "winner_votes",
                }
            )
        )
        agg = agg.merge(winner, on="sub_clean", how="left")
    else:
        agg["winner_party"] = None
        agg["winner_name"] = None
        agg["winner_votes"] = None

    # Area type
    agg["area_type"] = agg["dist_clean"].apply(
        lambda d: AREA_TYPES.get(f"อำเภอ{d}", "other")
    )
    return agg


# ── Map builders ──────────────────────────────────────────────────────────────


def _build_choropleth_map(
    features: list[dict], sub_stats: pd.DataFrame
) -> "folium.Map":
    """Build a folium choropleth of turnout by subdistrict."""
    import branca.colormap as cm

    m = folium.Map(location=[15.2, 102.4], zoom_start=10, tiles="CartoDB positron")

    sub_names = [f["properties"].get("adm3_name1", "") for f in features]
    rate_map = sub_stats.set_index("sub_clean")["turnout_rate"].to_dict()

    vmin = sub_stats["turnout_rate"].min(skipna=True)
    vmax = sub_stats["turnout_rate"].max(skipna=True)
    colorscale = cm.LinearColormap(
        ["#fee5d9", "#fc4e2a", "#800026"],
        vmin=vmin or 0,
        vmax=vmax or 1,
        caption="อัตราผู้ใช้สิทธิ์",
    )
    colorscale.add_to(m)

    for feat in features:
        sub = feat["properties"].get("adm3_name1", "")
        district = feat["properties"].get("adm2_name1", "")
        matched = _fuzzy_match(sub, list(rate_map.keys()))
        rate = rate_map.get(matched)

        fill_color = (
            colorscale(rate) if rate is not None and not pd.isna(rate) else "#d3d3d3"
        )
        folium.GeoJson(
            feat,
            style_function=lambda _, fc=fill_color: {
                "fillColor": fc,
                "color": "#555",
                "weight": 1,
                "fillOpacity": 0.75,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["adm3_name1", "adm2_name1"],
                aliases=["ตำบล:", "อำเภอ:"],
            ),
            popup=folium.Popup(
                f"<b>{district} / {sub}</b><br>Turnout: {rate:.1%}"
                if rate is not None
                else f"<b>{district} / {sub}</b><br>No data",
                max_width=200,
            ),
        ).add_to(m)
    return m


def _add_winner_markers(
    m: "folium.Map", features: list[dict], sub_stats: pd.DataFrame
) -> "folium.Map":
    """Add circle markers at subdistrict centroids coloured by winning party."""
    # Keep the row with the highest winner_votes when sub_clean is duplicated across districts
    deduped = (
        sub_stats.sort_values("winner_votes", ascending=False)
        .drop_duplicates("sub_clean")
        .set_index("sub_clean")[["winner_party", "winner_name", "winner_votes", "turnout_rate"]]
    )
    winner_map = deduped.to_dict("index")
    sub_names = list(winner_map.keys())

    for feat in features:
        sub = feat["properties"].get("adm3_name1", "")
        centroid = _feature_centroid(feat)
        if centroid is None:
            continue

        matched = _fuzzy_match(sub, sub_names)
        row = winner_map.get(matched, {})
        party = row.get("winner_party") if row else None
        if not party or (isinstance(party, float) and pd.isna(party)):
            continue

        hex_color = color(party)
        turnout = row.get("turnout_rate")
        turnout_str = f"{turnout:.1%}" if turnout and not pd.isna(turnout) else "–"

        folium.CircleMarker(
            location=centroid,
            radius=9,
            color=hex_color,
            fill=True,
            fill_color=hex_color,
            fill_opacity=0.85,
            popup=folium.Popup(
                f"<b>{sub}</b><br>ผู้ชนะ: {row.get('winner_name', '–')}<br>"
                f"พรรค: {party}<br>คะแนน: {row.get('winner_votes', 0):,.0f}<br>"
                f"Turnout: {turnout_str}",
                max_width=220,
            ),
            tooltip=f"{sub} → {party}",
        ).add_to(m)
    return m


# ── GeoJSON export ────────────────────────────────────────────────────────────


def _export_map_data(sub_stats: pd.DataFrame, features: list[dict]) -> str:
    """Build map_data.geojson with election stats + geometry."""
    # Build lookup: sub_clean → geometry
    geom_map = {
        feat["properties"].get("adm3_name1", ""): feat.get("geometry")
        for feat in features
    }
    feat_list = []
    for _, row in sub_stats.iterrows():
        sub = row["sub_clean"]
        matched = _fuzzy_match(sub, list(geom_map.keys()))
        feat_list.append(
            {
                "type": "Feature",
                "geometry": geom_map.get(matched),
                "properties": {
                    "subdistrict": sub,
                    "district": row["dist_clean"],
                    "eligible_voters": int(row["eligible_voters"])
                    if pd.notna(row["eligible_voters"])
                    else None,
                    "voter_turnout": int(row["voter_turnout"])
                    if pd.notna(row["voter_turnout"])
                    else None,
                    "turnout_rate": round(float(row["turnout_rate"]), 4)
                    if pd.notna(row.get("turnout_rate"))
                    else None,
                    "valid_votes": int(row["valid_votes"])
                    if pd.notna(row["valid_votes"])
                    else None,
                    "station_count": int(row["station_count"]),
                    "winner_party": row.get("winner_party"),
                    "winner_name": row.get("winner_name"),
                    "area_type": row.get("area_type", "other"),
                },
            }
        )
    return json.dumps(
        {"type": "FeatureCollection", "features": feat_list},
        ensure_ascii=False,
        indent=2,
    )


# ── Main render ───────────────────────────────────────────────────────────────


def render(
    records: pd.DataFrame,
    candidates: pd.DataFrame,
    pages: pd.DataFrame,
    official: pd.DataFrame,
) -> None:

    st.subheader("การวิเคราะห์เชิงพื้นที่ — นครราชสีมา เขตเลือกตั้งที่ 5")
    st.caption("อำเภอโนนสูง · อำเภอพิมาย · อำเภอเฉลิมพระเกียรติ")

    sub_stats = _subdistrict_stats(records, candidates)
    features = _load_c5_features()

    # ── Map section ───────────────────────────────────────────────
    st.markdown("### แผนที่")

    if not HAS_GEO:
        st.warning(
            "ไม่พบ folium / streamlit-folium — ติดตั้งด้วย `pip install folium streamlit-folium`"
        )
    elif not features:
        st.warning(
            f"ไม่พบไฟล์ GeoJSON: `{_GEOJSON_PATH}` — วาง `tha_admin3.geojson` ใน `{_HERE.parent}`"
        )
    else:
        map_type = st.radio(
            "แสดงแผนที่",
            ["Choropleth Turnout", "Winner per Subdistrict", "ทั้งคู่"],
            horizontal=True,
        )

        m = _build_choropleth_map(features, sub_stats)
        if map_type in ("Winner per Subdistrict", "ทั้งคู่"):
            m = _add_winner_markers(m, features, sub_stats)

        st_folium(m, height=540, width="stretch")

        if map_type in ("Winner per Subdistrict", "ทั้งคู่"):
            st.caption("จุดสี = พรรคที่ชนะในแต่ละตำบล (บัตรเขต Tier A)")

    # ── Turnout bar chart (always shown) ─────────────────────────
    st.markdown("### อัตราผู้ใช้สิทธิ์แยกตามตำบล")
    turnout_sorted = sub_stats.dropna(subset=["turnout_rate"]).sort_values(
        "turnout_rate", ascending=False
    )
    if len(turnout_sorted) > 0:
        fig_t = px.bar(
            turnout_sorted,
            x="sub_clean",
            y="turnout_rate",
            color="dist_clean",
            color_discrete_sequence=px.colors.qualitative.Set2,
            title="อัตราผู้ใช้สิทธิ์ต่อตำบล",
            labels={
                "sub_clean": "ตำบล",
                "turnout_rate": "อัตราผู้ใช้สิทธิ์",
                "dist_clean": "อำเภอ",
            },
        )
        fig_t.update_layout(xaxis_tickangle=-50)
        st.plotly_chart(fig_t, width="stretch")

    st.divider()

    # ── Winner per subdistrict table ──────────────────────────────
    st.markdown("### ผู้ชนะต่อตำบล (บัตรเขต, Tier A)")
    winner_tbl = sub_stats[
        [
            "dist_clean",
            "sub_clean",
            "winner_party",
            "winner_name",
            "winner_votes",
            "turnout_rate",
        ]
    ].copy()
    winner_tbl = winner_tbl.dropna(subset=["winner_party"]).sort_values(
        "winner_votes", ascending=False
    )
    winner_tbl["turnout_rate"] = winner_tbl["turnout_rate"].map(
        lambda x: f"{x:.1%}" if pd.notna(x) else "–"
    )
    st.dataframe(
        winner_tbl.rename(
            columns={
                "dist_clean": "อำเภอ",
                "sub_clean": "ตำบล",
                "winner_party": "พรรคผู้ชนะ",
                "winner_name": "ชื่อผู้ชนะ",
                "winner_votes": "คะแนน",
                "turnout_rate": "อัตราผู้ใช้สิทธิ์",
            }
        ),
        width="stretch",
        height=350,
    )

    st.divider()

    # ── Area-type analysis ────────────────────────────────────────
    st.markdown("### การวิเคราะห์แยกตามประเภทพื้นที่")

    st.info(
        "**เกษตรกรรม (agricultural):** อำเภอโนนสูง, เฉลิมพระเกียรติ — ข้าว มันสำปะหลัง อ้อย\n\n"
        "**ท่องเที่ยว/ประวัติศาสตร์:** อำเภอพิมาย — อุทยานประวัติศาสตร์พิมาย (ปราสาทขอม)",
    )

    # Turnout by area type
    area_turnout = (
        sub_stats.groupby("area_type")
        .agg(
            mean_turnout=("turnout_rate", "mean"),
            std_turnout=("turnout_rate", "std"),
            n=("sub_clean", "count"),
        )
        .reset_index()
        .dropna(subset=["mean_turnout"])
    )
    fig_area = px.bar(
        area_turnout,
        x="area_type",
        y="mean_turnout",
        error_y="std_turnout",
        color="area_type",
        title="อัตราผู้ใช้สิทธิ์เฉลี่ยแยกตามประเภทพื้นที่",
        labels={"area_type": "ประเภทพื้นที่", "mean_turnout": "เฉลี่ย Turnout"},
    )
    st.plotly_chart(fig_area, width="stretch")

    # Winner party distribution by area type
    area_winner = sub_stats.dropna(subset=["winner_party"]).copy()
    if len(area_winner) > 0:
        aw = (
            area_winner.groupby(["area_type", "winner_party"])
            .size()
            .reset_index(name="n")
        )
        fig_aw = px.bar(
            aw,
            x="area_type",
            y="n",
            color="winner_party",
            barmode="stack",
            color_discrete_map={p: color(p) for p in aw["winner_party"]},
            title="พรรคที่ชนะแยกตามประเภทพื้นที่",
            labels={"area_type": "ประเภทพื้นที่", "n": "จำนวนตำบล", "winner_party": "พรรค"},
        )
        st.plotly_chart(fig_aw, width="stretch")

    # Party vote totals by area type (Tier A district candidates)
    dist_cand, dist_cap = clean_subset(
        candidates[candidates["ballot_type"] == "district"],
        count_tier="A",
        requires=["votes"],
    )
    if len(dist_cand) > 0:
        dc = dist_cand.copy()
        dc["sub_clean"] = dc["subdistrict"].apply(
            lambda s: _strip_prefix(str(s) if pd.notna(s) else "", "ตำบล")
        )
        dc["dist_clean"] = dc["district"].apply(
            lambda s: _strip_prefix(str(s) if pd.notna(s) else "", "อำเภอ")
        )
        dc["area_type"] = dc["dist_clean"].apply(
            lambda d: AREA_TYPES.get(f"อำเภอ{d}", "other")
        )
        area_party = dc.groupby(["area_type", "party"])["votes"].sum().reset_index()
        top_p = area_party.groupby("party")["votes"].sum().nlargest(8).index.tolist()
        fig_ap = px.bar(
            area_party[area_party["party"].isin(top_p)],
            x="area_type",
            y="votes",
            color="party",
            barmode="group",
            color_discrete_map={p: color(p) for p in top_p},
            title=f"คะแนนพรรค Top 8 แยกตามประเภทพื้นที่<br><sub>{dist_cap}</sub>",
            labels={"area_type": "ประเภทพื้นที่", "votes": "คะแนน", "party": "พรรค"},
        )
        st.plotly_chart(fig_ap, width="stretch")

    st.divider()

    # ── Policy analysis table ─────────────────────────────────────
    st.markdown("### การวิเคราะห์นโยบายกับผลโหวต")
    st.markdown("""
| ประเภทพื้นที่ | อำเภอ | นโยบายที่คาดว่ามีผล | แนวโน้มพรรค | หมายเหตุ |
|---|---|---|---|---|
| เกษตรกรรม | โนนสูง, เฉลิมพระเกียรติ | ราคาสินค้าเกษตร, ประกันรายได้ชาวนา, สวัสดิการรัฐ | เพื่อไทย / ภูมิใจไทย | เกษตรกรตอบสนองต่อนโยบายอุดหนุนโดยตรง |
| ท่องเที่ยว/ประวัติศาสตร์ | พิมาย | โครงสร้างพื้นฐานท่องเที่ยว, อนุรักษ์มรดกวัฒนธรรม | หลากหลาย | รายได้จากท่องเที่ยว — คะแนนกระจายมากกว่า |

*การวิเคราะห์นี้ใช้ข้อมูล OCR ที่ผ่าน Tier A เท่านั้น ให้ระมัดระวังในการตีความ*
""")

    # ── Export map_data.geojson ───────────────────────────────────
    st.divider()
    st.markdown("### Export")
    geojson_str = _export_map_data(sub_stats, features)
    col1, col2 = st.columns(2)
    col1.download_button(
        "⬇️ ดาวน์โหลด map_data.geojson",
        data=geojson_str,
        file_name="map_data.geojson",
        mime="application/json",
    )
    if col2.button("💾 บันทึก map_data.geojson ลงไฟล์"):
        out_path = _HERE / "reports" / "map_data.geojson"
        out_path.write_text(geojson_str, encoding="utf-8")
        col2.success(f"บันทึกแล้วที่ {out_path}")
