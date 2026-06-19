"""The adapter seam — one thin provider per vendor.

The pipeline trusts the *enums*, not the vendor (solution_dna.md §2.1). Each
adapter's contract is: take an image + prompt + JSON schema, and return a
schema-shaped dict — however its vendor produces structured output. Single
provider for now (Anthropic, native structured output); adding another vendor
later means writing one more adapter and changing nothing in the pipeline.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol

from . import config


class VisionError(RuntimeError):
    """The vision call could not produce a usable record. Fail closed."""


class VisionAdapter(Protocol):
    def see(
        self,
        *,
        image_b64: str,
        media_type: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return (record_dict, usage). record_dict conforms to `schema`."""
        ...


class AnthropicVisionAdapter:
    """Anthropic Messages API with native structured output (output_config.format).

    Owns this vendor's auth, message format, image encoding, and structured-output
    mechanism. Determinism: temperature is omitted by default (Opus 4.8 rejects
    it); reproducibility is the responsibility of the caching layer above.
    """

    def __init__(self, model: str | None = None, max_tokens: int | None = None):
        import anthropic  # imported lazily so the package imports without the SDK
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=config.anthropic_api_key())
        self.model = model or config.vision_model()
        self.max_tokens = max_tokens or config.vision_max_tokens()
        self.temperature = config.vision_temperature()

    def see(
        self,
        *,
        image_b64: str,
        media_type: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},  # stable enum prompt → cache it
            }],
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": media_type, "data": image_b64,
                    }},
                    {"type": "text", "text": user_prompt},
                ],
            }],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature

        try:
            resp = self._client.messages.create(**kwargs)
        except self._anthropic.APIError as e:  # network/auth/rate/server
            raise VisionError(f"Anthropic API error: {e}") from e

        # Fail closed on a refusal or a truncated record — never emit a guess.
        if resp.stop_reason == "refusal":
            raise VisionError("vision model refused the request")
        if resp.stop_reason == "max_tokens":
            raise VisionError("vision record truncated (raise VISION_MAX_TOKENS)")

        text = next((b.text for b in resp.content if b.type == "text"), None)
        if text is None:
            raise VisionError("no text block in vision response")
        try:
            record = json.loads(text)
        except json.JSONDecodeError as e:
            raise VisionError(f"vision output was not valid JSON: {e}") from e

        usage = {
            "model": resp.model,
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "cache_read_input_tokens": getattr(resp.usage, "cache_read_input_tokens", 0),
            "cache_creation_input_tokens": getattr(resp.usage, "cache_creation_input_tokens", 0),
        }
        return record, usage


def _extract_json_object(content: Any) -> dict[str, Any] | None:
    """Pull a single JSON object out of a model's text reply.

    OpenRouter has no native schema format, so a model may wrap its JSON in
    prose or code fences (reasoning models especially). Try a clean parse first,
    then strip fences, then grab the outermost {...}. Returns a dict or None.
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


class OpenRouterVisionAdapter:
    """OpenRouter (OpenAI-compatible) with JSON-mode output.

    No native schema format like Anthropic's, so it asks for a JSON object in
    JSON mode and leans on the pipeline's coerce_record validate/repair floor.
    Determinism via temperature 0 + seed (OpenRouter exposes both). Uses stdlib
    HTTP so no extra dependency is added for one adapter.
    """

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, model: str | None = None, max_tokens: int | None = None):
        self.api_key = config.openrouter_api_key()
        self.model = model or config.vision_model()
        # Structured perception doesn't need chain-of-thought, and on a reasoning
        # model the thinking eats the whole budget before the JSON is emitted
        # (finish_reason='length', empty content). Give a generous floor anyway.
        self.max_tokens = max_tokens or max(config.vision_max_tokens(), 4096)
        t = config.vision_temperature()
        self.temperature = 0.0 if t is None else t
        self.seed = config.vision_seed()

    def see(
        self,
        *,
        image_b64: str,
        media_type: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # Inject the shape OpenRouter won't enforce natively.
        sys_text = (
            system_prompt
            + "\n\nReturn ONLY a single JSON object that conforms to this JSON "
            "Schema. No prose, no markdown, no code fences:\n"
            + json.dumps(schema)
        )
        data_uri = f"data:{media_type};base64,{image_b64}"
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "seed": self.seed,
            # Suppress chain-of-thought so the token budget goes to the JSON
            # answer, not reasoning (models that can't disable it ignore this).
            "reasoning": {"enabled": False},
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": sys_text},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": user_prompt + " Respond with JSON only."},
                ]},
            ],
        }
        req = urllib.request.Request(
            self.BASE_URL,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Title": "HackerRank Orchestrate - Stage 1",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            raise VisionError(f"OpenRouter HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise VisionError(f"OpenRouter connection error: {e}") from e

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise VisionError(f"OpenRouter response not JSON: {e}") from e
        if data.get("error"):
            raise VisionError(f"OpenRouter error: {data['error']}")

        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError) as e:
            raise VisionError(f"OpenRouter response missing content: {raw[:300]}") from e

        record = _extract_json_object(content)
        if record is None:
            raise VisionError(
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


def make_vision_adapter() -> VisionAdapter:
    """Construct the env-selected vision adapter. This is the provider seam."""
    provider = config.vision_provider()
    if provider == "openrouter":
        return OpenRouterVisionAdapter()
    if provider == "anthropic":
        return AnthropicVisionAdapter()
    raise VisionError(
        f"unknown VISION_PROVIDER={provider!r} (use 'anthropic' or 'openrouter')"
    )
