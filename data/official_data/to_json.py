import csv
import json

def csv_to_candidates_json(csv_path: str) -> list[dict]:
    candidates = []
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            candidates.append({
                "number": int(row["candidate_number"]),
                "party": row["party"],
                "withdrawn": row["withdrawn"].strip().upper() == "TRUE",
            })
    return candidates

candidates = csv_to_candidates_json("partylist_candidates.csv")
print(json.dumps(candidates, ensure_ascii=False, indent=2))