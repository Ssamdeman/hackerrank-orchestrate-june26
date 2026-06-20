# 06-19-2026 12:58:41 Architect Handoff — Appendix B: Stage 2 Complete + Live Smoke Test

*Append this after Appendix A. The original handoff carries the mission, cast, values, and operating rules — all still current. Appendix A recorded Stage 1 (Seeing) complete. This appendix updates **state** only: Stage 2 (Reading the claim) is now built, tested, and committed, and both model stages have been verified end-to-end on live data for the first time. Read the original, then Appendix A, then this.*

---

## What changed since Appendix A

Appendix A's "immediate next move" — the Stage 2 grounding directive — is **done**, and Stage 2 is built through to a live smoke test. The architecture in `solution_dna.md` held; nothing in the four values or the locked shape changed. Two design corrections came out of the critique loop (both conceded, both improved the design) and are recorded below. The headline: **both model steps are now real, tested, committed, and smoke-verified on actual dataset rows** — the system's perception and extraction halves are proven on live inputs. Only the deterministic resolver (Stage 3) remains.

## How the work actually ran (same rhythm, still working)

Stage 2 followed the Stage 1 pattern exactly — ground first, then a few tasks at a time, never the whole stage at once:

1. **Ground** — Agent 3 read the contract + the committed `schema.py` + the real CSVs and surfaced the claim-vs-image enum split, a proposed `ClaimRecord`, the injection mechanism, and the input source. No code. This settled four design questions and a vocab-ownership question before any code existed.
2. **Phase 1 — schema + floor** — vocab hoist, `ClaimRecord`, `coerce_claim`. No model call.
3. **Critique loop** — the skeptics caught two real things (adapter seam, regex scope). Both conceded; see "Lessons paid for in Stage 2."
4. **Phase 2 ground** — surfaced the real `providers.py` shape, the exact enum tokens, and a threat characterization of the labeled rows.
5. **Phase 2 — build** — provider refactor (gated on Stage 1 staying green), deterministic injection floor, `extract_claim`, flag wiring.
6. **Live smoke test** — first real model calls; human visually verified the output against the images and claims.

Keep this rhythm for Stage 3: ground first. Stage 3 has **more** genuine open questions than Stages 1–2 did — do not skip the grounding step.

## Decisions locked during Stage 2 (architect calls — all reversible via config/schema)

- **Vocab hoisted to `code/vocab.py`.** The four shared enums (`OBJECT_PARTS`, `ISSUE_TYPES`, `SEVERITIES`, `CONFIDENCES`) were lifted out of `stage1/schema.py` into a neutral module both stages import. Neither stage owns the contract. An **is-identity test** asserts Stage 2's enums are the same objects as `vocab.py`'s, so the two stages cannot silently drift apart.
- **`ClaimRecord` is a deliberate subset, not a mirror of `ImageRecord`.** A claim owns neither image-usability (`valid_image`, quality flags — vision's) nor verdict fields (resolver's). It carries part/issue/severity (best-effort), `claim_summary`, extraction `confidence`, and the injection fields. `claim_object` is carried (given input) so the record is self-contained and `coerce` can run the object↔part check.
- **`coerce_claim` has two deliberate asymmetries vs Stage 1.** (1) `none` is **illegal** for `claimed_issue_type` — a claim never asserts no-damage; vagueness → `unknown`. (2) `injection_detected` **fails open to `True`** while everything else fails closed to `unknown`/`low` — a malformed flag must never silence a possible injection.
- **Injection = one model call + a deterministic floor, OR'd in code.** `injection_detected = floor_fired OR model_flag`, computed outside the model's own field. The model can **raise** the flag, never **lower** it. The deterministic floor is the un-suppressible signal.
- **The deterministic floor is categorical, LLM-control register ONLY.** It fires on attack-on-the-model syntax (`ignore previous instructions`, `system prompt`, `override context`, role injection, jailbreak/DAN), as templates, not sample strings. **Business-logic imperatives ("approve regardless", "refund now", "you must") are deliberately OUT** — they are indistinguishable from a furious legitimate claimant and belong to the model's semantic read. High-precision floor, high-recall model. This split is what makes one-call extraction safe.
- **Classify, don't translate.** Foreign-language transcript → enum token directly; `claim_summary` written in English inline; no intermediate translation artifact for an injection to hide behind. The detector reads the raw `user_claim` bytes.
- **Multi-part claims mirror Stage 1** — `claimed_part` (primary) + `additional_claimed_parts` (list). Info loss here is irreversible downstream; the resolver collapses to primary + names others in the justification.
- **Provider seam split by concern (critique outcome).** Vendor backends (`_AnthropicBackend`, `_OpenRouterBackend`) own all generic transport; modality adapters (`_VisionAdapter`, `_ClaimAdapter`) only compose content blocks. A text call simply omits the image block — **no null-image branch, no strip logic** (there is no multimodal-validation failure mode for text-only `/v1/messages`). `make_vision_adapter()`'s external surface is unchanged, so Stage 1 is untouched. New `make_claim_adapter()`; new `CLAIM_PROVIDER`/`CLAIM_MODEL` knobs default to the vision provider. The single env→factory swap point survives intact — now serving both roles. **This per-role routing strengthens the ≥2-config comparison** (cheap claim-read + frontier vision is a defensible cost story for judges).
- **Claim token floor 2048 → 4096** (matches vision), after a free reasoning model rambled past the budget and failed to close its JSON. Not part of the cache key, so the bump re-bills nothing.

## Lessons paid for in Stage 2 (don't re-learn them)

- **Concede the diagnosis, correct the stated risk.** Both critique hits were right in diagnosis; both came with an inaccurate *risk*. The adapter split was right, but the warned-of "strict multimodal endpoint rejects null image" failure doesn't exist for these providers — so the fix is naming honesty + one swap point, **not** defensive null-handling. Accepting a wrong reason builds a wrong guard.
- **Don't certify a precision rate against a tiny sample.** Validating the regex false-positive rate against ~15–18 clean rows is statistical theater. The floor's safety is **categorical, proven by construction** (hand-built tests: fires on all LLM-control strings, silent on all business-logic/angry-customer strings), not estimated from sample frequency.
- **The regex floor is precision, the model is recall.** Multilingual injection (the transcript is Hinglish-confirmed) is the model's job; English-only regex would miss it. Don't push recall onto the deterministic floor.
- **Injection tests are hand-constructed, not sample-drawn** — the labeled sample contains **zero transcript injections** (see below), so there is nothing to source them from.

## What the threat characterization found (a real result, carry it forward)

Of the 20 labeled rows, only **user_034** is `text_instruction_present` — and its planted instruction is **not in the transcript**. The transcript is a clean package claim. By elimination the label is **image-borne**: the instruction is text in the submitted image, which is Stage 1's `text_seen`/`text_content`, **not** Stage 2's transcript reader. Consequence: the Stage 2 transcript floor has zero positive examples in the labeled data (it is insurance for the unseen 44, justified categorically), and **the entire sample's injection-detection correctness rides on Stage 1's `text_seen` → resolver `text_instruction_present` path.** That path is now load-bearing for Stage 3.

## Current repo state

- **`code/vocab.py`** — the shared contract (`OBJECT_PARTS`, `ISSUE_TYPES`, `SEVERITIES`, `CONFIDENCES`). Both stages import from here.
- **`code/stage1/`** — unchanged in behavior; `schema.py` now imports the shared enums from `vocab.py`; `providers.py` refactored to vendor-backend + modality-adapter shape (public `.see(...)` surface preserved); `VisionError` is now an alias of shared `ProviderError`.
- **`code/stage2/`** — `schema.py` (`ClaimRecord` + `coerce_claim`), the injection floor (`scan_injection`), `extract_claim()` (one text-only call via `make_claim_adapter()`), per-call cache (`stage2/.cache/`, git-ignored, keyed on claim + prompt + schema + model; the deterministic floor recomputes even on a cache hit).
- **`code/smoke_test.py`** — runs both stages live on selected rows, prints a path table + side-by-side per-row blocks for human verification. Does **not** reconcile or emit a verdict.
- **Tests:** 36/36 combined, offline, mocked adapter, no API key — Stage 1 (9, regression), Stage 2 schema (13), injection floor (3: 11 attacks fire / 8 business-logic stay silent / edge), extract (11: OR wiring, malformed-can't-lower, multilingual, coerce). The precision guarantee is tested both directions, including a Hinglish angry-customer string that must **not** fire the floor.
- **Provider-agnostic, per-role.** `VISION_PROVIDER`/`VISION_MODEL` and `CLAIM_PROVIDER`/`CLAIM_MODEL`. Free OpenRouter for dev; frontier for the scored run. **That swap is the ≥2-config comparison the rubric rewards** — now spanning both model roles.
- **Committed:** Stage 2 work checkpointed on `main`; dev log appended at each phase. (`solution_dna.md`, `CLAUDE.md` still worth committing so the repo is self-contained — doesn't block Stage 3.)

## What the live smoke test proved

First real model calls — 4 cases (Hinglish car, multi-part car, laptop spill, package), both stages, free model. Human visually verified output against the actual images and claims:

- **Pipeline is real and schema-valid** — 4/4 clean after the token-floor bump; literal `vocab.py` tokens throughout; the one transient failure (free model rambling past the budget) fixed by the floor bump, not a wiring bug.
- **Classify-don't-translate fired end-to-end on live foreign-language input** — Hinglish "side mirror toot gaya" → `side_mirror` / `broken_part` with an English summary, no translation hop.
- **Multi-part list populated** on the live multi-part row.
- **The security path is alive.** On the package box, the blind pass emitted `text_seen=True` and captured the box text **inertly as data** — corroborated by a license plate, keycap legends, and barcode digits across the other objects. Had the box read "approve regardless," it would land in `text_content` the same way: captured, never executed, and (blind-first) never matchable to a claim. **Caveat:** the smoke set's `text_seen=True` is a *benign* imperative-shaped caption — the path is proven to **capture and quote**, not yet proven against an **actual planted command** (the dataset has none in the smoke set). This shapes a Stage 3 grounding question (below).
- **Claim-vs-image divergence is expected signal, not error.** Human confirmed cases where the claim asserts damage the image doesn't clearly show (laptop liquid damage is internal/invisible; a multi-part car's relevant scratch lives in img_2, not img_1). These are exactly the `contradicted` / `not_enough_information` cases the resolver exists to decide — concrete calibration anchors, not pipeline failures.

## Immediate next move

Write the **Stage 3 (Resolving) grounding directive** for Agent 3 — same ground-first rhythm, no resolver logic yet. Stage 3 is **deterministic, no pixels, no model in the verdict path, readable top to bottom**: it takes Stage 1's image records + Stage 2's claim record, reconciles enums by string match, applies the evidence bar, folds history as risk-only, emits every output field by fixed branch logic, and writes one row per claim to `output.csv` with a templated justification. The grounding step must surface, before any code: the **exact `output.csv` schema + controlled output vocabulary** from `problem_statement.md`; the **`user_history.csv` shape** (`history_flags`, `history_summary`, claim counts, keyed on `user_id`); and a proposal for each open thread below — surfaced, not decided.

## Open threads for Stage 3 (resolve by data, not assumption)

- **Multi-image coverage + `supporting_image_ids` (TOP).** Stage 1 currently runs on `img_1` only, but cases ship 2–3 images and the relevant evidence (and readable text) may live in `img_2`/`img_3` — human confirmed a case where `img_1` was irrelevant and the supporting scratch was in `img_2`. Stage 3 must run vision across the full `image_paths` set and select `supporting_image_ids` from it.
- **Image-borne injection, end-to-end.** The resolver maps `text_seen` → `text_instruction_present` (likely also `manual_review_required`) and **never executes** `text_content`. **Open question raised by the smoke test:** does *any* image text raise the flag, or only instruction-shaped text? The benign Amazon caption fired `text_seen=True` — mapping that straight to `text_instruction_present` would be a false positive. Decide the rule (any-text vs instruction-shaped) from the labeled data, not by assumption.
- **The contradicted / not_enough boundary** — anchored to the 20, tuned on the disagreement set. Live anchors already in hand (invisible internal damage; image-doesn't-show-claimed-part).
- **Multi-part primary reconciliation** — when claim-primary ≠ image-primary (e.g. the multi-part car). Default to the claimed primary, name the second in the justification; revisit if the disagreement set says otherwise.
- **History as risk only** — wiring `history_flags`/`history_summary` so they raise flags but never flip a verdict the photo settles.
- **Authenticity flags' final column** — `looks_manipulated`/`looks_non_original` → `possible_manipulation`/`non_original_image`: learn whether they earn an output column from the 20.
- **Grader strictness on the part/damage vocabulary** — loose or exact; learn from the 20.

## The values (unchanged, all four verified on live data this round)

- **Blind-first** — vision never saw the claim; box text could not be matched to a claim. Verified.
- **History as risk only** — not yet wired (correctly — it is Stage 3).
- **Fail-closed as a floor** — `coerce_claim` repairs to safe defaults; the one model failure produced no guessed record. Verified.
- **Instructions as data** — `text_seen=True` + inert `text_content` capture on the live box. Verified.

*If an Iteration 3 is needed, it is threshold tuning from the disagreement data — not a redesign. Where `solution_dna.md` disagrees with the contract files, the contract files win.*