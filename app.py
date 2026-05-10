"""
app.py — DSDE Election OCR Analysis
Streamlit entry point: loads shared data once, routes to 4 tabs.

Tabs:
  1. Overview        — headline KPIs, tier composition, map placeholder
  2. Data Quality    — failure modes, OCR accuracy vs official, spot-check queue
  3. EDA             — distributions (full vs valid) + rankings
  4. Geospatial      — choropleth turnout, winner markers, area analysis (instruction.txt)
"""

from lib import load_data
from tabs import data_quality, eda, geo, overview

import streamlit as st

st.set_page_config(
    page_title="DSDE Election OCR — นครราชสีมา เขต 5",
    page_icon="🗳️",
    layout="wide",
)

st.title("🗳️ การวิเคราะห์ข้อมูลการเลือกตั้ง — นครราชสีมา เขต 5")
st.caption("ข้อมูล: บัญชีรายงานผลการนับคะแนน (OCR) · 606 ระเบียน · 3 อำเภอ")

records, candidates, pages, official = load_data()

t1, t2, t3, t4 = st.tabs(
    [
        "📊 Overview",
        "🔍 Data Quality",
        "📈 EDA",
        "🗺️ Geospatial",
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
