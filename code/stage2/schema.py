"""The claim record and Stage 2's validate/repair floor.

ClaimRecord is the subset of the shared contract a claim can actually answer:
the part(s) and damage it names, optionally severity, plus the genuine claim
restated and a security signal. It carries neither image-usability nor verdict
fields (the "two booleans are different questions" split). Enums are imported
from code/vocab.py — never redefined here.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable

from vocab import CONFIDENCES, ISSUE_TYPES, OBJECT_PARTS, SEVERITIES

CLAIM_OBJECTS: tuple[str, ...] = ("car", "laptop", "package")

# A damage claim asserts damage; it never asserts "no damage present" — that's a
# vision finding. Vagueness about which damage is 'unknown', so 'none' is illegal
# for a claimed issue.
CLAIM_ISSUE_TYPES: tuple[str, ...] = tuple(t for t in ISSUE_TYPES if t != "none")

CLAIM_SUMMARY_CAP = 200
INJECTION_EXCERPT_CAP = 200


def claim_output_schema(claim_object: str) -> dict[str, Any]:
    """JSON Schema the extraction model conforms to, for a GIVEN claim_object.

    Because claim_object is known at call time, claimed_part is constrained to
    that object's exact part list (tighter than Stage 1's union). Covers only the
    fields the model emits — user_id and claim_object are injected by the caller.
    """
    parts = list(OBJECT_PARTS.get(claim_object, ("unknown",)))

    def enum(values) -> dict[str, Any]:
        return {"type": "string", "enum": list(values)}

    props = {
        "claimed_part": enum(parts),
        "additional_claimed_parts": {"type": "array", "items": enum(parts)},
        "claimed_issue_type": enum(CLAIM_ISSUE_TYPES),
        "claimed_severity": enum(SEVERITIES),
        "claim_summary": {"type": "string"},
        "confidence": enum(CONFIDENCES),
        "injection_detected": {"type": "boolean"},
        "injection_excerpt": {"type": "string"},
    }
    return {
        "type": "object",
        "properties": props,
        "required": list(props.keys()),
        "additionalProperties": False,
    }


@dataclass
class ClaimRecord:
    """One claim, read into the shared enums. Fields fixed by grounding."""
    user_id: str                       # pass-through join key
    claim_object: str                  # given input {car, laptop, package}; selects part vocab
    claimed_part: str                  # primary part from OBJECT_PARTS[claim_object]; "unknown" if unnamed
    additional_claimed_parts: list[str]  # other named parts (may be empty); mirrors Stage 1
    claimed_issue_type: str            # CLAIM_ISSUE_TYPES; "unknown" if vague, never "none"
    claimed_severity: str              # SEVERITIES; "unknown" by default
    claim_summary: str                 # genuine claim restated in English, one line, capped, inert
    confidence: str                    # CONFIDENCES — extraction confidence
    injection_detected: bool           # raw security signal (fail closed True)
    injection_excerpt: str             # planted-instruction snippet, capped & inert; "" if none

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def coerce_claim(
    raw: dict[str, Any],
    *,
    user_id: str,
    claim_object: str,
    on_repair: Callable[[str], None] | None = None,
) -> ClaimRecord:
    """Force a model-emitted dict into a clean, enum-valid ClaimRecord.

    Same fail-closed discipline as Stage 1's coerce_record. user_id and
    claim_object are supplied by the caller (pass-through / given input), not the
    model. Every out-of-vocabulary value is repaired and reported via on_repair.
    """
    def note(msg: str) -> None:
        if on_repair:
            on_repair(msg)

    def pick(value: Any, allowed: tuple[str, ...], default: str, name: str) -> str:
        if value in allowed:
            return value
        note(f"{name}={value!r} not in vocabulary → {default!r}")
        return default

    def as_text(value: Any, name: str, cap: int) -> str:
        # Guard the dict-in-text-field bug that escaped Stage 1's floor once:
        # a non-string becomes "" rather than a str()'d dict of garbage.
        if value is None:
            text = ""
        elif isinstance(value, str):
            text = value
        else:
            note(f"{name} was {type(value).__name__}, not a string → ''")
            text = ""
        if len(text) > cap:
            text = text[:cap].rstrip()
            note(f"{name} capped to {cap} chars")
        return text

    # claim_object is a trusted input; if it's somehow outside the three, we
    # cannot pick a part vocabulary, so parts fail closed to "unknown".
    if claim_object in OBJECT_PARTS:
        valid_parts = OBJECT_PARTS[claim_object]
    else:
        note(f"claim_object={claim_object!r} not in {CLAIM_OBJECTS} → parts forced to 'unknown'")
        valid_parts = ("unknown",)

    claimed_part = pick(raw.get("claimed_part"), valid_parts, "unknown", "claimed_part")

    # Additional parts: keep only those legal for THIS object, drop the primary,
    # "unknown", and duplicates, preserving order.
    additional: list[str] = []
    for p in raw.get("additional_claimed_parts") or []:
        if p not in valid_parts:
            note(f"additional_claimed_parts entry {p!r} invalid for {claim_object!r} → dropped")
            continue
        if p == claimed_part or p == "unknown" or p in additional:
            continue
        additional.append(p)

    return ClaimRecord(
        user_id=user_id,
        claim_object=claim_object,
        claimed_part=claimed_part,
        additional_claimed_parts=additional,
        # "none" is repaired to "unknown" here (claims never assert no-damage).
        claimed_issue_type=pick(
            raw.get("claimed_issue_type"), CLAIM_ISSUE_TYPES, "unknown", "claimed_issue_type"),
        claimed_severity=pick(raw.get("claimed_severity"), SEVERITIES, "unknown", "claimed_severity"),
        claim_summary=as_text(raw.get("claim_summary"), "claim_summary", CLAIM_SUMMARY_CAP),
        # Extraction confidence fails closed to "low".
        confidence=pick(raw.get("confidence"), CONFIDENCES, "low", "confidence"),
        injection_detected=_as_flag_fail_open(raw.get("injection_detected"), note),
        injection_excerpt=as_text(raw.get("injection_excerpt"), "injection_excerpt", INJECTION_EXCERPT_CAP),
    )


def _as_flag_fail_open(value: Any, note: Callable[[str], None]) -> bool:
    """A malformed injection flag must NOT silence a possible injection → True."""
    if isinstance(value, bool):
        return value
    note(f"injection_detected={value!r} not a bool → True (fail closed: never silence injection)")
    return True
