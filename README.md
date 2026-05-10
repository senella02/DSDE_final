# Visualization — Thai Election 2026 EDA Dashboard

Streamlit app for exploring and validating OCR-extracted Thai election ballot data from Nakhon Ratchasima District 5 (292 polling stations, 3 อำเภอ).

## What it does

The app sits downstream of an OCR pipeline that reads handwritten vote counts from scanned ballot forms (ส.ส.5/16, 5/17, 5/18). It normalizes ~3 000 raw JSON outputs into structured parquets, validates ballot arithmetic, tiers records by data quality, and exposes six analysis tabs:

| Tab | Purpose |
|---|---|
| Overview | KPIs, tier composition, election-type breakdown |
| Data Quality | OCR failure modes, accuracy vs official ECT results, spot-check queue |
| EDA | Vote distributions, candidate/party rankings |
| Geospatial | Choropleth turnout, winner markers, district-level spatial analysis |
| Anomaly Detection | Rule-based flags (perfect turnout, zero ballots, high void/spoil) + Z-score outliers |
| Swing Analysis | 2023 → 2026 net gain/loss, split-ticket voting patterns |

## Quick start

```bash
conda run -n dsde streamlit run app.py
```

On first run, the ingestion pipeline walks `OCR_OUTPUT_JSON-*/`, builds four parquets under `data/`, and caches them. Subsequent runs skip ingestion.

## Project structure

```
app.py                  # Entry point, tab routing
lib.py                  # Data loading, quality filtering, party color lookup
party_colors.json       # Party → hex (single source of truth)
tabs/                   # One module per tab
anomaly/                # Rule-based + statistical anomaly detection
data/
  records.parquet       # 606 rows — one per ballot record (district or partylist)
  candidates.parquet    # 18 606 rows — candidate votes, exploded from records
  pages.parquet         # 1 793 rows — per-page OCR metadata
  official.parquet      # 69 rows — ECT official results (ground truth)
  manifest/             # Geo remapping overrides (pdf_manifest.csv)
  official_data/        # Raw government result JSONs
  korat2023_data/       # 2023 election data for swing analysis
  OCR_OUTPUT_JSON-*/    # Raw OCR outputs (not committed)
```

## Data quality tiers

Every analysis should be gated by `count_tier` before aggregating. The tier is assigned per ballot record:

| Tier | Condition |
|---|---|
| A | Ballot math valid (`valid + void + spoiled ≈ total`) **and** candidate sum matches |
| B | Ballot math valid, candidate sum off |
| C | Ballot math broken |

Geo completeness is tracked separately as `meta_tier` (M0 = full geo, M1 = station/district missing, M2 = subdistrict null on a normal record).

## Parquet schemas

**`records.parquet`** — core unit of analysis. Key columns: `file_id`, `election_type` (`normal` / `advance_in_district` / `advance_out_of_district`), `ballot_type` (`district` / `partylist`), `station_number`, `eligible_voters`, `voter_turnout`, `total_ballots`, `valid_votes`, `void_ballots`, `spoiled_ballots`, `count_tier`, `meta_tier`, `failure_modes`, `turnout_rate`, `void_rate`, `spoil_rate`.

**`candidates.parquet`** — vote per candidate/party. Key columns: `file_id`, `ballot_type`, `number`, `name`, `party`, `votes`, `withdrawn`, `count_tier`, `meta_tier`. Join to `records` on `file_id + ballot_type`.

**`pages.parquet`** — OCR diagnostic. Key columns: `file_id`, `page_no`, `page_role` (`header` / `continuation`), `ocr_latency_sec`, `failure_modes`, `error`.

**`official.parquet`** — ECT ground truth for accuracy measurement only. 9 district candidates + 60 partylist parties. Aggregate OCR records by `ballot_type` before comparing — per-station official data is not available.
