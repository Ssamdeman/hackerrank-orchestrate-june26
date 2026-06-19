# Multi-Modal Evidence Review — Iteration 2

## Where this came from

Iteration 1 was the philosophy. It went through three rounds of adversarial review, and the result is worth stating plainly: **the values held, the mechanism got sharper — and leaner.** Every change below removed a point of failure or a contradiction; none added invention. The system is _smaller_ than where Iteration 1 was trending, and that is the point. This is the settled shape. It is still a hypothesis we calibrate against the 20 labeled rows before trusting it on the 44 — but the architecture is locked.

## What hardened, and why

**Seeing became two-stage — but conditional.** Iteration 1's pure-blind pass could gloss a hairline crack; that critique was right. But steering the camera by the _claim_ breaks the cases where the claim is a fabrication — a "hood scratch" claim over a photo of a smashed front end, a "box" claim over a photo of a different object. Those verdicts depend on noticing what the claim never pointed at. So: a blind global pass runs on every image and catches wrong-object, wrong-part, and severity-mismatch. A directed detail pass runs _only when the blind pass reports its own low confidence, or when the object class itself warrants acuity_ — never triggered by the claim. Blind-first survives intact, localized damage stops slipping through, and most images still take a single look.

**Both seeing and claim-reading now speak one vocabulary.** Two free-text descriptions in different words ("scuffed chassis" vs "scratched door") would force the resolver to guess they meant the same physical thing. They don't get to. Both steps emit from the same controlled enum list the problem already hands us. Reconciliation becomes a string match, not a semantic guess.

**The adjudicator is no longer a model.** This is the largest change. Once both upstream steps emit clean enums, confidence, and the two booleans, the verdict is pure `if/else` — and an LLM "executing" deterministic logic only adds stochastic risk to a decision that has a correct, reliable answer. So the verdict and every structured field are produced by a deterministic resolver. **No model touches the verdict.** The strongest sentence we have for the judge: _the decision is a script you can read top to bottom, not a model you have to trust._

**Security is its own signal, not a gate.** Injection detection runs on the raw transcript text, in parallel, before anything is normalized. It does not block the row — every adversarial claim here still carries a real claim underneath ("...the claim is broken headlight," "...I still want the seal damage approved"). We extract the genuine claim _and_ raise the flag. Flag-and-extract, always both.

**Fail-closed is a floor, not a reflex.** "Not enough information" is the right answer for the genuinely unassessable and the adversarial — but it is the minority label in the sample, and a system that demands undeniable proof everywhere will tank the score. The default is the confident call the evidence reasonably supports. Fail-closed is the safety floor under that, not the resting state.

**Calibration is empirical.** We do not hand-read the 20 and encode one person's interpretation. We run the baseline against them, measure where the system disagrees with the known labels, then tune the resolver's thresholds against that disagreement set. The same loop produces the required strategy comparison.

## The settled shape — two model steps, one script

The flow, and the one ordering that matters:

**See → (look closer if needed) → read the claim → resolve.**

The "look closer" trigger reads _vision's own output and the object label_ — never the transcript. There is no point at which claim data is in scope to leak into seeing.

- **Stage 1 — Seeing.** Blind global pass on every image: what object, what part is visible, what damage, is the photo usable at all, is there any text written in it — emitted as enums plus a one-line observation and a confidence, with the claim nowhere in view. A directed detail pass fires only on the blind pass's low-confidence/ambiguity signal or by object class.
- **Stage 2 — Reading the claim.** Injection flagged on the raw text in parallel; the real claim extracted — in any language — into the same enums. English structured output, with no separate translation hop that could launder an injection before we catch it.
- **Stage 3 — Resolving.** Deterministic. Receives only the committed enums, observations, confidences, and booleans — **never the pixels.** Reconciles vision's part against the claim's part by match, applies the evidence-requirements bar, folds history as risk context only, and emits the verdict and all structured fields by fixed branch logic. The one natural-language field is templated, with an optional capped single line for phrasing.

## The values, unchanged

- **Blind-first** — the model looks before it's told the story, so it can't bend perception to fit the claim.
- **History as risk only** — history raises flags; it never flips a verdict the photo settles.
- **Fail-closed as a floor** — the honest answer when we can't confirm we're even seeing the right thing.
- **Instructions as data** — planted commands get flagged and ignored, never obeyed.

## The two booleans — now enforced by structure

The split that matters most, and it is now architectural: **vision owns "usable"** (blur, light, framing — `valid_image`); **the resolver owns "relevant"** (does this usable image actually meet the evidence bar for _this_ claim — `evidence_standard_met`). A blurry photo of an obviously crushed laptop is usable; a crisp macro of a clean bumper is useless for a windshield claim. Different steps, different questions, no conflation.

## Cost and safety, honestly

The conditional second pass keeps token cost and latency bounded — most rows are a single vision call, not two. Per-image findings cache by image hash, so re-tuning the resolver re-bills nothing. Two model steps total, temperature 0, deterministic verdict — the same input produces the same `output.csv`. The operational report writes itself from this: bounded calls, cached images, a verdict path with zero model variance.

## What's still open — resolved by data, not assumption

- **Grader strictness on the part and damage vocabulary** — loose or exact, we learn it from the 20.
- **Multi-part claims** — default to the primary claimed part, name the second in the justification; revisited if the disagreement set says otherwise.
- **The exact contradicted / not-enough boundary** — anchored to the sample, tuned on the disagreement set, never guessed.


## Iteration 2.1 — Provider abstraction (headless, multi-key)

**Adapting:** the pipeline goes headless. No single vendor is assumed. Providers become *config*, not code — supply an API key for any supported model and the pipeline routes to it. This is an upgrade to the same architecture, not a redesign; it passes the simplicity test because it has a real job (no lock-in, interchangeable keys) rather than adding cleverness.

**What changes**
- **Per-role provider routing.** The two model steps are configured independently: vision (Stage 1) gets its own provider / model / key; claim-read (Stage 2) gets its own. Plug a frontier vision model into Stage 1 and a cheap fast model into Stage 2 — or point both at one provider with one key. The single-key path is the out-of-the-box default; multi-key is the upgrade.
- **One thin adapter per provider.** Each adapter owns its vendor's auth, endpoint, message format, and image encoding. Adding a provider = writing one adapter; the pipeline does not change.

**What does NOT change**
- **The verdict path stays vendor-free.** Stage 3, the resolver, is deterministic: no model, no key, no provider. The "decision is a script, not a model" guarantee is untouched.
- **The four values are untouched** — blind-first, history-as-risk-only, fail-closed-as-floor, instructions-as-data.

**The boundary that makes this safe**
The abstraction is **not** "swap the URL." It is **"return validated enums."** Our whole design rests on both model steps emitting the *same controlled enums* so the resolver reconciles by string match. Structured output differs across vendors (Anthropic, OpenAI, Gemini each do it differently; open models via Ollama/OpenRouter vary and some are unreliable). So each adapter's contract is: hand the pipeline clean, schema-valid enums — however its vendor produces them (native schema, tool-use, or JSON-mode plus a validation/repair fallback). The pipeline trusts the enums, not the vendor.

**Operational notes**
- **Fail loud on capability.** Assign a text-only model to the vision role → error at config time, never a silent guess.
- **Determinism varies by vendor.** Use temp 0 where allowed; some providers expose no seed. Caching by image+prompt hash gives reproducibility regardless; the operational report states which providers cannot fully guarantee determinism.
- **Secrets.** More keys now — all still env-var only, `.env` git-ignored, dev-log redaction matters more.

**Bonus the rubric rewards:** swapping the vision provider across the 20 labeled rows *is* the "≥2 model configs compared" the evaluation requires — the abstraction gives us the comparison arm for free.


Iteration 2 is the architecture I'd defend. If there is an Iteration 3, it is threshold tuning from the disagreement data — not a redesign.
