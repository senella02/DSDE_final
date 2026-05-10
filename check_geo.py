import pandas as pd

out_lines = []

records = pd.read_parquet("data/records.parquet")
manifest = pd.read_csv("data/manifest/pdf_manifest.csv", dtype=str)[
    ["file_id", "file_path", "district", "subdistrict"]
].drop_duplicates("file_id").rename(
    columns={"district": "m_district", "subdistrict": "m_subdistrict"}
)

# --- Simulate _remap_geo_from_manifest ---
remapped = records.copy().reset_index(drop=True)
merged = remapped.merge(manifest, on="file_id", how="left")

for ocr_col, man_col in [("district", "m_district"), ("subdistrict", "m_subdistrict")]:
    has_manifest = merged[man_col].notna()
    remapped.loc[has_manifest, ocr_col] = merged.loc[has_manifest, man_col].values

# --- Compare remapped values against manifest expected values ---
normal = remapped[remapped["election_type"] == "normal"].copy()
normal_m = normal.merge(manifest, on="file_id", how="left")

normal_m["district_match"] = normal_m["district"].fillna("") == normal_m["m_district"].fillna("")
normal_m["subdistrict_match"] = normal_m["subdistrict"].fillna("") == normal_m["m_subdistrict"].fillna("")
normal_m["has_manifest"] = normal_m["m_district"].notna() | normal_m["m_subdistrict"].notna()

out_lines.append("=== POST-REMAP CHECK ===")
out_lines.append(f"Normal records total: {len(normal_m)}")
out_lines.append(f"Records covered by manifest: {normal_m['has_manifest'].sum()}")
out_lines.append(f"Records NOT in manifest:      {(~normal_m['has_manifest']).sum()}")
out_lines.append(f"")
out_lines.append(f"After remap:")
out_lines.append(f"  district match (remapped == manifest):    {normal_m['district_match'].sum()} / {len(normal_m)}")
out_lines.append(f"  subdistrict match (remapped == manifest): {normal_m['subdistrict_match'].sum()} / {len(normal_m)}")

# Records not covered by manifest (kept raw OCR values)
not_covered = normal_m[~normal_m["has_manifest"]]
out_lines.append(f"\n--- Records not in manifest (kept OCR district/subdistrict): {len(not_covered)} ---")
if len(not_covered):
    out_lines.append(not_covered[["file_id", "file_path", "district", "subdistrict"]].to_string())

# Records where district still mismatches after remap (shouldn't happen for covered records)
bad_district = normal_m[normal_m["has_manifest"] & ~normal_m["district_match"]]
out_lines.append(f"\n--- Covered records where district still mismatches: {len(bad_district)} ---")
if len(bad_district):
    out_lines.append(bad_district[["file_id","district","m_district","subdistrict","m_subdistrict"]].head(20).to_string())

bad_sub = normal_m[normal_m["m_subdistrict"].notna() & ~normal_m["subdistrict_match"]]
out_lines.append(f"\n--- Covered records where subdistrict still mismatches: {len(bad_sub)} ---")
if len(bad_sub):
    out_lines.append(bad_sub[["file_id","district","m_district","subdistrict","m_subdistrict"]].head(20).to_string())

# Naming format check
out_lines.append(f"\n--- Distinct district values after remap (normal records) ---")
out_lines.append(str(sorted(normal["district"].dropna().unique())))

out_lines.append(f"\n--- Records with m_subdistrict=NaN (เทศบาล, expected): check their post-remap subdistrict ---")
tesaban = normal_m[normal_m["has_manifest"] & normal_m["m_subdistrict"].isna()]
out_lines.append(f"Count: {len(tesaban)}")
if len(tesaban):
    # Show their file_path and what subdistrict ended up with
    sample = tesaban[["file_path", "subdistrict"]].drop_duplicates("file_path").head(20)
    out_lines.append(sample.to_string())

with open("check_geo_out.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines))

print("Done — see check_geo_out.txt")
