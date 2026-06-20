"""Stage 3 — Resolving.

The deterministic resolver: no pixels, no model in the verdict path. Consumes
Stage 1 per-image records + Stage 2 claim record + evidence requirements + user
history, and writes one verdict row per claim. Readable top to bottom.
"""
