# solution.md — Visualizing Dirty OCR Data

Implementation guide for the EDA + Data-Quality slice of the project. Final deliverable is a **single Streamlit app** with three tabs; each tab is one coherent story. We own all three tabs and the shared utilities every teammate's future tabs import.

---

## 1. Project layout

Flat, one-file-per-tab. Two people editing the same `app.py` is a merge-conflict factory; one tab per file fixes that.

```
Visualization/
├── app.py                       # Streamlit entry — loads data, routes tabs
├── lib.py                       # ingest, gates, tiers, palette, chart helpers
├── party_colors.json            # canonical party → hex
├── tabs/
│   ├── overview.py              # ours — headline KPIs + coverage summary
│   ├── data_quality.py          # ours — QA dashboard, accuracy vs official, spot-check queue
│   ├── eda.py                   # ours — distributions + rankings
│   └── <friend>_*.py            # her tabs go here
├── data/                        # generated, gitignored
│   ├── records.parquet
│   ├── candidates.parquet
│   ├── pages.parquet
│   └── official.parquet         # official government results, joined key
└── reports/
    ├── data_quality_report.csv
    ├── spotcheck_queue.csv
    └── accuracy_report.csv      # OCR vs official per-field error summary
```

`app.py` is tiny — load parquets once, define tabs, hand each tab the dataframes:

```python
# app.py
import streamlit as st
from lib import load_data
from tabs import overview, data_quality, eda

st.set_page_config(page_title="DSDE Election OCR", layout="wide")
records, candidates, pages, official = load_data()

tab_specs = [
    ("Overview",           overview.render),
    ("Data Quality",       data_quality.render),
    ("EDA",                eda.render),
    # friend's tabs append here
]
tabs = st.tabs([name for name, _ in tab_specs])
for tab, (_, render) in zip(tabs, tab_specs):
    with tab:
        render(records, candidates, pages, official)
```

Every tab module exposes a single `render(records, candidates, pages, official)` function. That's the contract — no globals, no surprises.

---

## 2. Data pipeline

One ingestion pass, run once, cached as parquet. Everything downstream reads parquet.

```python
# lib.py — ingestion
@st.cache_data
def load_data():
    if not all(p.exists() for p in PARQUET_FILES):
        ingest_json_to_parquet()           # walks OCR_OUTPUT_JSON/, builds 3 parquets
    return (pd.read_parquet("data/records.parquet"),
            pd.read_parquet("data/candidates.parquet"),
            pd.read_parquet("data/pages.parquet"))
```

`ingest_json_to_parquet()` does, in order: load JSON → flatten → impute one-missing ballot field → assign `count_tier` and `meta_tier` (§3) → write parquet. Keep it under 100 lines.

Also load official results into `data/official.parquet` in the same pass. Update `load_data()` to return it as a fourth dataframe:

```python
records, candidates, pages, official = load_data()
```

---

## 2a. Official government results

The official results serve as **ground truth** for measuring OCR accuracy.

**Join key**: `(station_number, subdistrict, ballot_type)`. If official data is only at subdistrict level, sum OCR station records up before comparing — never compare mismatched granularities.

**Three things to compute against official**:

1. **Field-level accuracy** — absolute and relative error per record for `valid_votes`, `void_ballots`, `spoiled_ballots`, `total_ballots`, and per-candidate `votes`.
2. **QA flag calibration** — cross-tab existing QA flags against "matches official" to surface false negatives (passes QA but value is wrong) and false positives (fails QA but value is actually correct).
3. **Error magnitude buckets** — bin errors as <5, <50, <500, 500+ to judge whether failures are close noise or severely corrupting.

**Edge cases to handle explicitly**:
- ~23 PDFs with no parseable OCR record → log as `coverage_gap` in `accuracy_report.csv`, don't silently drop.
- Advance-vote records may be grouped differently in official data — verify category mapping before joining.
- Scope: use official data only for OCR accuracy measurement, not for election outcome claims.

Output: `reports/accuracy_report.csv` — one row per matched record with per-field error columns + `qc_false_negative` / `qc_false_positive` flags.

---

## 3. Validity model

Two orthogonal axes. Don't conflate count integrity with metadata integrity.

**`count_tier`** — does the math work?

| Tier | Rule (post-imputation) | Use for |
|---|---|---|
| A | `total_is_valid ∧ candidate_sum_valid` | Vote shares, all aggregates |
| B | `total_is_valid ∧ ¬candidate_sum_valid` | Turnout, void %, spoil % only |
| C | `¬total_is_valid` | Spot-check queue only |

**`meta_tier`** — can we group/join this row?

| Tier | Rule | Use for |
|---|---|---|
| M0 | `district`, `subdistrict`, `station_number` all present | Station-level rankings |
| M1 | `moo` and/or `station_number` null | Subdistrict-level aggregates |
| M2 | `subdistrict` null on a `normal` record | Spot-check only |

For `advance` records, `district`/`subdistrict`/`moo` being null is expected by schema — those don't drop the row to M2.

**Imputation:** when exactly one of `{total_ballots, valid_votes, void_ballots, spoiled_ballots}` is null and the other three are present, derive it. Tag the row's `imputed_fields` so charts can show it. Run imputation *before* tier assignment so recoverable records lift from C to A.

---

## 4. The shared gate function

The single function every tab calls before plotting. Lives in `lib.py`. Returns `(filtered_df, caption_string)`.

```python
def clean_subset(df, *, count_tier=None, meta_tier=None, requires=None):
    out, parts = df, []
    if count_tier:
        out = out[out["count_tier"].isin(list(count_tier))]
        parts.append(f"count∈{set(count_tier)}")
    if meta_tier:
        out = out[out["meta_tier"].isin(list(meta_tier))]
        parts.append(f"meta∈{set(meta_tier)}")
    if requires:
        for col in requires:
            out = out[out[col].notna()]
        parts.append("notna(" + ",".join(requires) + ")")
    caption = f"n={len(out)}/{len(df)} • " + (" ∧ ".join(parts) if parts else "all rows")
    return out, caption
```

Usage in any tab — ours or hers:

```python
sub, cap = clean_subset(records, count_tier="AB", requires=["voter_turnout","eligible_voters"])
fig = px.histogram(sub, x="turnout_rate", title=f"Turnout<br><sub>{cap}</sub>")
st.plotly_chart(fig, width='stretch')
```

That's the entire methodology contract. If you can't write the gate as a `clean_subset()` call, you shouldn't be plotting yet.

---

## 5. Shared palette

`party_colors.json` keyed by exact party string from the JSON. Single accessor:

```python
# lib.py
PALETTE = json.loads(Path("party_colors.json").read_text(encoding="utf-8"))
def color(party): return PALETTE.get((party or "").strip(), "#B0B0B0")
```

Rule for everyone: never inline hex codes for parties. Import `color`.

---

## 6. Our tabs

Three tabs. Each is a self-contained story; every chart is one `clean_subset` call followed by one Plotly figure.

---

### Tab 1 — Overview

The landing page. Answers "what is this dataset and how healthy is it?" in a single glance.

- Five headline metric cards: total records, % clean (no failure modes), % imputed, median turnout, top party by vote share.
- Tier composition stacked bar — `election_type × ballot_type`, colored by `count_tier` — so the reader immediately sees how much data is usable.
- One map placeholder (empty `st.empty()` with a comment) for the geo teammate to drop a choropleth into.

No filters or toggles here. Keep it static and scannable.

---

### Tab 2 — Data Quality

The audit page. Three logical sections, separated by `st.divider()`.

**Section A — Failure mode analysis**
- Failure-mode frequency bar chart (sorted descending).
- Null-rate per header field (horizontal bar; sorted by null count).
- Failures-per-record histogram (how many records have 0, 1, 2, … failure modes).
- Failure-mode co-occurrence heatmap.

Surface whether failures cluster by station, subdistrict, or ballot type: systematic clustering = physical scanning/printing issue, not random OCR noise. That's a reportable finding even if those records can't contribute to vote-share charts. Tier C / high-failure records are the *subject* of this section — do not discard them.

**Section B — OCR accuracy vs official**
Four charts against government ground truth: per-field error distribution (box plot, one box per `valid_votes`, `void_ballots`, `spoiled_ballots`, `total_ballots`), error-magnitude bucketed bar (% records off by <5 / <50 / <500 / 500+), QA-flag calibration 2×2 (pass/fail QA × matches/differs from official → false negatives and false positives), OCR latency box faceted by `page_role`. Download button for `accuracy_report.csv`.

**Section C — Spot-check queue**
Plotly table of records with `count_tier=C` or `≥3 failure modes`, sorted by failure count descending, with `image_path` linked so a human can open the scan. Download button for `spotcheck_queue.csv` and `data_quality_report.csv`.

---

### Tab 3 — EDA

The analysis page. Two sections: distributions, then rankings.

**Section A — Distributions**
For each metric, render **two versions side by side** (full-data vs valid-only via `clean_subset`). The delta is a finding — significant shift = OCR failures are non-random and bias results.
- Turnout / void % / spoil % histograms (gate: `count_tier∈AB`, `requires` per chart).
- District vote share by party (Tier A, palette colors).
- Partylist vote share by party (Tier A, palette colors).
- Turnout-vs-void scatter colored by `count_tier`.

**Section B — Rankings**
- Top/bottom 15 stations by void %, by turnout %.
- Top 10 candidates by votes (district, Tier A).
- Party leaderboard (partylist, Tier A).

Every ranking table includes `count_tier`, `meta_tier`, and `imputed_fields` columns so the reader can judge OCR trustworthiness at a glance.

---

## 7. Conventions for every tab (ours and hers)

These are non-negotiable so the app reads as one product, not five:

- Every chart title carries the gate caption: `f"{title}<br><sub>{cap}</sub>"`.
- Every party color comes from `lib.color()`.
- Every plot uses `st.plotly_chart(fig, width='stretch')`.
- Imputed rows get a hatched/striped marker or a "(imputed)" tooltip note.
- Hover tooltips include `count_tier`, `meta_tier`, `failure_modes` wherever the row identity matters.
- One `render(records, candidates, pages)` function per tab file. No top-level Streamlit calls.

Pin these in the README and in a comment at the top of `lib.py`.

---

## 8. Build order

1. `lib.py` ingestion + tier assignment + `clean_subset` + `color` + `load_data`.
2. `party_colors.json` — extract distinct parties from the data, fill major-party hex by hand, leave the rest at default grey.
3. `app.py` skeleton with empty tab stubs.
4. Our three tabs, in the order listed in §6.
5. Hand `lib.py` to the friend, point her at `tabs/eda.py` as the reference for how a tab should look.
6. Final pass: every chart obeys §7.

No separate notebooks. The Streamlit app *is* the report.

---

## 9. Implementation order (short)

1. Ingest JSONs → `records.parquet`, `candidates.parquet`, `pages.parquet`
2. Assign `count_tier` + `meta_tier` + imputation logic
3. Load + clean official government results → `official.parquet`
4. Join OCR records to official → compute field-level errors → `accuracy_report.csv`
5. `party_colors.json`
6. `lib.py` — `load_data` (all 4 parquets), `clean_subset`, `color`
7. `app.py` skeleton (3 tabs wired, stubs only)
8. `data_quality.py` — Section A (failure modes), then B (accuracy vs official), then C (spot-check queue)
9. `eda.py` — Section A (distributions, dual full/valid plots), then B (rankings tables)
10. `overview.py` — metric cards, tier composition bar, map placeholder
11. Export `data_quality_report.csv` + `spotcheck_queue.csv`
12. Final pass — checklist §9 on every chart

---

## 9. Self-review checklist

Before any tab is merged, every chart in it must pass all six:

- [ ] Title shows `n=X/Y` and the gate string.
- [ ] Calls `clean_subset()` — no inline `df[df.x.notna()]`.
- [ ] Uses `lib.color()` for any party-colored mark.
- [ ] Imputed rows visually distinguishable (or excluded with a note in the caption).
- [ ] Tooltip exposes `count_tier` / `meta_tier` / `failure_modes`.
- [ ] One `render()` function per tab file — no module-level Streamlit calls.
- [ ] Distribution charts (EDA tab) show **both** full-data and valid-only versions; if they differ meaningfully, the difference is noted as a finding (OCR bias), not silently hidden.

With this dataset, methodology is the deliverable. The checklist is what makes it visible.
