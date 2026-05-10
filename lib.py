"""
lib.py — DSDE Election OCR shared utilities
Conventions (enforced project-wide):
  - Every chart title carries the gate caption: f"{title}<br><sub>{cap}</sub>"
  - Every party color comes from color()
  - Every plot uses st.plotly_chart(fig, width='stretch')
  - One render(records, candidates, pages, official) function per tab file — no module-level st calls
"""

import json
import re
from pathlib import Path

import pandas as pd

import streamlit as st

# ---------- Paths ----------

_HERE = Path(__file__).parent
GOVT_DIR = _HERE / "data" / "official_data"
DATA_DIR = _HERE / "data"
REPORTS_DIR = _HERE / "reports"
PALETTE_PATH = _HERE / "party_colors.json"

_BALLOT_FIELDS = ["total_ballots", "valid_votes", "void_ballots", "spoiled_ballots"]

MANIFEST_PATH = DATA_DIR / "manifest/pdf_manifest.csv"
REPORT_PATH = REPORTS_DIR / "report.json"

PARQUET_FILES = [
    DATA_DIR / "records.parquet",
    DATA_DIR / "candidates.parquet",
    DATA_DIR / "pages.parquet",
    DATA_DIR / "official.parquet",
]


def _find_ocr_dir() -> Path | None:
    dirs = sorted(_HERE.glob("data/OCR_OUTPUT_JSON"))
    return dirs[-1] if dirs else None


OCR_DIR = _find_ocr_dir()


# ---------- Palette ----------


def _load_palette() -> dict:
    if PALETTE_PATH.exists():
        return json.loads(PALETTE_PATH.read_text(encoding="utf-8"))
    return {}


PALETTE: dict = _load_palette()


def color(party) -> str:
    """Hex color for a party name or partylist number (int or numeric string); grey fallback."""
    if isinstance(party, (int, float)):
        return PALETTE.get(str(int(party)), "#B0B0B0")
    key = (party or "").strip()
    return PALETTE.get(key, "#B0B0B0")


# ---------- Validity gate ----------


def clean_subset(
    df: pd.DataFrame,
    *,
    count_tier=None,
    meta_tier=None,
    requires=None,
) -> tuple[pd.DataFrame, str]:
    """
    Filter df and return (filtered_df, caption_string).

    count_tier : iterable of tier letters, e.g. "AB" or ["A","B"]
    meta_tier  : iterable of tier strings, e.g. ["M0"]
    requires   : list of column names that must be non-null
    """
    out, parts = df.copy(), []
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
    caption = f"n={len(out)}/{len(df)} • " + (
        " ∧ ".join(parts) if parts else "all rows"
    )
    return out, caption


# ---------- JSON helpers ----------


def _load_json_file(path: Path) -> list:
    """Load JSON, converting bare NaN (Python serialiser artifact) to null."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"\bNaN\b", "null", text)
    return json.loads(text)


# ---------- Imputation ----------


def _impute_ballot_fields(rec: dict) -> list[str]:
    """
    If exactly one of the four ballot header fields is null and the other three
    are present, derive the missing value in-place.
    Returns the list of field names that were imputed (empty if none).
    """
    missing = [f for f in _BALLOT_FIELDS if rec.get(f) is None]
    if len(missing) != 1:
        return []
    present = {f: rec[f] for f in _BALLOT_FIELDS if f not in missing}
    if any(v is None for v in present.values()):
        return []

    m = missing[0]
    tb = present.get("total_ballots")
    vv = present.get("valid_votes")
    vb = present.get("void_ballots")
    sb = present.get("spoiled_ballots")

    if m == "total_ballots":
        rec["total_ballots"] = vv + vb + sb
    elif m == "valid_votes":
        rec["valid_votes"] = tb - vb - sb
    elif m == "void_ballots":
        rec["void_ballots"] = tb - vv - sb
    elif m == "spoiled_ballots":
        rec["spoiled_ballots"] = tb - vv - vb

    return [m]


# ---------- Tier assignment ----------


def _count_tier(rec: dict, imputed: list[str]) -> str:
    total_is_valid = rec.get("total_is_valid", False)
    candidate_sum_valid = rec.get("candidate_sum_valid", False)

    # Re-evaluate ballot math if we imputed a header field
    if imputed:
        tb = rec.get("total_ballots")
        vv = rec.get("valid_votes")
        vb = rec.get("void_ballots")
        sb = rec.get("spoiled_ballots")
        if None not in (tb, vv, vb, sb):
            total_is_valid = abs((vv + vb + sb) - tb) <= 1

    if total_is_valid and candidate_sum_valid:
        return "A"
    if total_is_valid:
        return "B"
    return "C"


def _meta_tier(rec: dict) -> str:
    election_type = rec.get("election_type", "normal")

    if election_type == "normal":
        # subdistrict null on normal record → worst tier
        if rec.get("subdistrict") is None:
            return "M2"
        # missing district or station_number → can only aggregate at subdistrict level
        if rec.get("district") is None or rec.get("station_number") is None:
            return "M1"
        return "M0"

    # Advance records: null geo fields are expected by schema
    return "M0" if rec.get("station_number") is not None else "M1"


# ---------- Ingestion ----------


def ingest_json_to_parquet() -> None:
    """Walk OCR_OUTPUT_JSON/, build the three data parquets, then load official."""
    DATA_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)

    rec_rows: list[dict] = []
    cand_rows: list[dict] = []
    page_rows: list[dict] = []

    for json_path in sorted(OCR_DIR.glob("*.json")):
        try:
            records = _load_json_file(json_path)
        except Exception as exc:
            print(f"[WARN] skip {json_path.name}: {exc}")
            continue

        if not isinstance(records, list):
            records = [records]

        for rec in records:
            meta = rec.get("metadata", {})
            file_id = meta.get("file_id", json_path.stem)
            ballot_type = rec.get("ballot_type", "unknown")

            imputed = _impute_ballot_fields(rec)

            failure_modes = rec.get("failure_modes", [])
            if isinstance(failure_modes, str):
                failure_modes = [failure_modes]

            row: dict = {
                "file_id": file_id,
                "pdf_name": meta.get("pdf_name"),
                "processed_at": meta.get("processed_at"),
                "total_pages": meta.get("total_pages"),
                "election_type": rec.get("election_type"),
                "ballot_type": ballot_type,
                "district": rec.get("district"),
                "subdistrict": rec.get("subdistrict"),
                "moo": rec.get("moo"),
                "station_number": rec.get("station_number"),
                "eligible_voters": rec.get("eligible_voters"),
                "voter_turnout": rec.get("voter_turnout"),
                "total_ballots": rec.get("total_ballots"),
                "valid_votes": rec.get("valid_votes"),
                "void_ballots": rec.get("void_ballots"),
                "spoiled_ballots": rec.get("spoiled_ballots"),
                "total_is_valid": rec.get("total_is_valid", False),
                "candidate_sum_valid": rec.get("candidate_sum_valid", False),
                "validation_message": rec.get("validation_message"),
                "candidate_sum_message": rec.get("candidate_sum_message"),
                "failure_modes": " | ".join(failure_modes),
                "failure_mode_count": len(failure_modes),
                "imputed_fields": ",".join(imputed),
            }

            row["count_tier"] = _count_tier(rec, imputed)
            row["meta_tier"] = _meta_tier(rec)

            ev = row["eligible_voters"]
            vt = row["voter_turnout"]
            tb = row["total_ballots"]
            vb = row["void_ballots"]
            sb = row["spoiled_ballots"]

            row["turnout_rate"] = (vt / ev) if (ev and vt is not None) else None
            row["void_rate"] = (vb / tb) if (tb and vb is not None) else None
            row["spoil_rate"] = (sb / tb) if (tb and sb is not None) else None

            rec_rows.append(row)

            for cand in rec.get("candidates", []):
                cand_rows.append(
                    {
                        "file_id": file_id,
                        "ballot_type": ballot_type,
                        "election_type": rec.get("election_type"),
                        "district": rec.get("district"),
                        "subdistrict": rec.get("subdistrict"),
                        "station_number": rec.get("station_number"),
                        "count_tier": row["count_tier"],
                        "meta_tier": row["meta_tier"],
                        "number": cand.get("number"),
                        "name": cand.get("name"),
                        "party": cand.get("party"),
                        "votes": cand.get("votes"),
                        "withdrawn": cand.get("withdrawn", False),
                    }
                )

            for page in rec.get("pages", []):
                pf = page.get("failure_modes", [])
                if isinstance(pf, str):
                    pf = [pf]
                page_rows.append(
                    {
                        "file_id": file_id,
                        "ballot_type": ballot_type,
                        "page_no": page.get("page_no"),
                        "image_path": page.get("image_path"),
                        "page_role": page.get("page_role"),
                        "ocr_latency_sec": page.get("ocr_latency_sec"),
                        "failure_modes": " | ".join(pf),
                        "error": page.get("error"),
                    }
                )

    pd.DataFrame(rec_rows).to_parquet(DATA_DIR / "records.parquet", index=False)
    pd.DataFrame(cand_rows).to_parquet(DATA_DIR / "candidates.parquet", index=False)
    pd.DataFrame(page_rows).to_parquet(DATA_DIR / "pages.parquet", index=False)

    _ingest_official()


# ---------- Official data ----------


def _parse_score(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    cleaned = str(val).replace(",", "").strip()
    return int(cleaned) if cleaned.isdigit() else None


def _parse_percent(val) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = str(val).replace("%", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_number_field(val) -> int | None:
    """Extract integer from strings like 'เบอร์ 37' or plain '37'."""
    if val is None:
        return None
    if isinstance(val, int):
        return val
    m = re.search(r"\d+", str(val))
    return int(m.group()) if m else None


def _ingest_official() -> None:
    """Load government ground-truth JSONs into data/official.parquet."""
    ballot_counts = _load_json_file(GOVT_DIR / "ballot_count.json")
    district_scores = _load_json_file(GOVT_DIR / "district_scores.json")
    district_candidates = _load_json_file(GOVT_DIR / "district_candidate.json")
    partylist_scores = _load_json_file(GOVT_DIR / "partylist_scores.json")
    partylist_candidates = _load_json_file(GOVT_DIR / "partylist_candidates.json")

    dc_map = {int(c["number"]): c for c in district_candidates}
    pl_map = {int(c["number"]): c for c in partylist_candidates}
    bc_map = {b["ballot_type"]: b for b in ballot_counts}

    rows: list[dict] = []

    # District candidates
    bc_d = bc_map.get("district", {})
    d_total = (
        (bc_d.get("valid_votes") or 0)
        + (bc_d.get("void_ballots") or 0)
        + (bc_d.get("spoiled_ballots") or 0)
        if bc_d
        else None
    )
    for s in district_scores:
        num = _parse_number_field(s.get("number"))
        meta = dc_map.get(num, {})
        rows.append(
            {
                "ballot_type": "district",
                "number": num,
                "name": meta.get("name"),
                "party": meta.get("party"),
                "withdrawn": meta.get("withdrawn", False),
                "official_votes": _parse_score(s.get("score")),
                "vote_percent": _parse_percent(s.get("percent")),
                "official_valid_votes": bc_d.get("valid_votes"),
                "official_void_ballots": bc_d.get("void_ballots"),
                "official_spoiled_ballots": bc_d.get("spoiled_ballots"),
                "official_total_ballots": d_total,
            }
        )

    # Partylist parties
    bc_p = bc_map.get("partylist", {})
    p_total = (
        (bc_p.get("valid_votes") or 0)
        + (bc_p.get("void_ballots") or 0)
        + (bc_p.get("spoiled_ballots") or 0)
        if bc_p
        else None
    )
    for s in partylist_scores:
        num = _parse_number_field(s.get("number"))
        meta = pl_map.get(num, {}) if num else {}
        rows.append(
            {
                "ballot_type": "partylist",
                "number": num,
                "name": None,
                "party": s.get("party"),
                "withdrawn": False,
                "official_votes": _parse_score(s.get("score")),
                "vote_percent": _parse_percent(s.get("percent")),
                "official_valid_votes": bc_p.get("valid_votes"),
                "official_void_ballots": bc_p.get("void_ballots"),
                "official_spoiled_ballots": bc_p.get("spoiled_ballots"),
                "official_total_ballots": p_total,
            }
        )

    pd.DataFrame(rows).to_parquet(DATA_DIR / "official.parquet", index=False)


# ---------- Geo remapping ----------


def _remap_geo_from_manifest(records: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Override district/subdistrict in records with pdf_manifest.csv ground truth.
    Advance records (no manifest geo) are left untouched.
    Returns (corrected_df, mismatch_stats).
    """
    if not MANIFEST_PATH.exists():
        return records, {"error": f"{MANIFEST_PATH.name} not found"}

    manifest = (
        pd.read_csv(MANIFEST_PATH, dtype=str)[["file_id", "district", "subdistrict"]]
        .drop_duplicates("file_id")
        .rename(columns={"district": "m_district", "subdistrict": "m_subdistrict"})
    )

    out = records.reset_index(drop=True).copy()
    merged = out.merge(manifest, on="file_id", how="left")

    stats: dict = {"total_records": len(out)}

    for ocr_col, man_col in [
        ("district", "m_district"),
        ("subdistrict", "m_subdistrict"),
    ]:
        has_manifest = merged[man_col].notna()
        ocr_null = merged[ocr_col].isna()
        differs = merged[ocr_col].fillna("\x00") != merged[man_col].fillna("\x00")

        null_filled = int((has_manifest & ocr_null).sum())
        value_changed = int((has_manifest & ~ocr_null & differs).sum())
        unchanged = int((has_manifest & ~ocr_null & ~differs).sum())

        stats[ocr_col] = {
            "null_filled": null_filled,
            "value_changed": value_changed,
            "unchanged": unchanged,
            "total_remapped": null_filled + value_changed,
        }

        out.loc[has_manifest, ocr_col] = merged.loc[has_manifest, man_col].values

    return out, stats


def _write_report(section: str, data: dict) -> None:
    """Upsert a named section in reports/report.json."""
    REPORTS_DIR.mkdir(exist_ok=True)
    report: dict = {}
    if REPORT_PATH.exists():
        try:
            report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    report[section] = data
    report["last_updated"] = pd.Timestamp.now().isoformat()
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------- Debug helpers ----------


def print_head() -> None:
    """Print the first 3 rows of each parquet file."""
    for path in PARQUET_FILES:
        print(f"\n{'=' * 60}")
        print(f"  {path.name}")
        print(f"{'=' * 60}")
        if not path.exists():
            print("  [not found]")
            continue
        df = pd.read_parquet(path)
        print(df.head(3).to_string())


# ---------- Entry point ----------


@st.cache_data
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load (or build) all four parquets. Cached by Streamlit."""
    if not all(p.exists() for p in PARQUET_FILES):
        if OCR_DIR is None:
            raise FileNotFoundError(
                "No OCR_OUTPUT_JSON-* directory found next to lib.py"
            )
        ingest_json_to_parquet()
    records = pd.read_parquet(DATA_DIR / "records.parquet")
    records, geo_stats = _remap_geo_from_manifest(records)
    _write_report("geo_remapping", geo_stats)
    return (
        records,
        pd.read_parquet(DATA_DIR / "candidates.parquet"),
        pd.read_parquet(DATA_DIR / "pages.parquet"),
        pd.read_parquet(DATA_DIR / "official.parquet"),
    )
