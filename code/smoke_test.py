"""Stage 1 + Stage 2 live smoke test — real OpenRouter calls.

Integration/wiring proof, NOT accuracy: confirm real claims.csv rows produce
schema-valid records through both stages with literal enum tokens. Stage 1 and
Stage 2 are printed SEPARATELY per row — no reconciliation, no verdict (Stage 3).

Run from code/:  python smoke_test.py
Uses the existing caches, so a re-run re-bills nothing. A failed call prints
inline for that row and the run continues.
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

# Both stages on the free OpenRouter model for this run.
os.environ.setdefault("VISION_PROVIDER", "openrouter")
os.environ.setdefault("CLAIM_PROVIDER", "openrouter")

try:
    sys.stdout.reconfigure(encoding="utf-8")  # box-drawing chars on Windows
except Exception:
    pass

from stage1.vision import see_image
from stage2.extract import extract_claim

REPO = Path(__file__).resolve().parents[1]

# Selected by characteristic (unambiguous by case folder, since user_ids repeat).
SELECT = [
    ("case_046", "Hinglish car (side mirror)"),
    ("case_001", "multi-part car (front bumper + headlight)"),
    ("case_018", "plain laptop (coffee spill)"),
    ("case_034", "package (shipping label — watch text_seen)"),
]

BAR = "═" * 50
SUB = "─" * 50


def load_rows():
    return list(csv.DictReader(open(REPO / "dataset" / "claims.csv", encoding="utf-8")))


def pick(rows, case):
    for r in rows:
        if f"/{case}/" in r["image_paths"]:
            return r
    return None


def block(row, why):
    user_id, obj = row["user_id"], row["claim_object"]
    first_img = row["image_paths"].split(";")[0]
    img_path = REPO / "dataset" / first_img

    print(BAR)
    print(f"ROW: {user_id}   OBJECT: {obj}   [{why}]")
    print(SUB)
    print(f"RAW CLAIM:   {row['user_claim']}")
    print(f"IMAGE:       {first_img}")
    print(SUB)

    print("STAGE 1 (what the image shows — claim NOT in view):")
    try:
        rec = see_image(img_path)
        print(f"  object_seen:      {rec.object_seen}")
        print(f"  part_seen:        {rec.object_part_seen}")
        print(f"  issue_seen:       {rec.issue_type_seen}")
        print(f"  severity_seen:    {rec.severity_seen}")
        print(f"  confidence:       {rec.confidence}")
        print(f"  valid_image:      {rec.valid_image}")
        print(f"  text_seen:        {rec.text_seen}")
        print(f"  observation:      {rec.observation}")
    except Exception as e:
        print(f"  [STAGE 1 ERROR] {type(e).__name__}: {e}")

    print(SUB)
    print("STAGE 2 (what the claim says):")
    try:
        cr = extract_claim(row["user_claim"], user_id=user_id, claim_object=obj)
        print(f"  claimed_part:        {cr.claimed_part}")
        print(f"  additional_parts:    {cr.additional_claimed_parts}")
        print(f"  claimed_issue_type:  {cr.claimed_issue_type}")
        print(f"  claimed_severity:    {cr.claimed_severity}")
        print(f"  confidence:          {cr.confidence}")
        print(f"  claim_summary:       {cr.claim_summary}")
        print(f"  injection_detected:  {cr.injection_detected}")
        print(f"  injection_excerpt:   {cr.injection_excerpt!r}")
    except Exception as e:
        print(f"  [STAGE 2 ERROR] {type(e).__name__}: {e}")
    print(BAR)
    print()


def path_table(rows):
    print("PATH TABLE (click the full path to open the image Stage 1 ran on):")
    print(SUB)
    for case, _why in SELECT:
        r = pick(rows, case)
        if r is None:
            print(f"  [{case}] not found")
            continue
        first_img = r["image_paths"].split(";")[0]
        full = (REPO / "dataset" / first_img).resolve()
        print(f"  {r['user_id']}  |  {case}")
        print(f"     full image path : {full}")
        print(f"     image_paths(csv): {r['image_paths']}")
    print(SUB + "\n")


def main():
    rows = load_rows()
    print(f"provider: vision={os.environ['VISION_PROVIDER']} claim={os.environ['CLAIM_PROVIDER']}")
    print(f"selected rows: {[c for c, _ in SELECT]}\n")
    path_table(rows)
    for case, why in SELECT:
        row = pick(rows, case)
        if row is None:
            print(BAR)
            print(f"[ROW NOT FOUND for {case}]")
            print(BAR + "\n")
            continue
        block(row, why)


if __name__ == "__main__":
    main()
