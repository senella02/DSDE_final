# CLAUDE.md — DSDE Final Project (EDA + Data Quality track)

Working notes for the EDA / Data-Quality slice of the DSDE final project. This is the **baseline** — every other analysis on the team feeds off the cleaned dataset and the party color palette defined here.

---

## 1. Project context (from `Requirement.md`)

**Goal of this track:** understand the data, audit OCR quality, and produce the assets the team's downstream dashboards rely on.

The dataset comes from **Thai election ballot-count forms** (district 5, นครราชสีมา / โนนสูง area) that were scanned and processed by **Typhoon OCR**. We are NOT writing the OCR pipeline — we consume its JSON outputs.

---

## 2. Data overview

### 2.1 Files in this folder

| File / folder | What it is |
|---|---|
| `data/OCR_OUTPUT_JSON/*.json` | One JSON per PDF, ~400 files. **Each file is a list** of records (usually 2: one `district`, one `partylist`). |
| `pdf_manifest.csv` | 400 rows. Source PDFs with `file_id`, `file_path`, `election_type`, `area_scope`, `district`, `subdistrict`, `station_no`, `pdf_name`. Authoritative list of input PDFs. |
| `page_manifest.csv` | 1,887 rows. Per-page tracking (`file_id`, `page_no`, `image_path`, `status`). |
| `reports/QA.csv` | 606 rows. Pre-computed QA flags per ballot record (see §4). |
| `Requirement.md` | The brief (Thai). |

### 2.2 Counts at a glance

- **377** unique `file_id`s appear in `QA.csv` (out of 400 PDFs in the manifest → ~23 PDFs produced no parseable record).
- **606** ballot records in QA.csv. Most PDFs contribute 2 records (district + partylist); 149 contribute 1; one PDF contributes 3.
- Election-type split: `normal` 577, `advance_out_of_district` 20, `advance_in_district` 8.
- Ballot-type split: `district` 331, `partylist` 274.

### 2.3 JSON record schema (per item in the list)

```
metadata: { file_id, pdf_name, processed_at, total_pages }
election_type      : "normal" | "advance_in_district" | "advance_out_of_district"
ballot_type        : "district" | "partylist"
district / subdistrict / moo  : present only when election_type == "normal"
station_number     : int
eligible_voters    : int (normal only)
voter_turnout      : int (normal only)
total_ballots      : int
valid_votes        : int   (บัตรดี)
void_ballots       : int   (บัตรเสีย)
spoiled_ballots    : int   (บัตรไม่เลือก)
candidates: [ { number, name, party, votes, withdrawn } ]
total_is_valid     : bool   — valid + void + spoiled ≈ total_ballots (±1)
candidate_sum_valid: bool   — sum(candidate.votes) ≈ valid_votes (±1)
validation_message / candidate_sum_message : human-readable reason
failure_modes      : [ string ]   — see §4 for taxonomy
pages              : [ { page_no, image_path, page_role, ocr_latency_sec, failure_modes, error, raw_ocr } ]
```

**Schema gotchas to remember while coding:**
- A single JSON file = a **list**, not a dict. Loop, don't index `[0]`.
- `district` / `subdistrict` / `moo` are `null` for advance-vote records — don't filter them out blindly.
- `candidates[i].votes` is `null` if the candidate withdrew **or** if OCR missed the row. Distinguish via `withdrawn`.
- `partylist` records always have `name = null` (it's a party-only ballot).
- Sample file checked: `dca1df07d6175b0ec5fc8bd5ec5f9b4a.json` — โนนสูง station 14. Both district and partylist records have `candidate_sum_fail` due to OCR missing tail rows of the candidate table. Pattern is common.

---

## 3. Data abnormalities (from `QA.csv`, n = 606)

| Abnormality | Count | % of records |
|---|---:|---:|
| Has at least one failure mode | 433 | 71.5% |
| Clean (no failure modes) | 173 | 28.5% |
| `total_is_valid == False` (ballot math broken) | 210 | 34.7% |
| `candidate_sum_valid == False` (votes ≠ valid) | 371 | 61.2% |
| `both_valid == True` (passes both) | 194 | 32.0% |

**Failure-mode frequencies** (counted per occurrence; a record can have several):

| Mode | Count | Meaning |
|---|---:|---|
| `candidate_sum_fail` | 330 | Σ candidate votes ≠ `valid_votes` — usually OCR missed candidate rows. |
| `null_header_field:*` | 216 | A header number couldn't be extracted. Breakdown below. |
| `ballot_math_fail` | 156 | `valid + void + spoiled` ≠ `total_ballots`. |
| `ocr_missed_candidates:[…]` | 60 | Specific candidate rows present in reference but not in OCR output. |
| `ocr_extra_candidates:[…]` | 51 | OCR hallucinated rows not in reference list. |
| `no_candidates_parsed` | 2 | Whole candidate table missing. |

**Which header fields go null most often:**

```
total_ballots      44
spoiled_ballots    41
void_ballots       34
valid_votes        31
moo                26
eligible_voters    26
voter_turnout       8
station_number      4
district            2
```

Distribution of failure-mode count per record: median 1, max 7. About **45%** of records have 2+ simultaneous failures, so QA logic should be additive, not exclusive.

**Implication for EDA:** the "valid_votes" and aggregate ballot fields are noisy. Any aggregate (turnout %, void rate, party share) should be computed only over rows where the relevant fields are non-null AND the relevant validity flag is True, and the report should always show the denominator we kept.

---

## 4. Our task breakdown

Strictly the **EDA + Data Quality** track. Other team members handle modeling, geo-mapping, etc. The primary deliverable is a **Streamlit app** (`app.py`) with three tabs; standalone plot files are not produced.

1. **Ingest & flatten.** Walk `OCR_OUTPUT_JSON/`, expand each list, build three long DataFrames and persist as Parquet under `data/`:
   - `data/records.parquet` — one row per ballot record (district or partylist) with header fields, validity flags, `count_tier`, `meta_tier`, and `imputed_fields`.
   - `data/candidates.parquet` — one row per candidate-vote, FK = `(file_id, ballot_type)`.
   - `data/pages.parquet` — one row per page, from `pages[]` inside each JSON record.

2. **Load official results.** Ingest government ground-truth into `data/official.parquet`. Join key: `(station_number, subdistrict, ballot_type)`. Compute per-field OCR errors → `reports/accuracy_report.csv`.

3. **Define the canonical party color palette.** Single source of truth for party → hex color. Save as `party_colors.json`. Keys must match the `party` strings exactly as they appear in the JSON (be careful with Thai whitespace).

4. **Streamlit app — three tabs** (see `solution.md §6` for full specs):
   - **Overview** — five headline metric cards + tier composition bar + map placeholder.
   - **Data Quality** — failure-mode analysis, OCR accuracy vs official, spot-check queue. Exports `reports/data_quality_report.csv` and `reports/spotcheck_queue.csv` via download buttons.
   - **EDA** — distributions (full vs valid-only, side-by-side) and station/party rankings.

---

## 5. Deliverables

| Deliverable | Path | Format | Notes |
|---|---|---|---|
| Streamlit app | `app.py`, `lib.py`, `tabs/` | py | Primary deliverable — three tabs. |
| Ballot records | `data/records.parquet` | parquet | One row per ballot record; includes `count_tier`, `meta_tier`, `imputed_fields`. |
| Candidate votes | `data/candidates.parquet` | parquet | One row per candidate-vote. |
| Page metadata | `data/pages.parquet` | parquet | One row per scanned page. |
| Official results | `data/official.parquet` | parquet | Government ground truth; join key `(station_number, subdistrict, ballot_type)`. |
| Party palette | `party_colors.json` | json | `{ "เพื่อไทย": "#…", … }` — used project-wide. |
| QA report | `reports/data_quality_report.csv` | csv | Per-record QA + failure-mode flags. |
| Spot-check queue | `reports/spotcheck_queue.csv` | csv | Records with `count_tier=C` or ≥3 failure modes. |
| Accuracy report | `reports/accuracy_report.csv` | csv | Per-record OCR vs official field-level errors + QA calibration flags. |

**Tooling:** pandas, plotly, streamlit. Keep numpy/pandas idioms simple — other teammates will read this.

---

## 6. Working conventions

- **Paths.** All notebooks/scripts read from `./data/OCR_OUTPUT_JSON/` and `./*.csv`. Don't hard-code absolute paths.
- **Encoding.** All Thai strings are UTF-8. When writing CSVs use `utf-8-sig` so Excel opens them cleanly.
- **Validity gates.** Before computing aggregates, document which rows you dropped and why. Never silently exclude.
- **Color palette.** Whenever a chart shows parties, import the shared palette — never invent ad-hoc colors per notebook.
