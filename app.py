"""
app.py — DSDE Election OCR Analysis
Streamlit entry point: loads shared data once, routes to 4 tabs.

Tabs:
  1. Overview        — headline KPIs, tier composition, map placeholder
  2. Data Quality    — failure modes, OCR accuracy vs official, spot-check queue
  3. EDA             — distributions (full vs valid) + rankings
  4. Geospatial      — choropleth turnout, winner markers, area analysis (instruction.txt)
  5. Swing Analysis  — 2023 vs 2026 net gain/loss, split-ticket, candidate shifts
"""

from lib import load_data
from tabs import data_quality, eda, geo, overview, swing_analysis

import streamlit as st

st.set_page_config(
    page_title="DSDE Election OCR — นครราชสีมา เขต 5",
    page_icon="🗳️",
    layout="wide",
)

st.title("🗳️ การวิเคราะห์ข้อมูลการเลือกตั้ง — นครราชสีมา เขต 5")
st.caption("ข้อมูล: บัญชีรายงานผลการนับคะแนน (OCR) · 606 ระเบียน · 3 อำเภอ")

records, candidates, pages, official = load_data()

t1, t2, t3, t4, t5 = st.tabs(
    [
        "📊 Overview",
        "🔍 Data Quality",
        "📈 EDA",
        "🗺️ Geospatial",
        "🔄 Swing Analysis"
    ]
)

with t1:
    overview.render(records, candidates, pages, official)
with t2:
    data_quality.render(records, candidates, pages, official)
with t3:
    eda.render(records, candidates, pages, official)
with t4:
    geo.render(records, candidates, pages, official)
with t5:
    swing_analysis.render(records, candidates, pages, official)