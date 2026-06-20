# HackerRank Orchestrate — Multi-Modal Evidence Review Solver

This repository contains the complete, production-grade damage-claim verification system built for the HackerRank Orchestrate challenge. 

---

## Overview

The system is a multi-modal damage-claim resolver designed to verify damage claims (cars, laptops, and packages) using submitted images and a support chat transcript. The resolver evaluates claims and classifies them into one of three statuses:
* `supported` — The visual evidence corroborates the claimed part and damage type.
* `contradicted` — The evidence conflicts with the claim (e.g. clean parts, mismatched damage families, incorrect object classes, or non-original screenshot/stock evidence).
* `not_enough_information` — The images are too blurry/unusable, or do not inspect the claimed parts.

---

## Architecture

The solver is split into three decoupled pipeline stages to ensure strict separation of concerns, observability, and safety:

```
                  +----------------------------------+
                  |  claims.csv / chat transcripts   |
                  +-----------------+----------------+
                                    |
                                    v
     +------------------------------+------------------------------+
     | STAGE 1: SEE (Visuals)       | STAGE 2: READ (Claims)       |
     | * Blind Global VLM Pass      | * LLM Claim Extraction       |
     | * Directed Detail VLM Pass   | * Deterministic Injection    |
     |   (if blind confidence < HI) |   Regex & Model Scan         |
     +------------------------------+------------------------------+
                                    |
                                    v
                  +-----------------+----------------+
                  | STAGE 3: RESOLVE (Verdict)       |
                  | * Deterministic Python Rule Spine |
                  | * Reconciles Parts & Damage      |
                  | * Strict Fail-Closed Safety      |
                  +-----------------+----------------+
                                    |
                                    v
                         +----------+----------+
                         |     output.csv      |
                         +---------------------+
```

1. **Stage 1: See (VLM Perception)** — Performs a blind global visual assessment of each image. If the VLM is unsure of itself (confidence is not high), a second directed detail look is conditionally triggered. The VLM never receives the claim or transcript, preventing confirmation bias.
2. **Stage 2: Read (Claim Analysis)** — Extracts the claimed object, part, damage type, and severity from the support conversation. It also runs a dual-layer injection scan (regex-based and model-based) to identify prompt injections.
3. **Stage 3: Resolve (Verdict Engine)** — A **100% deterministic Python resolver** that processes the Stage 1 and Stage 2 records. **No LLMs/VLMs are in the verdict path.** It applies five sequential gates: Quality/Usability, Authenticity, Object-Class Verification, Enum Reconciliation (damage compatibility maps), and the Evidence Bar.

### The Safety Spine
* **Images are Primary:** Status determinations are strictly grounded in what is visible in the images.
* **History is Risk-Only:** User claims history only adds risk flags (e.g. `user_history_risk`); it *never* overrides visual evidence to flip a status.
* **Fail-Closed on Anomalies:** Mismatched objects, low-quality photos, or screenshot/stock watermarks immediately trigger fail-closed verdicts (`contradicted` or `not_enough_information`).
* **Instructions-as-Data:** Verbatim text found inside images is treated strictly as inert data to prevent instruction-injection attacks.

---

## Setup

### Requirements
* **Python version:** Python 3.8+
* **Dependencies:** Install the required packages via pip:
  ```bash
  pip install -r code/requirements.txt
  ```

### Environment Config
Create a `.env` file inside the `code/` folder (or copy `code/.env.example`):
```ini
# code/.env
ANTHROPIC_API_KEY=your_anthropic_api_key
VISION_PROVIDER=openrouter  # optional: openrouter or anthropic
OPENROUTER_API_KEY=your_openrouter_api_key  # required if using openrouter
```

### Pre-Warmed Caching
The repository ships with a **pre-warmed cache** (`code/stage1/.cache/` and `code/stage2/.cache/`). A cold run by the grader will default to **100% offline cache-replay**, resulting in zero cost, zero network overhead, and near-instant execution. Live API calls are only made on a cache miss.

---

## Run Commands

### 1. Run the Main Pipeline
To run the resolver on the 44 test claims and generate the output files:
```bash
python code/main.py
```
* **Output generated:** `output.csv` (repo root) and `dataset/output.csv` (mirror).

### 2. Run the Evaluation Pipeline
To evaluate the resolver against the 20 gold-labeled development cases:
```bash
python code/evaluation/main.py
```
* **Output generated:** Scores summary on the CLI and a detailed markdown evaluation report written to `code/evaluation/evaluation_report.md`.

---

## Caching Strategy

All model queries are cached locally under `code/stage1/.cache/stage1/` and `code/stage2/.cache/stage2/`. Cache files are named using SHA-256 hashes generated from the exact parameters:
* **Stage 1 keys:** Hashed from `image_bytes + model + system_prompt + user_prompt + schema_json`.
* **Stage 2 keys:** Hashed from `user_claim + model + system_prompt + user_prompt + schema_json`.
* **Fallback Strategy:** If a live API call is required and OpenRouter returns a 429 rate limit or daily limit error, the query throttles with exponential backoff (up to 5 retries, then waits 2 minutes) before automatically falling back to the Anthropic provider. Warmed items are written to both cache directories so that subsequent runs replay cleanly.


## Reproducing the Results

**Default (recommended): replay from the shipped cache.**
The cache IS a committed artifact. A normal run replays it — deterministic, offline, ~1.4s:
```bash
python code/main.py            # regenerates output.csv from cache
python code/evaluation/main.py # regenerates the scorecard from cache
```
You do not need API keys for this. Same input → same output, every time.

**Optional: regenerate the cache from scratch (requires API keys).**
To re-derive every perception/extraction record live (e.g. to verify nothing is hardcoded):
1. Put valid keys in `code/.env` (`ANTHROPIC_API_KEY`, optionally `OPENROUTER_API_KEY`).
2. Delete the cache dirs: `code/stage1/.cache/` and `code/stage2/.cache/`.
3. Warm the cache (handles throttling + provider fallback automatically):
```bash
   python code/warm_cache.py
```
4. Re-run `python code/main.py`.
This makes ~110 vision + ~64 extraction calls (~$1–6 depending on model) and takes a few minutes. The deterministic Stage 3 resolver is unchanged either way — only the upstream perception cache is rebuilt.

---

## Evaluation Results

The pipeline has been thoroughly calibrated and scored:
* **Gold Accuracy:** **75.00%** overall accuracy on `sample_claims.csv` claim status, achieving **100.00%** accuracy on laptops.
* **API Cost Projection:** A full run on the 44-row test set is projected to cost only **$1.14** using Claude 3.5 Sonnet pricing.
* **Warmed Runtime:** Replaying from the pre-warmed cache executes in **~1.2 seconds** for all 44 rows.
* For a detailed operational breakdown and model config comparisons, see [code/evaluation/evaluation_report.md](file:///c:/Users/Samue/Documents/projects/github/Orchestrate-Hackerrank-2024/code/evaluation/evaluation_report.md).

---

## Directory Layout

```text
.
├── README.md                         # Grader documentation (you are here)
├── problem_statement.md              # HackerRank challenge details
├── AGENTS.md                         # Onboarding and session logging rules
├── output.csv                        # Final generated submission output (44 rows)
├── code/
│   ├── main.py                       # Main pipeline runner
│   ├── requirements.txt              # Dependencies (includes Pillow/AVIF decoder)
│   ├── vocab.py                      # Shared enums and vocabularies
│   ├── warm_cache.py                 # Utility to cache-warm misses with fallbacks
│   ├── stage1/                       # Image perception (VLM)
│   │   ├── vision.py                 # VLM wrapper and cache check
│   │   ├── providers.py              # Vendor backends (Anthropic/OpenRouter)
│   │   ├── schema.py                 # Image record schema and validators
│   │   └── .cache/                   # Warmed VLM image records cache
│   ├── stage2/                       # Chat reading (LLM)
│   │   ├── extract.py                # LLM claim extraction and cache check
│   │   ├── injection.py              # Injection regex scan
│   │   └── .cache/                   # Warmed LLM claim records cache
│   ├── stage3/                       # Deterministic resolver
│   │   ├── resolve.py                # Python resolver spine and gates 1-5
│   │   ├── evidence.py               # Minimum evidence standard requirements loader
│   │   ├── history.py                # User history risk lookup
│   │   └── schema.py                 # Output schema and coercion floor
│   └── evaluation/
│       ├── main.py                   # Development evaluation script
│       └── evaluation_report.md      # Scorecard and cost/operational report
└── dataset/
    ├── claims.csv                    # Test set claims
    ├── sample_claims.csv             # Dev set gold labels (20 rows)
    ├── evidence_requirements.csv     # Minimum evidence rules
    ├── user_history.csv              # Claims history records
    └── images/                       # Raw JPEG/PNG/AVIF images
```
