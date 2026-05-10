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
_GEOJSON_PATH = _HERE / "data/tha_admin3.geojson"

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

    # Use district records only for turnout — district and partylist share the same
    # eligible_voters/voter_turnout per station, so summing both would double-count.
    rec_district = rec_norm[rec_norm["ballot_type"] == "district"]

    agg = (
        rec_district.groupby(["dist_clean", "sub_clean"])
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

    # Winner per subdistrict for each ballot type (Tier A candidates)
    for bt, prefix in [("district", ""), ("partylist", "pl_")]:
        cand_sub, _ = clean_subset(
            candidates[
                (candidates["ballot_type"] == bt)
                & (~candidates["withdrawn"].fillna(False))
            ],
            count_tier="A",
            requires=["votes"],
        )
        if len(cand_sub) > 0:
            cand_sub = cand_sub.copy()
            cand_sub["sub_clean"] = cand_sub["subdistrict"].apply(
                lambda s: _strip_prefix(str(s) if pd.notna(s) else "", "ตำบล")
            )
            winner = (
                cand_sub.sort_values("votes", ascending=False)
                .groupby("sub_clean")
                .first()
                .reset_index()[["sub_clean", "party", "name", "votes"]]
                .rename(columns={
                    "party": f"{prefix}winner_party",
                    "name": f"{prefix}winner_name",
                    "votes": f"{prefix}winner_votes",
                })
            )
            agg = agg.merge(winner, on="sub_clean", how="left")
        else:
            agg[f"{prefix}winner_party"] = None
            agg[f"{prefix}winner_name"] = None
            agg[f"{prefix}winner_votes"] = None

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


def _hex_to_rgba(hex_color: str, alpha: float = 0.65) -> str:
    """Convert #RRGGBB to rgba(r,g,b,a) string for HTML tooltips."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _build_legend_html(parties: list[tuple[str, str]]) -> str:
    """Return an HTML string for a floating map legend."""
    items = "".join(
        f'<div style="display:flex;align-items:center;gap:6px;margin:3px 0">'
        f'<div style="width:14px;height:14px;background:{hex_col};border-radius:3px;flex-shrink:0"></div>'
        f'<span style="font-size:12px">{party}</span></div>'
        for party, hex_col in parties
    )
    return (
        '<div style="position:fixed;bottom:30px;left:30px;z-index:1000;background:white;'
        'padding:10px 14px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.25);'
        'font-family:sans-serif;max-width:200px">'
        f'<b style="font-size:13px">พรรคที่ชนะ</b>{items}</div>'
    )


def _add_winner_markers(
    m: "folium.Map",
    features: list[dict],
    sub_stats: pd.DataFrame,
    ballot_type: str = "district",
) -> "folium.Map":
    """Fill each subdistrict polygon with the winning party colour + popup."""
    from branca.element import Element

    prefix = "pl_" if ballot_type == "partylist" else ""
    party_col = f"{prefix}winner_party"
    name_col  = f"{prefix}winner_name"
    votes_col = f"{prefix}winner_votes"

    cols = [c for c in [party_col, name_col, votes_col, "turnout_rate"] if c in sub_stats.columns]
    deduped = (
        sub_stats.sort_values(votes_col, ascending=False)
        .drop_duplicates("sub_clean")
        .set_index("sub_clean")[cols]
    )
    winner_map = deduped.to_dict("index")
    sub_names  = list(winner_map.keys())
    seen_parties: list[tuple[str, str]] = []
    seen_set: set[str] = set()

    for feat in features:
        sub      = feat["properties"].get("adm3_name1", "")
        district = feat["properties"].get("adm2_name1", "")
        matched  = _fuzzy_match(sub, sub_names)
        row      = winner_map.get(matched, {})
        party    = row.get(party_col) if row else None

        if not party or (isinstance(party, float) and pd.isna(party)):
            # No data — light grey outline only
            folium.GeoJson(
                feat,
                style_function=lambda _: {
                    "fillColor": "#cccccc",
                    "color": "#888",
                    "weight": 1,
                    "fillOpacity": 0.3,
                },
                tooltip=f"{sub} / {district} — ไม่มีข้อมูล",
            ).add_to(m)
            continue

        hex_col  = color(party)
        turnout  = row.get("turnout_rate")
        turnout_str = f"{turnout:.1%}" if pd.notna(turnout) else "–"
        name_val = row.get(name_col) or party
        votes_val = row.get(votes_col, 0)
        label    = "พรรค" if ballot_type == "partylist" else "ผู้ชนะ"

        if party not in seen_set:
            seen_parties.append((party, hex_col))
            seen_set.add(party)

        popup_html = (
            f'<div style="font-family:sans-serif;min-width:160px">'
            f'<div style="background:{hex_col};color:white;padding:4px 8px;'
            f'border-radius:4px 4px 0 0;font-weight:bold">{party}</div>'
            f'<div style="padding:6px 8px;font-size:13px">'
            f'<b>ตำบล:</b> {sub}<br>'
            f'<b>อำเภอ:</b> {district}<br>'
            f'<b>{label}:</b> {name_val}<br>'
            f'<b>คะแนน:</b> {votes_val:,.0f}<br>'
            f'<b>Turnout:</b> {turnout_str}'
            f'</div></div>'
        )

        folium.GeoJson(
            feat,
            style_function=lambda _, hc=hex_col: {
                "fillColor": hc,
                "color": hc,
                "weight": 1.5,
                "fillOpacity": 0.65,
            },
            highlight_function=lambda _, hc=hex_col: {
                "fillColor": hc,
                "color": "#222",
                "weight": 3,
                "fillOpacity": 0.85,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["adm3_name1", "adm2_name1"],
                aliases=["ตำบล:", "อำเภอ:"],
                style="font-family:sans-serif;font-size:13px",
            ),
            popup=folium.Popup(popup_html, max_width=240),
        ).add_to(m)

    # Add floating legend
    if seen_parties:
        legend = Element(_build_legend_html(seen_parties))
        m.get_root().html.add_child(legend)

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
    st.caption(
        "โนนสูง, พิมาย (เฉพาะกระเบื้องใหญ่, ชีวาน, ท่าหลวง, สัมฤทธิ์), เฉลิมพระเกียรติ (เฉพาะช้างทอง, ท่าช้าง)"
    )

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
            # f"ไม่พบไฟล์ GeoJSON: `{_GEOJSON_PATH}` — วาง `tha_admin3.geojson` ใน `{_HERE.parent}`"
            "ไม่พบไฟล์ GeoJSON: กรุณา download `tha_admin3.geojson` จาก https://drive.google.com/file/d/1PowqO0fX2DhIN0fDdd1hJLu3I31iUglg/view?usp=sharing แล้ววาง `tha_admin3.geojson` ใน /data"
        )
    else:
        def _make_map(ballot_type: str) -> "folium.Map":
            m = folium.Map(location=[15.2, 102.4], zoom_start=9, tiles="CartoDB positron")
            return _add_winner_markers(m, features, sub_stats, ballot_type=ballot_type)

        col_map1, col_map2 = st.columns(2)
        with col_map1:
            st.caption("บัตรเขต — เลือกคน (district)")
            st_folium(_make_map("district"), height=480, use_container_width=True, key="map_district")
        with col_map2:
            st.caption("บัตรบัญชีรายชื่อ — เลือกพรรค (partylist)")
            st_folium(_make_map("partylist"), height=480, use_container_width=True, key="map_partylist")
        st.caption("จุดสี = พรรคที่ชนะในแต่ละตำบล (Tier A)")

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
    st.markdown("### ผู้ชนะต่อตำบล (Tier A)")
    col_d, col_pl = st.columns(2)

    def _winner_table(col, party_col, name_col, votes_col, title):
        tbl = sub_stats[["dist_clean", "sub_clean", party_col, name_col, votes_col]].copy()
        tbl = tbl.dropna(subset=[party_col]).sort_values(votes_col, ascending=False)
        with col:
            st.markdown(f"**{title}**")
            st.dataframe(
                tbl.rename(columns={
                    "dist_clean": "อำเภอ", "sub_clean": "ตำบล",
                    party_col: "พรรค", name_col: "ชื่อ", votes_col: "คะแนน",
                }),
                use_container_width=True, height=350,
            )

    _winner_table(col_d, "winner_party", "winner_name", "winner_votes", "บัตรเขต (เลือกคน)")
    _winner_table(col_pl, "pl_winner_party", "pl_winner_name", "pl_winner_votes", "บัตรบัญชีรายชื่อ (เลือกพรรค)")

    st.divider()

    # ── Area-type analysis ────────────────────────────────────────
    st.markdown("### การวิเคราะห์แยกตามประเภทพื้นที่")

    st.info(
        "**เกษตรกรรม :** อำเภอโนนสูง, เฉลิมพระเกียรติ — ข้าว มันสำปะหลัง อ้อย\n\n"
        "**ท่องเที่ยว/ประวัติศาสตร์:** อำเภอพิมาย — อุทยานประวัติศาสตร์พิมาย (ปราสาทขอม)",
    )

    # Turnout by area type
    area_turnout = (
        sub_stats[sub_stats["area_type"] != "other"]
        .groupby("area_type")
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

    # Winner party distribution by area type — district and partylist side-by-side
    aw_base = sub_stats[sub_stats["area_type"] != "other"].copy()
    col_aw1, col_aw2 = st.columns(2)

    def _winner_area_chart(col, party_col: str, title: str) -> None:
        df = aw_base.dropna(subset=[party_col])
        if len(df) == 0:
            return
        aw = df.groupby(["area_type", party_col]).size().reset_index(name="n")
        fig = px.bar(
            aw,
            x="area_type",
            y="n",
            color=party_col,
            barmode="stack",
            color_discrete_map={p: color(p) for p in aw[party_col]},
            title=title,
            labels={"area_type": "ประเภทพื้นที่", "n": "จำนวนตำบล", party_col: "พรรค"},
        )
        with col:
            st.plotly_chart(fig, use_container_width=True)

    _winner_area_chart(col_aw1, "winner_party", "ส.ส.เขต — พรรคที่ชนะแยกตามพื้นที่")
    _winner_area_chart(col_aw2, "pl_winner_party", "บัญชีรายชื่อ — พรรคที่ชนะแยกตามพื้นที่")

    # Party votes by area type — district and partylist shown side-by-side
    def _area_party_chart(ballot_type: str, cap_label: str) -> None:
        sub_cand, cap = clean_subset(
            candidates[candidates["ballot_type"] == ballot_type],
            count_tier="A",
            requires=["votes"],
        )
        if len(sub_cand) == 0:
            return
        sc = sub_cand.copy()
        sc["dist_clean"] = sc["district"].apply(
            lambda s: _strip_prefix(str(s) if pd.notna(s) else "", "อำเภอ")
        )
        sc["area_type"] = sc["dist_clean"].apply(
            lambda d: AREA_TYPES.get(f"อำเภอ{d}", "other")
        )
        sc = sc[sc["area_type"] != "other"]
        area_party = sc.groupby(["area_type", "party"])["votes"].sum().reset_index()
        top_p = area_party.groupby("party")["votes"].sum().nlargest(8).index.tolist()
        fig = px.bar(
            area_party[area_party["party"].isin(top_p)],
            x="area_type",
            y="votes",
            color="party",
            barmode="group",
            color_discrete_map={p: color(p) for p in top_p},
            title=f"คะแนนพรรค Top 8 — {cap_label}<br><sub>{cap}</sub>",
            labels={"area_type": "ประเภทพื้นที่", "votes": "คะแนน", "party": "พรรค"},
        )
        st.plotly_chart(fig, use_container_width=True)

    # col_d, col_pl = st.columns(2)
    # with col_d:
    #     _area_party_chart("district", "บัตรเขต (เลือกคน)")
    # with col_pl:
    #     _area_party_chart("partylist", "บัตรบัญชีรายชื่อ (เลือกพรรค)")

    st.divider()

    # ── Policy analysis table ─────────────────────────────────────
#     st.markdown("### การวิเคราะห์นโยบายกับผลโหวต")
#     st.markdown("""
# | ประเภทพื้นที่ | อำเภอ | นโยบายที่คาดว่ามีผล | แนวโน้มพรรค | หมายเหตุ |
# |---|---|---|---|---|
# | เกษตรกรรม | โนนสูง, เฉลิมพระเกียรติ | ราคาสินค้าเกษตร, ประกันรายได้ชาวนา, สวัสดิการรัฐ | เพื่อไทย / ภูมิใจไทย | เกษตรกรตอบสนองต่อนโยบายอุดหนุนโดยตรง |
# | ท่องเที่ยว/ประวัติศาสตร์ | พิมาย | โครงสร้างพื้นฐานท่องเที่ยว, อนุรักษ์มรดกวัฒนธรรม | หลากหลาย | รายได้จากท่องเที่ยว — คะแนนกระจายมากกว่า |

# *การวิเคราะห์นี้ใช้ข้อมูล OCR ที่ผ่าน Tier A เท่านั้น ให้ระมัดระวังในการตีความ*
# """)

    # ── Export map_data.geojson ───────────────────────────────────
    # st.divider()
    # st.markdown("### Export")
    # geojson_str = _export_map_data(sub_stats, features)
    # col1, col2 = st.columns(2)
    # col1.download_button(
    #     "⬇️ ดาวน์โหลด map_data.geojson",
    #     data=geojson_str,
    #     file_name="map_data.geojson",
    #     mime="application/json",
    # )
    # if col2.button("💾 บันทึก map_data.geojson ลงไฟล์"):
    #     out_path = _HERE / "reports" / "map_data.geojson"
    #     out_path.write_text(geojson_str, encoding="utf-8")
    #     col2.success(f"บันทึกแล้วที่ {out_path}")
