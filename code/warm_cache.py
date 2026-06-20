import csv
import json
import sys
import time
import os
import hashlib
import traceback
from pathlib import Path

# Add code folder to python path so imports resolve
repo_root = Path(r"c:\Users\Samue\Documents\projects\github\Orchestrate-Hackerrank-2024")
sys.path.append(str(repo_root / "code"))

from stage1.vision import SYSTEM_PROMPT as S1_SYS, USER_PROMPT as S1_USR, _cache_key as _s1_key, _directed_prompts, _media_type, _relative_ref
from stage1.schema import vision_output_schema, coerce_record
from stage1 import config
from stage1.providers import _make_backend, _VisionAdapter, _ClaimAdapter, ProviderError

from stage2.extract import _system_prompt as s2_sys, _user_prompt as s2_usr, _cache_key as _s2_key
from stage2.schema import claim_output_schema

# Output directories
S1_CACHE_DIR = repo_root / "code" / "stage1" / ".cache" / "stage1"
S2_CACHE_DIR = repo_root / "code" / "stage2" / ".cache" / "stage2"

OR_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
ANT_MODEL = "claude-opus-4-8"

# Global state to track last request time for OpenRouter to respect 20 req/min limit
last_or_request_time = 0.0
force_anthropic = False

# Counters
or_warmed_count = 0
ant_warmed_count = 0
failed_warmed_count = 0

def load_image_correctly(image_path):
    image_bytes = image_path.read_bytes()
    media_type = _media_type(image_path)
    if media_type == "image/avif" or b"ftypavif" in image_bytes[:30] or b"ftypav1" in image_bytes[:30]:
        from PIL import Image
        import io
        try:
            with Image.open(image_path) as img:
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    img = img.convert("RGB")
                out = io.BytesIO()
                img.save(out, format="JPEG", quality=90)
                image_bytes = out.getvalue()
                media_type = "image/jpeg"
        except Exception:
            pass
    return image_bytes, media_type

def throttle_openrouter():
    global last_or_request_time
    now = time.time()
    elapsed = now - last_or_request_time
    # 20 req/min means 3 seconds per request. Wait 3.5s to be safe.
    if elapsed < 3.5:
        sleep_time = 3.5 - elapsed
        time.sleep(sleep_time)
    last_or_request_time = time.time()

def call_vlm_with_fallback(image_path, system_prompt, user_prompt, pass_type, key_or, key_ant):
    global force_anthropic, or_warmed_count, ant_warmed_count, failed_warmed_count
    
    import base64
    image_bytes, media_type = load_image_correctly(image_path)
    image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    image_id = image_path.stem
    image_ref = _relative_ref(image_path, repo_root)
    out_schema = vision_output_schema()
    
    # Try OpenRouter if not forced to Anthropic
    if not force_anthropic:
        attempts = 5
        has_slept_2min = False
        for attempt in range(1, attempts + 1):
            try:
                throttle_openrouter()
                print(f"  [VLM] Querying OpenRouter (Attempt {attempt}/{attempts}) for {image_path.name} ({pass_type})...")
                
                backend = _make_backend("openrouter", OR_MODEL, 4096, None, 0)
                adapter = _VisionAdapter(backend)
                raw, usage = adapter.see(
                    image_b64=image_b64,
                    media_type=media_type,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    schema=out_schema,
                )
                
                # Write to both caches
                S1_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                # OpenRouter Cache
                (S1_CACHE_DIR / f"{key_or}.json").write_text(
                    json.dumps({"record": raw, "usage": usage, "image_ref": image_ref, "pass_type": pass_type}, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                # Anthropic Cache mirror
                (S1_CACHE_DIR / f"{key_ant}.json").write_text(
                    json.dumps({"record": raw, "usage": usage, "image_ref": image_ref, "pass_type": pass_type}, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                print(f"  -> SUCCESS via OpenRouter. Cached under both models.")
                or_warmed_count += 1
                return raw
            except Exception as e:
                err_msg = str(e)
                print(f"  -> OpenRouter error: {err_msg}")
                # Check for rate limit / daily cap
                if "429" in err_msg or "rate limit" in err_msg.lower() or "free-models-per-day" in err_msg:
                    print("  -> Daily cap or rate limit hit. Switching immediately to Anthropic for this and future requests.")
                    force_anthropic = True
                    break
                
                if attempt < attempts:
                    sleep_dur = 2 ** attempt
                    print(f"  -> Retrying in {sleep_dur}s...")
                    time.sleep(sleep_dur)
                else:
                    if not has_slept_2min:
                        print("  -> 5 attempts failed. Sleeping 2 minutes once before fallback/retry...")
                        time.sleep(120)
                        has_slept_2min = True
                        # Try one last time
                        try:
                            throttle_openrouter()
                            raw, usage = adapter.see(
                                image_b64=image_b64,
                                media_type=media_type,
                                system_prompt=system_prompt,
                                user_prompt=user_prompt,
                                schema=out_schema,
                            )
                            # Write to both
                            S1_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                            (S1_CACHE_DIR / f"{key_or}.json").write_text(
                                json.dumps({"record": raw, "usage": usage, "image_ref": image_ref, "pass_type": pass_type}, ensure_ascii=False, indent=2),
                                encoding="utf-8"
                            )
                            (S1_CACHE_DIR / f"{key_ant}.json").write_text(
                                json.dumps({"record": raw, "usage": usage, "image_ref": image_ref, "pass_type": pass_type}, ensure_ascii=False, indent=2),
                                encoding="utf-8"
                            )
                            print(f"  -> SUCCESS via OpenRouter after 2m wait.")
                            or_warmed_count += 1
                            return raw
                        except Exception as e2:
                            print(f"  -> OpenRouter last attempt failed: {e2}. Falling back to Anthropic.")
                            force_anthropic = True
                    else:
                        force_anthropic = True

    # Fallback to Anthropic
    print(f"  [VLM] Querying Anthropic for {image_path.name} ({pass_type})...")
    try:
        backend = _make_backend("anthropic", ANT_MODEL, 1024, None, 0)
        adapter = _VisionAdapter(backend)
        raw, usage = adapter.see(
            image_b64=image_b64,
            media_type=media_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=out_schema,
        )
        
        # Write to both caches
        S1_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (S1_CACHE_DIR / f"{key_or}.json").write_text(
            json.dumps({"record": raw, "usage": usage, "image_ref": image_ref, "pass_type": pass_type}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        (S1_CACHE_DIR / f"{key_ant}.json").write_text(
            json.dumps({"record": raw, "usage": usage, "image_ref": image_ref, "pass_type": pass_type}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"  -> SUCCESS via Anthropic. Cached under both models.")
        ant_warmed_count += 1
        return raw
    except Exception as e:
        print(f"  -> CRITICAL: Anthropic also failed: {e}")
        failed_warmed_count += 1
        raise e

def call_llm_with_fallback(user_claim, user_id, claim_object, key_or, key_ant):
    global force_anthropic, or_warmed_count, ant_warmed_count, failed_warmed_count
    
    out_schema = claim_output_schema(claim_object)
    sys_prompt = s2_sys(claim_object)
    usr_prompt = s2_usr(user_claim)
    
    # Try OpenRouter if not forced to Anthropic
    if not force_anthropic:
        attempts = 5
        has_slept_2min = False
        for attempt in range(1, attempts + 1):
            try:
                throttle_openrouter()
                print(f"  [LLM] Querying OpenRouter (Attempt {attempt}/{attempts}) for user {user_id} claim extraction...")
                
                backend = _make_backend("openrouter", OR_MODEL, 4096, None, 0)
                adapter = _ClaimAdapter(backend)
                raw, usage = adapter.read(
                    system_prompt=sys_prompt,
                    user_prompt=usr_prompt,
                    schema=out_schema,
                )
                
                # Write to both caches
                S2_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                (S2_CACHE_DIR / f"{key_or}.json").write_text(
                    json.dumps({"record": raw, "usage": usage}, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                (S2_CACHE_DIR / f"{key_ant}.json").write_text(
                    json.dumps({"record": raw, "usage": usage}, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                print(f"  -> SUCCESS via OpenRouter. Cached under both models.")
                or_warmed_count += 1
                return raw
            except Exception as e:
                err_msg = str(e)
                print(f"  -> OpenRouter error: {err_msg}")
                if "429" in err_msg or "rate limit" in err_msg.lower() or "free-models-per-day" in err_msg:
                    print("  -> Daily cap or rate limit hit. Switching immediately to Anthropic for this and future requests.")
                    force_anthropic = True
                    break
                
                if attempt < attempts:
                    sleep_dur = 2 ** attempt
                    print(f"  -> Retrying in {sleep_dur}s...")
                    time.sleep(sleep_dur)
                else:
                    if not has_slept_2min:
                        print("  -> 5 attempts failed. Sleeping 2 minutes once before fallback/retry...")
                        time.sleep(120)
                        has_slept_2min = True
                        try:
                            throttle_openrouter()
                            raw, usage = adapter.read(
                                system_prompt=sys_prompt,
                                user_prompt=usr_prompt,
                                schema=out_schema,
                            )
                            # Write to both
                            S2_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                            (S2_CACHE_DIR / f"{key_or}.json").write_text(
                                json.dumps({"record": raw, "usage": usage}, ensure_ascii=False, indent=2),
                                encoding="utf-8"
                            )
                            (S2_CACHE_DIR / f"{key_ant}.json").write_text(
                                json.dumps({"record": raw, "usage": usage}, ensure_ascii=False, indent=2),
                                encoding="utf-8"
                            )
                            print(f"  -> SUCCESS via OpenRouter after 2m wait.")
                            or_warmed_count += 1
                            return raw
                        except Exception as e2:
                            print(f"  -> OpenRouter last attempt failed: {e2}. Falling back to Anthropic.")
                            force_anthropic = True
                    else:
                        force_anthropic = True

    # Fallback to Anthropic
    print(f"  [LLM] Querying Anthropic for user {user_id} claim extraction...")
    try:
        backend = _make_backend("anthropic", ANT_MODEL, 1024, None, 0)
        adapter = _ClaimAdapter(backend)
        raw, usage = adapter.read(
            system_prompt=sys_prompt,
            user_prompt=usr_prompt,
            schema=out_schema,
        )
        
        # Write to both caches
        S2_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (S2_CACHE_DIR / f"{key_or}.json").write_text(
            json.dumps({"record": raw, "usage": usage}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        (S2_CACHE_DIR / f"{key_ant}.json").write_text(
            json.dumps({"record": raw, "usage": usage}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"  -> SUCCESS via Anthropic. Cached under both models.")
        ant_warmed_count += 1
        return raw
    except Exception as e:
        print(f"  -> CRITICAL: Anthropic also failed: {e}")
        failed_warmed_count += 1
        raise e

def check_and_warm():
    claims_path = repo_root / "dataset" / "claims.csv"
    with open(claims_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        claims = list(reader)

    print("======================================================================")
    print("STEP 1: Checking caches and identifying misses...")
    print("======================================================================")

    out_schema_s1 = vision_output_schema()
    schema_json_s1 = json.dumps(out_schema_s1, sort_keys=True)

    unique_images = set()
    for row in claims:
        unique_images.update(row["image_paths"].split(";"))

    missing_s1_blind = []
    missing_s1_directed = []
    missing_s2_claims = []

    # Check Stage 1
    for p in sorted(unique_images):
        full_path = repo_root / "dataset" / p
        if not full_path.exists():
            print(f"Image does not exist on disk: {p}")
            continue
        
        image_bytes, media_type = load_image_correctly(full_path)
        
        key_or_blind = _s1_key(image_bytes, OR_MODEL, S1_SYS, S1_USR, schema_json_s1)
        key_ant_blind = _s1_key(image_bytes, ANT_MODEL, S1_SYS, S1_USR, schema_json_s1)
        
        # Load blind record (check if cached in either OR or ANT)
        blind_rec = None
        for key in (key_or_blind, key_ant_blind):
            cache_file = S1_CACHE_DIR / f"{key}.json"
            if cache_file.exists():
                try:
                    cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
                    blind_rec = coerce_record(cached_data["record"], image_id=full_path.stem, image_ref=p)
                    break
                except Exception:
                    pass
        
        if blind_rec is None:
            # Blind pass is missing
            missing_s1_blind.append((p, full_path, key_or_blind, key_ant_blind))
        else:
            # Blind pass exists, check if directed pass is needed and missing
            if blind_rec.confidence != "high":
                sys_p, usr_p = _directed_prompts(blind_rec)
                key_or_dir = _s1_key(image_bytes, OR_MODEL, sys_p, usr_p, schema_json_s1)
                key_ant_dir = _s1_key(image_bytes, ANT_MODEL, sys_p, usr_p, schema_json_s1)
                
                # Check if directed pass is cached in either OR or ANT
                dir_exists = (S1_CACHE_DIR / f"{key_or_dir}.json").exists() or (S1_CACHE_DIR / f"{key_ant_dir}.json").exists()
                if not dir_exists:
                    missing_s1_directed.append((p, full_path, sys_p, usr_p, key_or_dir, key_ant_dir))

    # Check Stage 2
    for r in claims:
        user_id = r["user_id"]
        user_claim = r["user_claim"]
        claim_object = r["claim_object"]
        
        out_schema_s2 = claim_output_schema(claim_object)
        schema_json_s2 = json.dumps(out_schema_s2, sort_keys=True)
        sys_p = s2_sys(claim_object)
        usr_p = s2_usr(user_claim)
        
        key_or_s2 = _s2_key(user_claim, OR_MODEL, sys_p, usr_p, schema_json_s2)
        key_ant_s2 = _s2_key(user_claim, ANT_MODEL, sys_p, usr_p, schema_json_s2)
        
        s2_exists = (S2_CACHE_DIR / f"{key_or_s2}.json").exists() or (S2_CACHE_DIR / f"{key_ant_s2}.json").exists()
        if not s2_exists:
            missing_s2_claims.append((user_id, user_claim, claim_object, key_or_s2, key_ant_s2))

    print(f"Unique images: {len(unique_images)}")
    print(f"Missing Stage 1 Blind passes: {len(missing_s1_blind)}")
    print(f"Missing Stage 1 Directed passes: {len(missing_s1_directed)}")
    print(f"Missing Stage 2 Claims: {len(missing_s2_claims)}")
    print("======================================================================")

    # Process Stage 1 Blind misses
    if missing_s1_blind:
        print("\nSTEP 2A: Warming Stage 1 Blind passes...")
        for idx, (p, full_path, key_or, key_ant) in enumerate(missing_s1_blind):
            print(f"[{idx+1}/{len(missing_s1_blind)}] Image: {p}")
            try:
                raw_blind = call_vlm_with_fallback(full_path, S1_SYS, S1_USR, "blind_global", key_or, key_ant)
                
                # Check if we immediately need to run directed detail pass for this newly fetched image
                blind_rec = coerce_record(raw_blind, image_id=full_path.stem, image_ref=p)
                if blind_rec.confidence != "high":
                    sys_p, usr_p = _directed_prompts(blind_rec)
                    
                    # Reload correctly with AVIF-to-JPEG converted bytes for key generation
                    image_bytes, _ = load_image_correctly(full_path)
                    key_or_dir = _s1_key(image_bytes, OR_MODEL, sys_p, usr_p, schema_json_s1)
                    key_ant_dir = _s1_key(image_bytes, ANT_MODEL, sys_p, usr_p, schema_json_s1)
                    print(f"  -> Directed pass required (confidence {blind_rec.confidence}). Processing...")
                    call_vlm_with_fallback(full_path, sys_p, usr_p, "directed_detail", key_or_dir, key_ant_dir)
            except Exception:
                print(f"  -> FAILED to warm blind global for {p}")
                traceback.print_exc()

    # Process Stage 1 Directed misses (which already had cached blind passes but lacked directed pass)
    if missing_s1_directed:
        print("\nSTEP 2B: Warming Stage 1 Directed passes...")
        for idx, (p, full_path, sys_p, usr_p, key_or_dir, key_ant_dir) in enumerate(missing_s1_directed):
            print(f"[{idx+1}/{len(missing_s1_directed)}] Directed Image: {p}")
            try:
                call_vlm_with_fallback(full_path, sys_p, usr_p, "directed_detail", key_or_dir, key_ant_dir)
            except Exception:
                print(f"  -> FAILED to warm directed detail for {p}")
                traceback.print_exc()

    # Process Stage 2 Claim misses
    if missing_s2_claims:
        print("\nSTEP 2C: Warming Stage 2 Claims...")
        for idx, (user_id, user_claim, claim_object, key_or, key_ant) in enumerate(missing_s2_claims):
            print(f"[{idx+1}/{len(missing_s2_claims)}] Claim user: {user_id}")
            try:
                call_llm_with_fallback(user_claim, user_id, claim_object, key_or, key_ant)
            except Exception:
                print(f"  -> FAILED to warm claim for user {user_id}")
                traceback.print_exc()

    print("\n======================================================================")
    print("WARMING PROCESS COMPLETED.")
    print(f"  Warmed via OpenRouter: {or_warmed_count}")
    print(f"  Warmed via Anthropic:  {ant_warmed_count}")
    print(f"  Warmed failures:       {failed_warmed_count}")
    print("======================================================================")

if __name__ == "__main__":
    check_and_warm()
