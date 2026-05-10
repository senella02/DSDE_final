# CLAUDE.md — Visualization Codebase

**Context:** Streamlit dashboard over Typhoon OCR output for นครราชสีมา เขต 5, 2026 Thai election. 3 อำเภอ: พิมาย, เฉลิมพระเกียรติ, โนนสูง. Election types: `normal`, `advance_out_of_district`, `advance_in_district`.

---

## File layout

```
Visualization/
├── app.py                        # Streamlit entry — 6 tabs
├── lib.py                        # load_data(), clean_subset(), color(), tiers
├── party_colors.json             # party → hex (UTF-8 Thai keys)
├── tabs/
│   ├── overview.py
│   ├── data_quality.py
│   ├── eda.py
│   ├── geo.py
│   └── swing_analysis.py
├── data/
│   ├── records.parquet           # 607 rows
│   ├── candidates.parquet        # 19,863 rows
│   ├── pages.parquet             # 1,794 rows
│   ├── official.parquet          # 69 rows — government totals, not per-station
│   ├── manifest/pdf_manifest.csv, page_manifest.csv
│   └── korat2023_data/district_2023.csv, partylist_2023.csv
└── reports/
    ├── data_quality_report.csv, spotcheck_queue.csv, accuracy_report.csv
    └── anomaly_flags.csv, cluster_labels.csv
```

---

## Parquet schemas

### `records.parquet` — 607 rows

| Column | Type | Notes |
|---|---|---|
| `file_id` | str | MD5 of source PDF |
| `election_type` | str | `normal` / `advance_in_district` / `advance_out_of_district` |
| `ballot_type` | str | `district` / `partylist` |
| `district`, `subdistrict`, `moo` | str/float | null for advance records |
| `station_number` | float | null for advance or badly-read records |
| `eligible_voters`, `voter_turnout` | float | normal only |
| `total_ballots`, `valid_votes`, `void_ballots`, `spoiled_ballots` | float | |
| `total_is_valid` | bool | valid+void+spoiled ≈ total (±1) |
| `candidate_sum_valid` | bool | Σ candidate votes ≈ valid_votes (±1) |
| `failure_modes` | str | Pipe-separated, e.g. `"candidate_sum_fail (sum=…) \| null_header_field:moo"` |
| `failure_mode_count` | int | |
| `count_tier` | str | A / B / C |
| `meta_tier` | str | M0 / M1 / M2 |
| `imputed_fields` | str | Fields derived by imputation |
| `turnout_rate`, `void_rate`, `spoil_rate` | float | Pre-computed ratios |

**Distribution:** normal=578, advance_out=20, advance_in=8 | district=306, partylist=300 | tier A=219, B=205, C=183 | M0=564, M1=35, M2=8 | 70% have ≥1 failure mode.

### `candidates.parquet` — 19,863 rows

| Column | Notes |
|---|---|
| `file_id` | FK to records |
| `ballot_type`, `election_type`, `district`, `subdistrict`, `station_number`, `count_tier`, `meta_tier` | Inherited from parent |
| `number` | Candidate/party number |
| `name` | null for partylist |
| `party` | Thai party name |
| `votes` | null if withdrawn **or** OCR missed — check `withdrawn` to distinguish |
| `withdrawn` | bool |

district=2,754 rows (9 candidates), partylist=17,100 rows.

### `pages.parquet` — 1,794 rows

| Column | Notes |
|---|---|
| `file_id` | FK to records |
| `page_no` | 1-based |
| `page_role` | `header` / `continuation` (split: 598 / 1,196) |
| `ocr_latency_sec` | Mean 8.75s, max 191.5s |
| `failure_modes`, `error` | Page-level issues |

### `official.parquet` — 69 rows

Use for OCR accuracy benchmarking only — aggregate totals, not per-station.  
Columns: `ballot_type`, `number`, `name`, `party`, `withdrawn`, `official_votes`, `vote_percent`, `official_valid_votes`, `official_void_ballots`, `official_spoiled_ballots`, `official_total_ballots`.

Official totals: **district** valid=87,644 / void=3,871 / spoiled=3,614 / total=95,129 | **partylist** valid=86,005 / void=5,849 / spoiled=3,277 / total=95,131.

---

## Validity model

### `count_tier` — ballot arithmetic

| Tier | Rule | Use for |
|---|---|---|
| A | total_is_valid ∧ candidate_sum_valid | Any aggregate |
| B | total_is_valid ∧ ¬candidate_sum_valid | Turnout/void/spoil % only |
| C | ¬total_is_valid | Spot-check queue only |

### `meta_tier` — geographic joinability

| Tier | Rule | Use for |
|---|---|---|
| M0 | district, subdistrict, station_number all present | Station-level joins |
| M1 | station_number or moo null | Subdistrict aggregates only |
| M2 | subdistrict null on a normal record | Spot-check only |

Advance records: null district/subdistrict/moo is expected; M-tier is set by `station_number` alone.  
**Imputation:** if exactly one of {total_ballots, valid_votes, void_ballots, spoiled_ballots} is null and the other three are present, it is derived. Runs before tier assignment.

---

## Data quality

### Top failure modes

| Mode | Records |
|---|---:|
| `candidate_sum_fail` | 318 |
| `ballot_math_fail` | 159 |
| `ocr_missed_candidates` | 60 |
| `null_header_field:total_ballots` | 41 |
| `null_header_field:spoiled_ballots` | 40 |
| `null_header_field:void_ballots` | 33 |
| `null_header_field:valid_votes` | 30 |
| `null_header_field:eligible_voters` | 28 |
| `null_header_field:moo` | 26 |
| `ocr_extra_candidates` | 25 |

Strip from `(` to get base mode name. ~45% of records have 2+ simultaneous failures. ~23 PDFs produced no parseable record. Nulls in `eligible_voters`/`moo`/`voter_turnout` are expected for advance records.

---

## OCR JSON schema

Each JSON is a **list** — always loop, never index `[0]`.

```
metadata: { file_id, pdf_name, processed_at, total_pages }
election_type, ballot_type, district, subdistrict, moo, station_number
eligible_voters, voter_turnout          (normal only)
total_ballots, valid_votes, void_ballots, spoiled_ballots
candidates: [ { number, name, party, votes, withdrawn } ]
total_is_valid, candidate_sum_valid
failure_modes: [ string ]
pages: [ { page_no, image_path, page_role, ocr_latency_sec, failure_modes, error } ]
```

- `name` null on partylist candidates.
- `district`/`subdistrict`/`moo` null for advance records — not an error.

---

## Coding conventions

**Tab signature:** one `render(records, candidates, pages, official)` per tab file. No module-level Streamlit calls.

**Filtering policy:**
- `data_quality.py`, `eda.py`: gate all aggregates via `clean_subset()`; attach `n=X/Y` caption to every chart.
- All other tabs (`overview`, `geo`, `swing_analysis`): plot all data; drop nulls only per-field for the specific chart; never call `clean_subset()` with a tier filter.

```python
# data_quality / eda only
from lib import clean_subset
sub, cap = clean_subset(records, count_tier="AB", requires=["voter_turnout", "eligible_voters"])
fig = px.histogram(sub, x="turnout_rate", title=f"Turnout Rate<br><sub>{cap}</sub>")
```

**All plots:** `st.plotly_chart(fig, use_container_width=True)`

**Party colors:** `from lib import color; color("เพื่อไทย")` — never inline hex codes.

**CSV encoding:** `utf-8-sig` (BOM) so Excel opens Thai strings correctly.
