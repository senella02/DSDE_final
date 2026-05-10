import json
import os
import math
import csv

JSON_DIR = "data/OCR_OUTPUT_JSON"
THRESHOLD = 10_000
OUT_CSV = "high_votes_hits.csv"

hits = []

for fname in os.listdir(JSON_DIR):
    if not fname.endswith(".json"):
        continue
    fpath = os.path.join(JSON_DIR, fname)
    with open(fpath, encoding="utf-8") as f:
        try:
            records = json.load(f)
        except Exception as e:
            pass

    for rec in records:
        if rec.get("ballot_type") != "partylist":
            continue
        for cand in rec.get("candidates", []):
            v = cand.get("votes")
            if v is None or (isinstance(v, float) and math.isnan(v)):
                continue
            if v >= THRESHOLD:
                hits.append({
                    "file": fname,
                    "pdf_name": rec.get("metadata", {}).get("pdf_name", ""),
                    "election_type": rec.get("election_type"),
                    "district": rec.get("district"),
                    "subdistrict": rec.get("subdistrict"),
                    "station_number": rec.get("station_number"),
                    "cand_number": cand.get("number"),
                    "party": cand.get("party"),
                    "votes": v,
                })

hits.sort(key=lambda x: x["votes"], reverse=True)

with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=list(hits[0].keys()) if hits else [])
    writer.writeheader()
    writer.writerows(hits)

print(f"Done. {len(hits)} hit(s) written to {OUT_CSV}")
