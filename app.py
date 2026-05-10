
import streamlit as st

from lib import load_data
from tabs import data_quality, eda, geo, overview
from anomaly import tab as anomaly_tab
from tabs import data_quality, eda, geo, overview, swing_analysis

import streamlit as st

st.set_page_config(
    page_title="DSDE Election OCR — นครราชสีมา เขต 5",
    page_icon="🗳️",
    layout="wide",
)

st.title("การวิเคราะห์ข้อมูลการเลือกตั้ง — นครราชสีมา เขต 5")
st.caption("ข้อมูล: บัญชีรายงานผลการนับคะแนน (OCR) · 606 ระเบียน · 3 อำเภอ")

records, candidates, pages, official = load_data()

t1, t2, t3, t4, t5, t6 = st.tabs(
    [
        "Overview",
        "Data Quality",
        "EDA",
        "Geospatial",
        "Anomaly",
        "Swing Analysis"
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
    anomaly_tab.render(records, candidates, pages, official)
with t6:
    swing_analysis.render(records, candidates, pages, official)