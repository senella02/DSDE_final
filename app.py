"""
app.py — DSDE Election OCR · Streamlit entry point.

Loads all four parquets once (cached), then routes to per-tab render functions.
Each tab module exposes a single render(records, candidates, pages, official) function.
"""
import streamlit as st

from lib import load_data
from tabs import overview, data_quality, eda
from anomaly import tab as anomaly_tab

st.set_page_config(
    page_title="DSDE Election OCR",
    page_icon="🗳",
    layout="wide",
)

records, candidates, pages, official = load_data()

tab_specs = [
    ("Overview",     overview.render),
    ("Data Quality", data_quality.render),
    ("EDA",          eda.render),
    ("Anomaly",      anomaly_tab.render),
]

tabs = st.tabs([name for name, _ in tab_specs])
for tab, (_, render) in zip(tabs, tab_specs):
    with tab:
        render(records, candidates, pages, official)
