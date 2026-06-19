"""Provider configuration — from environment only. No secrets in code.

Loads code/.env (git-ignored) if present, then reads everything from the
environment. Providers are config, not code (solution_dna.md §2.1).
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    # code/.env sits one level up from this file's package.
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:
    # dotenv is optional at runtime; the env vars may already be set.
    pass

# Per-provider defaults. Frontier vision (Anthropic) is the foundation for the
# scored run; free OpenRouter is the dev arm. Swap the whole vendor with
# VISION_PROVIDER, or just the model with VISION_MODEL.
DEFAULT_VISION_MODEL = "claude-opus-4-8"
DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"


def vision_provider() -> str:
    """Which vision vendor Stage 1 routes to: 'anthropic' | 'openrouter'."""
    return os.environ.get("VISION_PROVIDER", "anthropic").strip().lower()


def vision_model() -> str:
    """Model slug for the active provider. VISION_MODEL overrides the default."""
    explicit = os.environ.get("VISION_MODEL")
    if explicit:
        return explicit
    if vision_provider() == "openrouter":
        return DEFAULT_OPENROUTER_MODEL
    return DEFAULT_VISION_MODEL


def vision_max_tokens() -> int:
    return int(os.environ.get("VISION_MAX_TOKENS", "1024"))


def vision_temperature() -> float | None:
    """Temperature for the vision call, or None to omit it.

    Opus 4.8 / 4.7 reject temperature (400). Default is None — determinism comes
    from the image+prompt-hash cache, not from a seed the vendor won't expose.
    Set VISION_TEMPERATURE only for older models that accept it.
    """
    raw = os.environ.get("VISION_TEMPERATURE", "").strip()
    return float(raw) if raw else None


def vision_seed() -> int:
    """Determinism seed for providers that accept one (e.g. OpenRouter)."""
    return int(os.environ.get("VISION_SEED", "0"))


def anthropic_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Put it in code/.env (git-ignored) or "
            "export it in your shell. Secrets are read from the environment only."
        )
    return key


def openrouter_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Put it in code/.env (git-ignored) or "
            "export it in your shell. Secrets are read from the environment only."
        )
    return key
