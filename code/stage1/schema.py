"""The per-image blind record and Stage 1's validator.

The shared contract enums (ISSUE_TYPES, OBJECT_PARTS, SEVERITIES, CONFIDENCES)
live in code/vocab.py — neither stage owns them. This module adds the Stage-1-
internal enums and the ImageRecord shape. The record shape and the
vision/resolver ownership split are fixed by solution_dna.md (Iteration 2).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Callable

# Shared contract enums live in code/vocab.py so neither stage owns them.
from vocab import CONFIDENCES, ISSUE_TYPES, OBJECT_PARTS, SEVERITIES

# --- Stage-1-internal enums (not shared, not output columns) --------------

# Blind vision must be able to say "this is something other than the three
# claim objects" so the resolver can later raise wrong_object. claim_object
# (an input) is only {car, laptop, package}; we add other/unknown for seeing.
OBJECTS_SEEN: tuple[str, ...] = ("car", "laptop", "package", "other", "unknown")

# The only risk_flags vision owns: pure image-quality / usability. These drive
# valid_image. Every other risk_flag needs the claim or history → resolver.
QUALITY_FLAGS: tuple[str, ...] = (
    "blurry_image", "low_light_or_glare", "cropped_or_obstructed", "wrong_angle",
)

# Union of every part, for the structured-output schema. Object↔part
# consistency is enforced in Python (a flat enum would allow a laptop with a
# "windshield").
ALL_PARTS: tuple[str, ...] = tuple(
    sorted({p for parts in OBJECT_PARTS.values() for p in parts})
)

TEXT_CONTENT_CAP = 200
OBSERVATION_CAP = 240


# --- The per-image blind record -------------------------------------------

@dataclass
class ImageRecord:
    """One image, seen blind. Fields and ownership are locked by solution_dna.md.

    `image_id` is the bare contract id (filename without extension). `image_ref`
    is the full relative path — the internal cache/uniqueness key, since `img_1`
    repeats across case folders.
    """
    image_id: str               # bare img_N — for the contract / supporting_image_ids
    image_ref: str              # full relative path — internal cache + uniqueness key

    object_seen: str            # OBJECTS_SEEN
    object_part_seen: str       # part valid for object_seen, else "unknown" (primary)
    additional_parts_seen: list[str]  # other parts present (may be empty)
    issue_type_seen: str        # ISSUE_TYPES; "none" = part visible & clean
    severity_seen: str          # SEVERITIES (perception property — vision owns it)

    valid_image: bool           # usable for automated review (vision owns "usable")
    quality_flags: list[str]    # subset of QUALITY_FLAGS justifying valid_image

    looks_manipulated: bool     # raw authenticity hint; resolver owns the final flag
    looks_non_original: bool    # raw authenticity hint; resolver owns the final flag

    text_seen: bool             # any writing visible in the image at all
    text_content: str           # the text, capped & inert ("" if none) — for Stage 2

    observation: str            # one-line, image-grounded, plain language
    confidence: str             # CONFIDENCES — drives the "look closer" trigger
    pass_type: str = "blind_global"  # which DNA pass produced this record

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --- Structured-output schema (the adapter's "return validated enums" contract) ---

def vision_output_schema() -> dict[str, Any]:
    """JSON Schema the vision model must conform its output to.

    Covers only the fields the *model* perceives. image_id/image_ref/pass_type
    are attached by the pipeline, not emitted by the model. object_part uses the
    full union; object↔part consistency is enforced in `coerce_record`.
    """
    def enum(values: tuple[str, ...]) -> dict[str, Any]:
        return {"type": "string", "enum": list(values)}

    def enum_array(values: tuple[str, ...]) -> dict[str, Any]:
        return {"type": "array", "items": {"type": "string", "enum": list(values)}}

    props = {
        "object_seen": enum(OBJECTS_SEEN),
        "object_part_seen": enum(ALL_PARTS),
        "additional_parts_seen": enum_array(ALL_PARTS),
        "issue_type_seen": enum(ISSUE_TYPES),
        "severity_seen": enum(SEVERITIES),
        "valid_image": {"type": "boolean"},
        "quality_flags": enum_array(QUALITY_FLAGS),
        "looks_manipulated": {"type": "boolean"},
        "looks_non_original": {"type": "boolean"},
        "text_seen": {"type": "boolean"},
        "text_content": {"type": "string"},
        "observation": {"type": "string"},
        "confidence": enum(CONFIDENCES),
    }
    return {
        "type": "object",
        "properties": props,
        "required": list(props.keys()),
        "additionalProperties": False,
    }


# --- Validate / repair (defense in depth) ---------------------------------

def coerce_record(
    raw: dict[str, Any],
    *,
    image_id: str,
    image_ref: str,
    pass_type: str = "blind_global",
    on_repair: Callable[[str], None] | None = None,
) -> ImageRecord:
    """Force a model-emitted dict into a clean, enum-valid ImageRecord.

    Native structured output already constrains the shape; this is the floor
    under it. Out-of-vocabulary values fail closed (→ unknown / false / []),
    and every repair is reported via `on_repair` so silent drift is impossible.
    """
    def note(msg: str) -> None:
        if on_repair:
            on_repair(msg)

    def pick(value: Any, allowed: tuple[str, ...], default: str, name: str) -> str:
        if value in allowed:
            return value
        note(f"{name}={value!r} not in vocabulary → {default!r}")
        return default

    def as_bool(value: Any, name: str) -> bool:
        if isinstance(value, bool):
            return value
        note(f"{name}={value!r} not a bool → False")
        return False

    object_seen = pick(raw.get("object_seen"), OBJECTS_SEEN, "unknown", "object_seen")

    # Part vocabulary is conditioned on the object actually seen.
    if object_seen in OBJECT_PARTS:
        valid_parts = OBJECT_PARTS[object_seen]
    else:
        valid_parts = ("unknown",)
        if raw.get("object_part_seen") not in (None, "unknown"):
            note(f"object_seen={object_seen!r} has no parts → object_part_seen forced to 'unknown'")

    object_part_seen = pick(raw.get("object_part_seen"), valid_parts, "unknown", "object_part_seen")

    # Additional parts: keep only those valid for this object, drop the primary
    # and any duplicates, preserving order.
    additional: list[str] = []
    for p in raw.get("additional_parts_seen") or []:
        if p not in valid_parts:
            note(f"additional_parts_seen entry {p!r} invalid for {object_seen!r} → dropped")
            continue
        if p == object_part_seen or p == "unknown" or p in additional:
            continue
        additional.append(p)

    # Quality flags: keep only the vision-owned usability flags, deduped.
    quality: list[str] = []
    for f in raw.get("quality_flags") or []:
        if f not in QUALITY_FLAGS:
            note(f"quality_flags entry {f!r} not vision-owned → dropped")
            continue
        if f not in quality:
            quality.append(f)

    def as_text(value: Any, name: str) -> str:
        # Fail closed: a non-string (e.g. a model echoing the schema fragment
        # {"type": "string"}) becomes "" rather than a str()'d dict of garbage.
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        note(f"{name} was {type(value).__name__}, not a string → ''")
        return ""

    text_seen = as_bool(raw.get("text_seen"), "text_seen")
    text_content = as_text(raw.get("text_content"), "text_content")
    if len(text_content) > TEXT_CONTENT_CAP:
        text_content = text_content[:TEXT_CONTENT_CAP]
        note(f"text_content capped to {TEXT_CONTENT_CAP} chars")

    observation = as_text(raw.get("observation"), "observation").strip()
    if len(observation) > OBSERVATION_CAP:
        observation = observation[:OBSERVATION_CAP].rstrip()
        note(f"observation capped to {OBSERVATION_CAP} chars")

    return ImageRecord(
        image_id=image_id,
        image_ref=image_ref,
        object_seen=object_seen,
        object_part_seen=object_part_seen,
        additional_parts_seen=additional,
        issue_type_seen=pick(raw.get("issue_type_seen"), ISSUE_TYPES, "unknown", "issue_type_seen"),
        severity_seen=pick(raw.get("severity_seen"), SEVERITIES, "unknown", "severity_seen"),
        valid_image=as_bool(raw.get("valid_image"), "valid_image"),
        quality_flags=quality,
        looks_manipulated=as_bool(raw.get("looks_manipulated"), "looks_manipulated"),
        looks_non_original=as_bool(raw.get("looks_non_original"), "looks_non_original"),
        text_seen=text_seen,
        text_content=text_content,
        observation=observation,
        # Confidence fails closed to "low": an unparseable confidence should
        # trigger the look-closer path, not be trusted.
        confidence=pick(raw.get("confidence"), CONFIDENCES, "low", "confidence"),
        pass_type=pass_type,
    )
