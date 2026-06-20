import sys
import os
import csv
from pathlib import Path

# Add code folder to python path so imports resolve
repo_root = Path(__file__).resolve().parent.parent
sys.path.append(str(repo_root / "code"))

from stage1.vision import see_image
from stage2.extract import extract_claim
from stage3.evidence import EvidenceRequirements
from stage3.history import UserHistoryLookup
from stage3.resolve import resolve_spine, resolve_verdict
from stage3.schema import OUTPUT_COLUMNS, Verdict

def see_image_safe(full_path, repo_root):
    try:
        return see_image(full_path, repo_root=repo_root)
    except Exception as e:
        from stage1.schema import ImageRecord
        try:
            rel_path = full_path.relative_to(repo_root).as_posix()
        except Exception:
            rel_path = str(full_path)
        return ImageRecord(
            image_id=full_path.stem,
            image_ref=rel_path,
            object_seen="unknown",
            object_part_seen="unknown",
            additional_parts_seen=[],
            issue_type_seen="unknown",
            severity_seen="unknown",
            valid_image=False,
            quality_flags=["blurry_image"],
            looks_manipulated=False,
            looks_non_original=False,
            text_seen=False,
            text_content="",
            observation=f"Inspection failed: {type(e).__name__}",
            confidence="low",
            pass_type="error_fallback"
        )

def extract_claim_safe(user_claim, user_id, claim_object):
    try:
        return extract_claim(user_claim, user_id=user_id, claim_object=claim_object)
    except Exception as e:
        from stage2.schema import ClaimRecord
        return ClaimRecord(
            user_id=user_id,
            claim_object=claim_object,
            claimed_part="unknown",
            additional_claimed_parts=[],
            claimed_issue_type="unknown",
            claimed_severity="unknown",
            claim_summary=f"Extraction failed: {type(e).__name__}",
            confidence="low",
            injection_detected=False,
            injection_excerpt=""
        )

def main():
    import time
    start_time = time.time()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    claims_path = repo_root / "dataset" / "claims.csv"
    evidence_path = repo_root / "dataset" / "evidence_requirements.csv"
    history_path = repo_root / "dataset" / "user_history.csv"
    output_dataset_path = repo_root / "dataset" / "output.csv"
    output_root_path = repo_root / "output.csv"

    # Load resources
    evidence_keyer = EvidenceRequirements(str(evidence_path))
    history_lookup = UserHistoryLookup(str(history_path))

    # Read claims
    with open(claims_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        claims = list(reader)

    provider = os.getenv("VISION_PROVIDER", "anthropic").upper()
    print("======================================================================")
    print("HACKERRANK ORCHESTRATE: DAMAGE-CLAIM RESOLVER PIPELINE")
    print(f"  Rows to process:  {len(claims)}")
    print(f"  VLM Provider:     {provider}")
    print("  Cache Mode:       CACHE-FIRST (Offline Replay Mode)")
    print("======================================================================")

    verdicts = []
    for i, row in enumerate(claims):
        user_id = row["user_id"]
        claim_obj = row["claim_object"]
        image_paths_str = row["image_paths"]
        img_paths = image_paths_str.split(";")

        # Get case ID for logging (e.g. images/test/case_010/img_1.jpg -> case_010)
        case_id = "unknown"
        if img_paths:
            parts = img_paths[0].split('/')
            if len(parts) >= 3:
                case_id = parts[-2]

        print(f"[{i+1:2d}/{len(claims)}] {case_id} ({claim_obj}) ... resolving", end="", flush=True)

        # Stage 1: Fan-out vision across all images
        img_recs = []
        for p in img_paths:
            full_path = repo_root / "dataset" / p
            img_recs.append(see_image_safe(full_path, repo_root=repo_root))

        # Stage 2: Extract claim
        cr = extract_claim_safe(row["user_claim"], user_id=user_id, claim_object=claim_obj)

        # Stage 3: Lookup history and resolve
        uh = history_lookup.get(user_id)
        state = resolve_spine(img_recs, cr, evidence_keyer, uh)
        verdict = resolve_verdict(state, cr, img_recs, uh)
        
        # Override first 4 fields to match original input verbatim
        verdict.image_paths = image_paths_str
        verdict.user_claim = row["user_claim"]
        verdicts.append(verdict)
        
        print(" [done]", flush=True)

    # Write output to both files
    for dest in [output_dataset_path, output_root_path]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(OUTPUT_COLUMNS))
            writer.writeheader()
            for v in verdicts:
                writer.writerow(v.to_csv_row())
        print(f"Successfully wrote {len(verdicts)} rows to {dest}.")

    elapsed = time.time() - start_time
    print("======================================================================")
    print("PIPELINE EXECUTION COMPLETE")
    print(f"  Processed rows: {len(verdicts)}")
    print(f"  Total runtime:  {elapsed:.2f} seconds")
    print(f"  Output files:   {output_dataset_path}")
    print(f"                  {output_root_path}")
    print("======================================================================")
        
    # Spot-print 3 rows
    print("\nSpot-printing 3 rows:")
    import random
    random.seed(42) # deterministic spot-print selection
    spot_indices = sorted(random.sample(range(len(verdicts)), min(3, len(verdicts))))
    for idx in spot_indices:
        print(f"\n--- Row {idx} ---")
        row_dict = verdicts[idx].to_csv_row()
        for k, v in row_dict.items():
            print(f"{k}: {v}")

if __name__ == "__main__":
    main()
