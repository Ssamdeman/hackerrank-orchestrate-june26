# 06-19-2026 04:35:22 Architect Handoff — Appendix A: Stage 1 Complete

*Append this after the original handoff. The original carries the mission, cast, values, and operating rules — all still current. This appendix only updates **state**: Stage 1 (Seeing) is now built, tested, and committed. Read the original first, then this.*

---

## What changed since the original handoff

The original's "immediate next move" — write the Stage 1 build directive — is **done**. Stage 1 (Seeing) is complete and checkpointed. The architecture in `solution_dna.md` held; nothing in the four values or the locked shape changed. What follows is the build record and the decisions made along the way.

## How the work actually ran (the rhythm that worked)

Stage 1 was not one directive. It was broken into phases, each a small standalone directive to Agent 3, each waiting on the prior:

1. **Ground** — Agent 3 read the contract + `solution_dna.md` and surfaced back the enum vocabularies and its proposed per-image record. No code. This caught five real design questions before any code existed.
2. **Build blind pass** — one image in, one schema-valid record out, claim out of view.
3. **Provider seam (2b)** — added an OpenRouter adapter so the vision provider is config, not code.
4. **Conditional detail pass** — the "look closer" second look.
5. **Lock** — verify clean → offline test → commit.

Keep this rhythm for Stage 2: ground first, then a few tasks at a time, never dump the whole stage at once. Agent 3 self-directs the *how*; the architect directs the *what* (in/out data) and the decisions that matter.

## Decisions locked during Stage 1 (architect calls — all reversible via config)

- **Confidence is an enum (`low/medium/high`), not a float.** Model self-reported floats aren't calibrated. The "look closer" trigger is a single boundary; an enum serves it honestly.
- **Authenticity = vision hint, resolver decides.** Vision emits `looks_manipulated` / `looks_non_original` hints; the resolver owns final `possible_manipulation` / `non_original_image` emission. Not part of `valid_image` — a doctored photo can still be "usable." No separate authenticity model step.
- **`text_content` captured, capped (~200 chars), inert.** The resolver never sees pixels, so Stage 2 needs the in-image text in hand to judge injection. Quoted as data, never executed — the instructions-as-data value in practice.
- **`severity_seen` lives in the blind pass.** Severity is a perception property; the resolver has no pixels.
- **`additional_parts_seen` kept as a list.** Resolver collapses to primary + names others in justification. Info loss here is irreversible downstream.
- **Detail-pass trigger = confidence-only (`!= high`).** No object-class rule yet. The detail pass exists to fix vision's *own* uncertainty, so vision's own confidence is the honest trigger. A class rule presumes which damage gets missed before the data says so — that's "measure, don't hand-read." Add the class rule only if the disagreement set shows blind misses on fine damage at high confidence.
- **Internal key = full relative path; emitted ID = bare `img_N`.** `img_N` is only unique within a case folder.

## Current repo state

- **`code/stage1/`** — `schema.py` (enums · `ImageRecord` · `coerce_record` validate/repair floor), `vision.py` (`see_image()` / `see_image_passes()` · blind + directed prompts · image+prompt+schema+model hash cache), `providers.py` (adapter seam: `AnthropicVisionAdapter` + `OpenRouterVisionAdapter` + `make_vision_adapter()` factory), `config.py`, `devlog.py`, `run_blind_pass.py`, `tests/test_stage1.py`.
- **Provider-agnostic.** `VISION_PROVIDER=openrouter|anthropic`, `VISION_MODEL` overrides. Free OpenRouter for dev iteration; frontier for the scored run. **That swap is the ≥2-config comparison the rubric rewards.**
- **Determinism** via per-image cache (image bytes + prompt + schema + model), git-ignored. Re-runs and resolver re-tuning re-bill nothing.
- **Tested offline** — 9/9 pass, mocked adapter, no API key needed: `coerce_record` fail-closed (incl. the dict-in-text-field bug that once escaped the floor), enum validation, confidence trigger.
- **Committed:** `d95b611` on `main` — "Stage 1 complete — blind + conditional detail vision pass, provider-agnostic, tested." Dev-log appended.
- **Not yet tracked:** `solution_dna.md`, `CLAUDE.md`, `mile_stone_one.md`. Worth committing so the repo is self-contained — doesn't block Stage 2.

## What Stage 1 proved

The detail pass earns its keep: on the free model it confirmed one ambiguous read (`case_012`, "dark mark" → confirmed scratch, medium→high), walked back one over-confident read (`case_017`, retracted a bad `water_damage` call to fail-closed), and left a genuinely-unassessable photo alone (`case_007`, blurry, stayed low). Blind-first and fail-closed-as-a-floor both behaved as designed. Note: free-model perception is for *pipeline* validation, not ground truth — severity/part accuracy gets settled in the calibration loop against the 20 labeled rows.

## Immediate next move

Write the **Stage 2 (Reading the claim) grounding directive** for Agent 3 — same ground-first rhythm. Stage 2: injection flagged on the raw transcript in parallel; the real claim extracted — in any language — into the **same controlled enums** Stage 1 emits; English structured output, **no separate translation hop** that could launder an injection before it's caught. Flag-and-extract, always both. Claim-reading must emit to the same enum vocabulary so Stage 3 reconciles by string match. Keep scope fenced — no resolver logic yet.

## Open threads (carry forward — resolved by data, not assumption)

- Grader strictness on the part/damage vocabulary — learn from the 20.
- Multi-part claims — primary part default, second named in justification.
- The exact contradicted / not-enough boundary — anchored to the sample, tuned on the disagreement set.
- Authenticity flags' final place in output — learn whether they earn a column from the 20.
- Object-class trigger for the detail pass — add only if the disagreement set demands it.

*If an Iteration 3 is needed, it is threshold tuning from the disagreement data — not a redesign.*