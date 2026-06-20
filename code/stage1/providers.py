"""The provider seam — vendor backends + per-role modality adapters.

The pipeline trusts the enums, not the vendor (solution_dna.md §2.1). A vendor
*backend* owns all generic transport (auth, endpoint, structured output, error
handling, usage) and exposes `complete(system_prompt, content_blocks, schema)`
plus block builders. A *modality adapter* decides which blocks to send and
delegates:

    vision (Stage 1): [image_block, text_block]   → .see(...)
    claim  (Stage 2): [text_block]                 → .read(...)

Adding a vendor = one backend; adding a modality = one adapter. The single
provider-swap point (env → factory → backend) serves both roles.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol

from . import config


class ProviderError(RuntimeError):
    """A model call could not produce a usable record. Fail closed."""


# Back-compat alias — Stage 1 imports VisionError.
VisionError = ProviderError


# --- JSON extraction (for vendors without native schema enforcement) -------

def _extract_json_object(content: Any) -> dict[str, Any] | None:
    """Pull a single JSON object out of a model's text reply.

    OpenRouter has no native schema format, so a model may wrap its JSON in
    prose or code fences. Try a clean parse, then strip fences, then grab the
    outermost {...}. Returns a dict or None.
    """
    if isinstance(content, list):  # some models return content as parts
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    if not isinstance(content, str):
        return None
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()
    for candidate in (text, _outermost_braces(text)):
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _outermost_braces(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    return text[start:end + 1] if 0 <= start < end else ""


# --- Vendor backends (generic transport; modality-agnostic) ----------------

class _AnthropicBackend:
    """Anthropic Messages API with native structured output (output_config.format).

    Determinism: temperature omitted by default (Opus 4.8 rejects it);
    reproducibility is the caching layer's job.
    """

    def __init__(self, model: str, max_tokens: int, temperature: float | None):
        import anthropic  # lazy so the package imports without the SDK
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=config.anthropic_api_key())
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    @staticmethod
    def text_block(text: str) -> dict[str, Any]:
        return {"type": "text", "text": text}

    @staticmethod
    def image_block(image_b64: str, media_type: str) -> dict[str, Any]:
        return {"type": "image", "source": {
            "type": "base64", "media_type": media_type, "data": image_b64,
        }}

    def complete(self, *, system_prompt: str, content_blocks: list[dict[str, Any]],
                 schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{
                "type": "text", "text": system_prompt,
                "cache_control": {"type": "ephemeral"},  # stable enum prompt → cache it
            }],
            messages=[{"role": "user", "content": content_blocks}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        try:
            resp = self._client.messages.create(**kwargs)
        except self._anthropic.APIError as e:
            raise ProviderError(f"Anthropic API error: {e}") from e

        if resp.stop_reason == "refusal":
            raise ProviderError("model refused the request")
        if resp.stop_reason == "max_tokens":
            raise ProviderError("record truncated (raise max_tokens)")
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if text is None:
            raise ProviderError("no text block in response")
        try:
            record = json.loads(text)
        except json.JSONDecodeError as e:
            raise ProviderError(f"output was not valid JSON: {e}") from e

        usage = {
            "model": resp.model,
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "cache_read_input_tokens": getattr(resp.usage, "cache_read_input_tokens", 0),
            "cache_creation_input_tokens": getattr(resp.usage, "cache_creation_input_tokens", 0),
        }
        return record, usage


class _OpenRouterBackend:
    """OpenRouter (OpenAI-compatible) with JSON-mode output.

    No native schema enforcement, so it asks for a JSON object in JSON mode and
    leans on the pipeline's coerce floor. Determinism via temperature 0 + seed.
    Stdlib HTTP, so no extra dependency.
    """

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, model: str, max_tokens: int, temperature: float | None, seed: int):
        self.api_key = config.openrouter_api_key()
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = 0.0 if temperature is None else temperature
        self.seed = seed

    @staticmethod
    def text_block(text: str) -> dict[str, Any]:
        return {"type": "text", "text": text}

    @staticmethod
    def image_block(image_b64: str, media_type: str) -> dict[str, Any]:
        return {"type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{image_b64}"}}

    def complete(self, *, system_prompt: str, content_blocks: list[dict[str, Any]],
                 schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        sys_text = (
            system_prompt
            + "\n\nReturn ONLY a single JSON object that conforms to this JSON "
            "Schema. No prose, no markdown, no code fences:\n" + json.dumps(schema)
        )
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "seed": self.seed,
            # Suppress chain-of-thought so the budget goes to the JSON answer
            # (models that can't disable it ignore this).
            "reasoning": {"enabled": False},
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": sys_text},
                {"role": "user", "content": content_blocks},
            ],
        }
        req = urllib.request.Request(
            self.BASE_URL,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Title": "HackerRank Orchestrate",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            raise ProviderError(f"OpenRouter HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise ProviderError(f"OpenRouter connection error: {e}") from e

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ProviderError(f"OpenRouter response not JSON: {e}") from e
        if data.get("error"):
            raise ProviderError(f"OpenRouter error: {data['error']}")
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError) as e:
            raise ProviderError(f"OpenRouter response missing content: {raw[:300]}") from e

        record = _extract_json_object(content)
        if record is None:
            raise ProviderError(
                f"could not extract a JSON object (finish_reason="
                f"{choice.get('finish_reason')!r}): {str(content)[:300]}"
            )
        u = data.get("usage") or {}
        usage = {
            "model": data.get("model", self.model),
            "input_tokens": u.get("prompt_tokens"),
            "output_tokens": u.get("completion_tokens"),
        }
        return record, usage


# --- Modality adapters (compose content blocks; vendor-agnostic) ------------

class VisionAdapter(Protocol):
    def see(self, *, image_b64: str, media_type: str, system_prompt: str,
            user_prompt: str, schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        ...


class ClaimAdapter(Protocol):
    def read(self, *, system_prompt: str, user_prompt: str,
             schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        ...


class _VisionAdapter:
    def __init__(self, backend):
        self._b = backend

    def see(self, *, image_b64, media_type, system_prompt, user_prompt, schema):
        blocks = [self._b.image_block(image_b64, media_type), self._b.text_block(user_prompt)]
        return self._b.complete(system_prompt=system_prompt, content_blocks=blocks, schema=schema)


class _ClaimAdapter:
    def __init__(self, backend):
        self._b = backend

    def read(self, *, system_prompt, user_prompt, schema):
        # Text-only: just the text block. There is no image to be absent.
        blocks = [self._b.text_block(user_prompt)]
        return self._b.complete(system_prompt=system_prompt, content_blocks=blocks, schema=schema)


# --- The single provider-swap point ----------------------------------------

def _make_backend(provider: str, model: str, max_tokens: int,
                  temperature: float | None, seed: int):
    if provider == "anthropic":
        return _AnthropicBackend(model=model, max_tokens=max_tokens, temperature=temperature)
    if provider == "openrouter":
        return _OpenRouterBackend(model=model, max_tokens=max_tokens,
                                  temperature=temperature, seed=seed)
    raise ProviderError(f"unknown provider {provider!r} (use 'anthropic' or 'openrouter')")


def make_vision_adapter() -> VisionAdapter:
    """Env-selected vision adapter (Stage 1). External surface unchanged."""
    provider = config.vision_provider()
    max_tokens = config.vision_max_tokens()
    if provider == "openrouter":
        max_tokens = max(max_tokens, 4096)  # reasoning models need headroom
    backend = _make_backend(provider, config.vision_model(), max_tokens,
                            config.vision_temperature(), config.vision_seed())
    return _VisionAdapter(backend)


def make_claim_adapter() -> ClaimAdapter:
    """Env-selected claim adapter (Stage 2), text-only."""
    provider = config.claim_provider()
    max_tokens = config.claim_max_tokens()
    if provider == "openrouter":
        # Free reasoning models can ramble past a tight budget before closing the
        # JSON (finish_reason='length'); give the same headroom as vision.
        max_tokens = max(max_tokens, 4096)
    backend = _make_backend(provider, config.claim_model(), max_tokens,
                            config.claim_temperature(), config.claim_seed())
    return _ClaimAdapter(backend)
