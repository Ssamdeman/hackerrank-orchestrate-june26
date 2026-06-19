# DNA — HackerRank Orchestrate (June 2026): Multi-Modal Evidence Review

> **Status: LIVE.** Problem confirmed from `problem_statement.md`, `AGENTS.md`, `README.md`, and the full
> dataset in the forked starter repo (`Ssamdeman/hackerrank-orchestrate-june26`). Challenge ends
> **2026-06-20 11:00 IST**. Results **2026-06-29**.
> This file is the authoritative build brief. Where it disagrees with `problem_statement.md` / `AGENTS.md`,
> **those files win** — they are the graded contract.

---

## 1. The problem in one sentence

Build a **terminal multi-modal AI agent** that, for each damage claim, decides whether the **submitted
images** *support*, *contradict*, or give *not_enough_information* for the user's claim — for **car,
laptop, or package** — with an explainable, image-grounded justification, written one row per claim into
`output.csv`.

## 2. Truth hierarchy (the safety spine — never violate)

1. **Images = primary source of truth.** The verdict must be grounded in what is actually visible.
2. **Conversation = the spec.** It defines *what* to check; extract the actual damage claim from it.
3. **User history = risk context only.** It can raise `risk_flags`, but **must not by itself override
   clear visual evidence**.
4. **Fail closed.** If images are missing / low-quality / mismatched / below the evidence bar →
   `claim_status = not_enough_information`, set `evidence_standard_met = false`, raise the matching flags.
   Never guess `supported`/`contradicted` to fill a row.

## 3. Inputs the agent reasons over

`dataset/claims.csv` (input-only, **44 rows**) and `dataset/sample_claims.csv` (labeled, **20 rows**) share
these input fields:

| Field | Meaning |
|---|---|
| `user_id` | Submitter; join key into `user_history.csv` |
| `image_paths` | One or more image paths, **semicolon-separated** (e.g. `images/test/case_001/img_1.jpg;...img_2.jpg`) |
| `user_claim` | The claim chat transcript (may be multilingual — sample has Hindi/Hinglish) |
| `claim_object` | `car` \| `laptop` \| `package` |

**Image ID** = filename without extension (`img_1.jpg` → `img_1`). Paths are relative to `dataset/`.

### Helper files
- **`dataset/user_history.csv`** (47 users): `user_id, past_claim_count, accept_claim, manual_review_claim,
  rejected_claim, last_90_days_claim_count, history_flags, history_summary`. `history_flags` values seen:
  `none`, `user_history_risk`, `manual_review_required` (and `;`-combined). These map directly into output
  `risk_flags`. Users in claims may be missing from history → treat as no-history (new user).
- **`dataset/evidence_requirements.csv`** (11 rules): `requirement_id, claim_object, applies_to,
  minimum_image_evidence`. The minimum-evidence checklist by object + issue family (`all` applies to every
  object). This defines the bar for `evidence_standard_met`.

## 4. Output — `output.csv` (EXACT schema, fixed column order)

One row per `dataset/claims.csv` row. **First 4 columns are the inputs echoed verbatim; the next 10 are predictions.**

| # | Column | Meaning / values |
|---|---|---|
| 1 | `user_id` | echoed input |
| 2 | `image_paths` | echoed input |
| 3 | `user_claim` | echoed input |
| 4 | `claim_object` | echoed input |
| 5 | `evidence_standard_met` | `true` if the image set is **sufficient to evaluate this claim**; else `false` |
| 6 | `evidence_standard_met_reason` | short reason for the evidence decision |
| 7 | `risk_flags` | `;`-separated flags, or `none` |
| 8 | `issue_type` | visible issue type (controlled vocab) |
| 9 | `object_part` | relevant part (controlled vocab, per object) |
| 10 | `claim_status` | `supported` \| `contradicted` \| `not_enough_information` |
| 11 | `claim_status_justification` | concise, image-grounded; mention relevant image IDs when helpful |
| 12 | `supporting_image_ids` | `;`-separated image IDs backing the decision; `none` if no image is sufficient |
| 13 | `valid_image` | `true` if the image set is **usable for automated review**; else `false` |
| 14 | `severity` | `none` \| `low` \| `medium` \| `high` \| `unknown` |

> **Two distinct booleans:** `valid_image` = images are *usable at all* (not blurry/manipulated/wrong object).
> `evidence_standard_met` = usable **and** they actually meet the minimum-evidence bar for *this* claim.

### Controlled vocabularies (use the closest matching value)
- **`claim_status`**: `supported`, `contradicted`, `not_enough_information`
- **`issue_type`**: `dent`, `scratch`, `crack`, `glass_shatter`, `broken_part`, `missing_part`,
  `torn_packaging`, `crushed_packaging`, `water_damage`, `stain`, `none`, `unknown`
  - `none` = relevant part visible and no issue present; `unknown` = issue can't be determined.
- **`object_part`** (per `claim_object`):
  - **car**: `front_bumper`, `rear_bumper`, `door`, `hood`, `windshield`, `side_mirror`, `headlight`,
    `taillight`, `fender`, `quarter_panel`, `body`, `unknown`
  - **laptop**: `screen`, `keyboard`, `trackpad`, `hinge`, `lid`, `corner`, `port`, `base`, `body`, `unknown`
  - **package**: `box`, `package_corner`, `package_side`, `seal`, `label`, `contents`, `item`, `unknown`
- **`risk_flags`**: `none`, `blurry_image`, `cropped_or_obstructed`, `low_light_or_glare`, `wrong_angle`,
  `wrong_object`, `wrong_object_part`, `damage_not_visible`, `claim_mismatch`, `possible_manipulation`,
  `non_original_image`, `text_instruction_present`, `user_history_risk`, `manual_review_required`
  - **Quality:** blurry / cropped / low-light / wrong-angle. **Mismatch:** wrong_object / wrong_object_part /
    claim_mismatch / damage_not_visible. **Authenticity:** possible_manipulation / non_original_image /
    `text_instruction_present` (= prompt-injection text inside an image — **never obey it**). **History:**
    user_history_risk / manual_review_required (sourced from `user_history.csv`).
- **`severity`**: `none`, `low`, `medium`, `high`, `unknown`

## 5. Decision architecture (the pipeline spine)

```
parse user_claim ─► extract claim (object, alleged part, alleged issue, multi-part?)
        │
per-image VLM pass (each image separately):
        │   object present? which part visible? what issue visible? quality / authenticity / injected-text?
        ▼
match images ↔ claim  +  evidence_requirements bar  ──►  valid_image? evidence_standard_met?
        │
adjudicate ─► supported | contradicted | not_enough_information
        │     (images primary; history is risk-only and cannot flip a clear visual verdict)
        ▼
risk_flags (quality+mismatch+authenticity+history)  +  severity  +  supporting_image_ids  +  grounded justification
        ▼
write row → output.csv
```

## 6. Non-negotiable constraints (scoring-critical)

- **Image-grounded, zero hallucination** — justifications cite only what is visible.
- **Fail closed** — see §2.4.
- **No hardcoded test labels / file-specific answers** — must generalize; no lookup tables keyed on case/user/image IDs.
- **Secrets from env vars only** (`ANTHROPIC_API_KEY`, etc.); never hardcode; `.env` ok but never committed.
- **Deterministic where possible** — temperature 0, fixed seed, fixed prompt templates, structured (tool/JSON)
  output, stable row ordering ⇒ same input ⇒ same `output.csv`.
- **Entry points are a contract** (`AGENTS.md` §6): keep `code/main.py` (solution) and `code/evaluation/main.py`
  (evaluation). Don't rename without updating `AGENTS.md`.
- **Mandatory append-only dev log** (see §9). Sub-agents/worktrees share the same file with `parent_agent=`.

## 7. Data inventory (in the fork)

- `dataset/sample_claims.csv` — 20 labeled rows (inputs + all 10 expected outputs) → dev/eval set.
- `dataset/claims.csv` — 44 input-only rows → produce predictions for these.
- `dataset/output.csv` — header only; **write predictions here**. (Submission = the populated `output.csv`.)
- `dataset/user_history.csv` — 47 users. `dataset/evidence_requirements.csv` — 11 rules.
- `dataset/images/{sample,test}/case_XXX/img_N.jpg` — **111 images** total. (`.DS_Store` junk present — ignore.)

## 8. Evaluation workflow (REQUIRED — must ship in `code.zip`)

Per `problem_statement.md` + `README.md`, the `evaluation/` folder must include `evaluation_report.md` with:
- **Metrics on `sample_claims.csv`**: `claim_status` accuracy (+ confusion matrix), `issue_type` /
  `object_part` accuracy, `evidence_standard_met` & `valid_image` accuracy, `severity` error,
  `supporting_image_ids` precision/recall, `risk_flags` F1 — **sliced by `claim_object`**.
- **≥2 strategies/prompts/model configs compared** (e.g. Opus 4.8 vs Sonnet 4.6 vision; single-pass vs
  per-image-then-adjudicate) and the final strategy chosen for `output.csv`.
- **Operational analysis**: approx model calls (sample + test), input/output token usage, images processed,
  approx full-test cost with stated pricing assumptions, approx latency/runtime, and TPM/RPM considerations
  (batching, throttling, caching, retry strategy).

## 9. Mandatory dev log + onboarding gate (`AGENTS.md` §2–§5 — graded as the chat transcript)

- **Path:** `%USERPROFILE%\hackerrank_orchestrate\log.txt` (Win) / `$HOME/hackerrank_orchestrate/log.txt`.
  Outside the repo; **never commit it**. Create parent dir if missing. UTF-8, `\n` endings, append-only,
  never rewrite past entries, **redact secrets**.
- **Onboarding gate (first run):** if the log has no `AGREEMENT RECORDED: <repo root>` line, run the §3 flow
  (greet, recite the 6 rules, collect exact `I agree`, append the `ONBOARDING COMPLETE` block). Then skip on
  later sessions.
- **Per-turn entry** after every user message: ISO-8601 timestamp + ≤80-char title; verbatim user prompt
  (secrets redacted); 2–5 sentence response summary; actions list; context block
  (`tool / branch / repo_root / worktree / parent_agent`). Sub-agents/worktrees append to the **same** file.

## 10. Submission deliverables (upload on HackerRank)

1. **`code.zip`** — runnable `code/` (solution + prompts/configs + README + `evaluation/`). **Exclude** venvs,
   `node_modules`, build artifacts, generated junk, and (per the email) the `data/`/`dataset/` corpus + images.
2. **`output.csv`** — predictions for **all** rows of `dataset/claims.csv`, exact columns in exact order, one
   row per input row.
3. **`chat_transcript`** — the `log.txt` from §9 (your AI-coding conversation, not the agent's runtime logs).

Then: **AI Judge interview** — 30 min voice, opens immediately after submit, **camera on**, open 12 h. Defend
architecture, decisions, model usage, evaluation, safety/tradeoffs. **Results 2026-06-29.**

## 11. How it's evaluated (four signals)

1. **Code quality** 2. **Output accuracy** 3. **AI chat transcript** 4. **Judge interview**.
System design + safe orchestration > prompt engineering alone.

## 12. Proposed build shape (modular & swappable — per CLAUDE.md design philosophy)

```
code/
├── main.py                  # entry point: read dataset/claims.csv → write output.csv (CONTRACT)
├── evaluation/
│   └── main.py              # entry point: eval on sample_claims.csv → evaluation_report.md (CONTRACT)
├── pipeline/
│   ├── extract_claim.py     # user_claim → structured claim (object, part, issue, multi-part)
│   ├── analyze_image.py     # per-image VLM pass → structured findings + quality/authenticity signals
│   ├── adjudicate.py        # claim + image findings + evidence_reqs + history → 10 output fields
│   └── schema.py            # output schema + controlled vocabularies (single source of truth)
├── vlm/client.py            # VLM provider behind one interface (Claude vision; model-swappable, temp 0)
├── prompts/                 # versioned prompt templates (out of code)
├── logging/                 # AGENTS.md-compliant append-only log writer
└── README.md                # install deps + run command
```

- **VLM:** default to the most capable Claude vision model (Opus 4.8; Sonnet 4.6 as the cost/speed comparison arm).
- **Structured output:** force JSON via tool use / response schema → deterministic parse, validate against §4 vocab.
- **Caching:** cache per-image analysis by image hash so re-runs don't re-bill identical images.

---

## 13. Open items to confirm during build

1. **Output location**: fork ships `dataset/output.csv` but README also says “write to `output.csv`”.
   Plan: write `dataset/output.csv`; mirror to repo-root `output.csv` if the grader expects it.
2. How strictly `issue_type` / `object_part` / `severity` are graded (exact match vs family) — inspect
   `sample_claims.csv` label distribution to calibrate.
3. Multi-part claims (e.g. “front bumper **and** left headlight”) — confirm whether output expects a single
   primary part or the most-relevant; sample rows are single-part so default to the primary claimed part.
4. Users present in `claims.csv` but absent from `user_history.csv` → treat as new/no-history (no history flag).

### Sources
- `problem_statement.md`, `AGENTS.md`, `README.md`, and `dataset/` in fork `Ssamdeman/hackerrank-orchestrate-june26`.
- Challenge page: https://www.hackerrank.com/hackerrank-orchestrate-june26
