import sys
import json
from pathlib import Path

# Setup paths
code_dir = Path('c:/Users/Samue/Documents/projects/github/Orchestrate-Hackerrank-2024/code')
sys.path.insert(0, str(code_dir))

from stage1.vision import see_image
from stage2.extract import extract_claim
from stage3.evidence import load_evidence_requirements
from stage3.history import load_user_history
from stage3.resolve import resolve_spine, resolve_verdict
import csv

repo_root = Path('c:/Users/Samue/Documents/projects/github/Orchestrate-Hackerrank-2024')
claims_csv = repo_root / 'dataset' / 'sample_claims.csv'

try:
    evidence_keyer = load_evidence_requirements(repo_root / 'dataset' / 'evidence_requirements.csv')
except Exception:
    evidence_keyer = load_evidence_requirements(repo_root / 'dataset')

try:
    history_map = load_user_history(repo_root / 'dataset' / 'user_history.csv')
except Exception:
    history_map = load_user_history(repo_root / 'dataset')

with open(claims_csv, newline='', encoding='utf-8') as f:
    reader = list(csv.DictReader(f))

# Define cases to test
targets = {
    'user_030': '1. Check case_016 text_content & injection',
    'user_001': '2a. Supported Verdict (case_001)',
    'user_008': '2b. Contradicted Verdict (case_008)',
    'user_032': '2c. NEI Verdict (case_018)',
}

for row in reader:
    uid = row['user_id']
    if uid in targets:
        print(f"\n{'='*60}")
        print(f"--- {targets[uid]} ({uid}) ---")
        
        # 1. Stage 1 (Vision)
        image_records = []
        paths = row['image_paths'].split(';')
        for p in paths:
            img_path = repo_root / 'dataset' / p
            img_rec = see_image(img_path, repo_root=repo_root, use_cache=True)
            image_records.append(img_rec)
            
            # Print case_016 specific check
            if uid == 'user_030' and p == paths[0]:
                text = img_rec.text_content
                print('text_content preview:')
                print(text[:200] + '...' if len(text)>200 else text)
                print()
                
        # 2. Stage 2 (Claim Extraction)
        claim_rec = extract_claim(
            row['user_claim'],
            user_id=row['user_id'],
            claim_object=row['claim_object'],
            use_cache=True
        )
        
        # 3. Stage 3 (Resolve)
        history = history_map.get(uid)
        state = resolve_spine(image_records, claim_rec, evidence_keyer, history)
        verdict = resolve_verdict(state, claim_rec, image_records, history)
        verdict.image_paths = row['image_paths']
        
        # Print results
        if uid == 'user_030':
            # specifically check injection
            print(f"Risk Flags: {verdict.risk_flags}")
            print(f"text_instruction_present fired: {'text_instruction_present' in verdict.risk_flags}")
        else:
            # print verdict summary
            print(json.dumps(verdict.to_csv_row(), indent=2))
