# Multi-Modal Evidence Review — `code/`

Damage-claim verifier. Architecture (see `../solution_dna.md`, Iteration 2):

**See → (look closer if needed) → read the claim → resolve.** Two model steps,
one deterministic script. No model ever touches the verdict.

This directory currently implements **Stage 1 — Seeing** (the blind global pass).
Stages 2 (claim reading) and 3 (deterministic resolver) are not built yet.

## Stage 1 — the blind global pass

One image in → one schema-valid record out, with the user's claim **never** in
view, so perception can't bend to fit a story.

```
stage1/
  schema.py          locked enums + the per-image record + validate/repair
  vision.py          see_image(): the blind pass, blind prompt, hash cache
  providers.py       adapter seam — "return validated enums"; Anthropic adapter
  config.py          provider/model config, env-only secrets
  devlog.py          mandatory append-only dev log helper
  run_blind_pass.py  exercise the pass on sample images
```

### Setup

```bash
pip install -r requirements.txt
cp .env.example .env          # then put your real ANTHROPIC_API_KEY in code/.env
```

`code/.env` is git-ignored. Secrets are read from the environment only.

### Run

From the `code/` directory:

```bash
python -m stage1.run_blind_pass
# or specific images:
python -m stage1.run_blind_pass dataset/images/sample/case_001/img_1.jpg
```

### Notes

- **Model:** default `claude-opus-4-8` (frontier vision = the perception
  foundation). Swap via `VISION_MODEL` for a cheaper cost arm — this swap is
  also the ≥2-model comparison the evaluation rewards.
- **Determinism:** Opus 4.8 rejects `temperature`, so reproducibility comes from
  a per-image cache keyed by image bytes + prompt + schema + model
  (`stage1/.cache/`, git-ignored). Re-runs and resolver re-tuning re-bill
  nothing.
- **Structured output:** the Anthropic adapter uses native `output_config.format`
  (JSON schema); `coerce_record` then validates/repairs as defense in depth, so
  a malformed record never escapes Stage 1.
- **Fail closed:** refusals, truncation, and unparseable output raise rather than
  emit a guess.
