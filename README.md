# Visualization — EDA + Data Quality

Streamlit app over OCR'd Thai election ballot forms (District 5, Nakhon Ratchasima).

## Quick start

```bash
streamlit run app.py
```

On first run, `load_data()` walks the `OCR_OUTPUT_JSON-*/` folder and writes four parquets under `data/`. Subsequent runs load from cache.

---

## lib.py — public API

### `load_data() → (records, candidates, pages, official)`
Call this once in `app.py`. Builds parquets if missing, then reads them. Cached by Streamlit.

### `clean_subset(df, *, count_tier, meta_tier, requires) → (df, caption)`
The **only** way tabs should filter before plotting. Returns the filtered DataFrame and a caption string like `n=207/606 • count∈{'A'} ∧ notna(voter_turnout)` that goes in every chart title.

```python
sub, cap = clean_subset(records, count_tier="AB", requires=["voter_turnout"])
fig = px.histogram(sub, x="turnout_rate", title=f"Turnout<br><sub>{cap}</sub>")
```

| Argument | Type | Meaning |
|---|---|---|
| `count_tier` | iterable | `"A"`, `"AB"`, `["A","B"]` — filter by count integrity |
| `meta_tier` | iterable | `["M0"]`, `["M0","M1"]` — filter by geo completeness |
| `requires` | list[str] | column names that must be non-null |

### `color(party) → str`
Returns the hex color for a party name. Falls back to `#B0B0B0` for unknowns. Import this — never hard-code hex values per chart.

---

## Parquets

### `data/records.parquet` — one row per ballot record
Each JSON file produces 1–2 records (one `district`, one `partylist`). 606 rows total.

| Column | Notes |
|---|---|
| `file_id` | MD5 of the source PDF |
| `election_type` | `normal` / `advance_in_district` / `advance_out_of_district` |
| `ballot_type` | `district` or `partylist` |
| `district`, `subdistrict`, `moo`, `station_number` | Null for advance records (expected) |
| `eligible_voters`, `voter_turnout` | Normal records only; null for advance |
| `total_ballots`, `valid_votes`, `void_ballots`, `spoiled_ballots` | Header counts; one field may be imputed |
| `total_is_valid` | `valid + void + spoiled ≈ total_ballots` (±1) |
| `candidate_sum_valid` | `Σ candidate votes ≈ valid_votes` (±1) |
| `failure_modes` | Pipe-separated OCR failure tags (e.g. `candidate_sum_fail \| null_header_field:moo`) |
| `failure_mode_count` | Integer count of failure modes |
| `imputed_fields` | Comma-separated field names that were derived (empty if none) |
| `count_tier` | **A** = both checks pass · **B** = ballot math ok, candidate sum off · **C** = ballot math broken |
| `meta_tier` | **M0** = district+subdistrict+station all present · **M1** = station or district missing · **M2** = subdistrict null on normal record |
| `turnout_rate`, `void_rate`, `spoil_rate` | Pre-computed ratios (null if inputs missing) |

**Use `count_tier` as the primary validity gate before any aggregate.**

### `data/candidates.parquet` — one row per candidate-vote
18 606 rows. Each record's candidate list is exploded here.

| Column | Notes |
|---|---|
| `file_id`, `ballot_type` | FK back to `records.parquet` |
| `election_type`, `district`, `subdistrict`, `station_number` | Denormalised from parent record |
| `count_tier`, `meta_tier` | Copied from parent — use to gate before aggregating votes |
| `number` | Candidate/party list number |
| `name` | Candidate name; always `null` for `partylist` records |
| `party` | Party name |
| `votes` | OCR-read vote count; `null` if withdrawn **or** OCR missed the row |
| `withdrawn` | `true` if the candidate withdrew before election day |

### `data/pages.parquet` — one row per scanned page
1 793 rows. Derived from the `pages[]` array inside each JSON record.

| Column | Notes |
|---|---|
| `file_id`, `ballot_type` | FK back to `records.parquet` |
| `page_no` | Page number within the PDF |
| `image_path` | Path to the rendered PNG (Google Drive path from OCR pipeline) |
| `page_role` | `header` (first page of a form) or `continuation` |
| `ocr_latency_sec` | Time the vision LLM spent on this page |
| `failure_modes` | Pipe-separated page-level failure tags |
| `error` | Raw error string if OCR crashed on this page |

### `data/official.parquet` — government ground truth
69 rows (9 district candidates + 60 partylist parties). Used for OCR accuracy measurement only — not for election-outcome claims.

| Column | Notes |
|---|---|
| `ballot_type` | `district` or `partylist` |
| `number` | Candidate/party list number |
| `name`, `party` | From `data/official_data/district_candidate.json` / `partylist_candidates.json` |
| `official_votes` | Official vote count from ECT results |
| `vote_percent` | Official percentage |
| `official_valid_votes`, `official_void_ballots`, `official_spoiled_ballots`, `official_total_ballots` | District-wide aggregates (same value repeated per row within a ballot_type) |

**Join key to OCR data:** aggregate OCR records by `ballot_type` (summing valid/void/spoiled), then compare to the official totals. Per-station official data is not available.

---

## party_colors.json
Single source of truth for party → hex. Always access via `lib.color(party)`. Major parties have hand-assigned official hex; all others resolve to `#B0B0B0` via the fallback.
