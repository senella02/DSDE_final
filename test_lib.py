"""
test.py — verify data loading functions in lib.py

Run with:  conda run -n dsde python test.py
Each test prints PASS / FAIL with a reason.
"""
import sys
import traceback
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"

_results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = PASS if condition else FAIL
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    _results.append((name, condition, detail))


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Import lib (without triggering st.cache_data)
# ---------------------------------------------------------------------------

section("Import")
try:
    import lib
    check("import lib", True)
except Exception as e:
    check("import lib", False, str(e))
    print("\nCannot continue — lib.py failed to import.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 1. Paths
# ---------------------------------------------------------------------------

section("1. Paths")

check(
    "OCR_DIR found",
    lib.OCR_DIR is not None,
    str(lib.OCR_DIR) if lib.OCR_DIR else "None — data/OCR_OUTPUT_JSON missing?",
)

check(
    "DATA_DIR exists",
    lib.DATA_DIR.exists(),
    str(lib.DATA_DIR),
)

# GOVT_DIR is defined as _HERE / "government_data" in lib.py.
# The actual folder is data/official_data — flag the mismatch.
govt_ok = lib.GOVT_DIR.exists()
check(
    "GOVT_DIR exists",
    govt_ok,
    str(lib.GOVT_DIR)
    + ("" if govt_ok else "  ← MISMATCH: actual data is in data/official_data/"),
)

check(
    "PALETTE_PATH exists",
    lib.PALETTE_PATH.exists(),
    str(lib.PALETTE_PATH),
)

# ---------------------------------------------------------------------------
# 2. Parquet files readable
# ---------------------------------------------------------------------------

section("2. Parquet files")

PARQUET_NAMES = ["records", "candidates", "pages", "official"]
frames: dict[str, pd.DataFrame] = {}

for name in PARQUET_NAMES:
    path = lib.DATA_DIR / f"{name}.parquet"
    try:
        df = pd.read_parquet(path)
        frames[name] = df
        check(f"{name}.parquet readable", True, f"{len(df):,} rows × {len(df.columns)} cols")
    except Exception as e:
        check(f"{name}.parquet readable", False, str(e))

# ---------------------------------------------------------------------------
# 3. records.parquet schema
# ---------------------------------------------------------------------------

section("3. records.parquet — schema & values")

if "records" in frames:
    rec = frames["records"]

    REQUIRED_COLS = [
        "file_id", "ballot_type", "election_type",
        "district", "subdistrict", "station_number",
        "total_ballots", "valid_votes", "void_ballots", "spoiled_ballots",
        "total_is_valid", "candidate_sum_valid",
        "count_tier", "meta_tier", "imputed_fields",
        "turnout_rate", "void_rate", "spoil_rate",
    ]
    missing_cols = [c for c in REQUIRED_COLS if c not in rec.columns]
    check("required columns present", not missing_cols, f"missing: {missing_cols}" if missing_cols else "all present")

    check(
        "count_tier values ⊆ {A,B,C}",
        set(rec["count_tier"].dropna().unique()).issubset({"A", "B", "C"}),
        str(rec["count_tier"].value_counts().to_dict()),
    )
    check(
        "meta_tier values ⊆ {M0,M1,M2}",
        set(rec["meta_tier"].dropna().unique()).issubset({"M0", "M1", "M2"}),
        str(rec["meta_tier"].value_counts().to_dict()),
    )
    check(
        "ballot_type values ⊆ {district,partylist}",
        set(rec["ballot_type"].dropna().unique()).issubset({"district", "partylist"}),
        str(rec["ballot_type"].value_counts().to_dict()),
    )
    check(
        "election_type values ⊆ expected set",
        set(rec["election_type"].dropna().unique()).issubset(
            {"normal", "advance_in_district", "advance_out_of_district"}
        ),
        str(rec["election_type"].value_counts().to_dict()),
    )
    _dup_mask = rec.duplicated(subset=["file_id", "ballot_type"], keep=False)
    check(
        "no duplicate file_id+ballot_type",
        not _dup_mask.any(),
        f"{_dup_mask.sum()} duplicates",
    )
    if _dup_mask.any():
        print(rec[_dup_mask][["file_id", "ballot_type", "election_type", "district", "subdistrict", "station_number"]].to_string(index=False))
    _tr = rec["turnout_rate"].dropna()
    _tr_ok = _tr.between(0, 1).all()
    check(
        "turnout_rate in [0,1] where not null",
        _tr_ok,
        f"min={rec['turnout_rate'].min():.3f} max={rec['turnout_rate'].max():.3f}",
    )
    if not _tr_ok:
        _bad = rec[rec["turnout_rate"].notna() & ~rec["turnout_rate"].between(0, 1)]
        print(f"    Error rows ({len(_bad)}):")
        print(_bad[["file_id", "ballot_type", "election_type", "station_number",
                     "voter_turnout", "eligible_voters", "turnout_rate"]].to_string(index=False))

# ---------------------------------------------------------------------------
# 4. candidates.parquet schema
# ---------------------------------------------------------------------------

section("4. candidates.parquet — schema & values")

if "candidates" in frames:
    cand = frames["candidates"]

    CAND_COLS = [
        "file_id", "ballot_type", "election_type",
        "district", "subdistrict", "station_number",
        "count_tier", "meta_tier",
        "number", "name", "party", "votes", "withdrawn",
    ]
    missing_cand = [c for c in CAND_COLS if c not in cand.columns]
    check("required columns present", not missing_cand, f"missing: {missing_cand}" if missing_cand else "all present")

    check(
        "votes non-negative where not null",
        (cand["votes"].dropna() >= 0).all(),
        f"min={cand['votes'].min()}",
    )
    check(
        "count_tier values ⊆ {A,B,C}",
        set(cand["count_tier"].dropna().unique()).issubset({"A", "B", "C"}),
        str(cand["count_tier"].value_counts().to_dict()),
    )
    check(
        "withdrawn column is boolean-like",
        cand["withdrawn"].dtype in (bool, "bool") or set(cand["withdrawn"].dropna().unique()).issubset({True, False, 0, 1}),
        str(cand["withdrawn"].dtype),
    )

# ---------------------------------------------------------------------------
# 5. pages.parquet schema
# ---------------------------------------------------------------------------

section("5. pages.parquet — schema & values")

if "pages" in frames:
    pages = frames["pages"]

    PAGE_COLS = ["file_id", "ballot_type", "page_no", "page_role", "ocr_latency_sec"]
    missing_pg = [c for c in PAGE_COLS if c not in pages.columns]
    check("required columns present", not missing_pg, f"missing: {missing_pg}" if missing_pg else "all present")

    check(
        "ocr_latency_sec non-negative where not null",
        (pages["ocr_latency_sec"].dropna() >= 0).all(),
        f"min={pages['ocr_latency_sec'].min():.3f} max={pages['ocr_latency_sec'].max():.3f}",
    )

# ---------------------------------------------------------------------------
# 6. official.parquet schema
# ---------------------------------------------------------------------------

section("6. official.parquet — schema & values")

if "official" in frames:
    off = frames["official"]

    OFF_COLS = [
        "ballot_type", "number", "name", "party",
        "official_votes", "vote_percent",
        "official_valid_votes", "official_void_ballots",
        "official_spoiled_ballots", "official_total_ballots",
    ]
    missing_off = [c for c in OFF_COLS if c not in off.columns]
    check("required columns present", not missing_off, f"missing: {missing_off}" if missing_off else "all present")

    check(
        "ballot_type values ⊆ {district,partylist}",
        set(off["ballot_type"].dropna().unique()).issubset({"district", "partylist"}),
        str(off["ballot_type"].value_counts().to_dict()),
    )
    check(
        "official_votes non-negative where not null",
        (off["official_votes"].dropna() >= 0).all(),
        f"min={off['official_votes'].min()}",
    )

# ---------------------------------------------------------------------------
# 7. Cross-frame consistency
# ---------------------------------------------------------------------------

section("7. Cross-frame consistency")

if "records" in frames and "candidates" in frames:
    rec_ids = set(frames["records"]["file_id"])
    cand_ids = set(frames["candidates"]["file_id"])
    orphan_cands = cand_ids - rec_ids
    check(
        "all candidate file_ids exist in records",
        not orphan_cands,
        f"{len(orphan_cands)} orphan file_ids" if orphan_cands else "ok",
    )

if "records" in frames and "pages" in frames:
    rec_ids = set(frames["records"]["file_id"])
    page_ids = set(frames["pages"]["file_id"])
    orphan_pages = page_ids - rec_ids
    check(
        "all page file_ids exist in records",
        not orphan_pages,
        f"{len(orphan_pages)} orphan file_ids" if orphan_pages else "ok",
    )

# ---------------------------------------------------------------------------
# 8. color() utility
# ---------------------------------------------------------------------------

section("8. color() utility")

palette = lib.PALETTE
check("palette loaded", bool(palette), f"{len(palette)} entries")

if palette:
    sample_party = next(iter(palette))
    result = lib.color(sample_party)
    check(
        "color() returns hex for known party",
        result.startswith("#") and len(result) in (7, 9),
        f"{sample_party!r} → {result}",
    )

unknown_color = lib.color("ไม่มีพรรคนี้")
check(
    "color() returns grey fallback for unknown",
    unknown_color == "#B0B0B0",
    unknown_color,
)
check(
    "color() handles None/empty",
    lib.color(None) == "#B0B0B0" and lib.color("") == "#B0B0B0",
)

# ---------------------------------------------------------------------------
# 9. clean_subset() utility
# ---------------------------------------------------------------------------

section("9. clean_subset() utility")

if "records" in frames:
    rec = frames["records"]
    try:
        sub, cap = lib.clean_subset(rec, count_tier="AB")
        check(
            "clean_subset count_tier=AB filters correctly",
            set(sub["count_tier"].unique()).issubset({"A", "B"}),
            f"n={len(sub)}/{len(rec)}",
        )
        check(
            "clean_subset returns caption string",
            isinstance(cap, str) and cap.startswith("n="),
            cap[:60],
        )
    except Exception as e:
        check("clean_subset(count_tier='AB')", False, str(e))

    try:
        sub2, cap2 = lib.clean_subset(rec, requires=["total_ballots", "valid_votes"])
        check(
            "clean_subset requires=[total_ballots,valid_votes] — no nulls remain",
            sub2["total_ballots"].notna().all() and sub2["valid_votes"].notna().all(),
            f"n={len(sub2)}/{len(rec)}",
        )
    except Exception as e:
        check("clean_subset(requires=[...])", False, str(e))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

section("Summary")
total = len(_results)
passed = sum(1 for _, ok, _ in _results if ok)
failed = total - passed
print(f"  {passed}/{total} passed", end="")
if failed:
    print(f"  ({failed} failed)")
    print("\n  Failed tests:")
    for name, ok, detail in _results:
        if not ok:
            print(f"    • {name}: {detail}")
else:
    print()
print()
