"""The Verdict record and Stage 3's validation floor.

Verdict is the final output row — exactly the 14 columns from
problem_statement.md, in order. Enum fields are validated against vocab.py
(single source of truth). Invalid values fail closed to safe defaults.
Booleans are coerced; text fields are capped. to_csv_row() emits the 14 fields
in exact column order with correct semicolon-joining and ``none`` sentinels.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# Single source of truth — import, never redefine.
from vocab import ISSUE_TYPES, OBJECT_PARTS, SEVERITIES

# ---------------------------------------------------------------------------
# Output-column enums not in vocab.py (output-layer only)
# ---------------------------------------------------------------------------

CLAIM_STATUSES: tuple[str, ...] = ("supported", "contradicted", "not_enough_information")

# risk_flags vocabulary — every legal token from problem_statement.md §140.
RISK_FLAGS: tuple[str, ...] = (
    "none",
    "blurry_image",
    "cropped_or_obstructed",
    "low_light_or_glare",
    "wrong_angle",
    "wrong_object",
    "wrong_object_part",
    "damage_not_visible",
    "claim_mismatch",
    "possible_manipulation",
    "non_original_image",
    "text_instruction_present",
    "user_history_risk",
    "manual_review_required",
)

# The 14 output columns, in exact contract order.
OUTPUT_COLUMNS: tuple[str, ...] = (
    "user_id",
    "image_paths",
    "user_claim",
    "claim_object",
    "evidence_standard_met",
    "evidence_standard_met_reason",
    "risk_flags",
    "issue_type",
    "object_part",
    "claim_status",
    "claim_status_justification",
    "supporting_image_ids",
    "valid_image",
    "severity",
)

# Text-field caps (consistent with Stage 1/2 discipline).
REASON_CAP = 300
JUSTIFICATION_CAP = 400


# ---------------------------------------------------------------------------
# The Verdict record
# ---------------------------------------------------------------------------

@dataclass
class Verdict:
    """One claim verdict — the 14-column output row.

    Pass-through fields (user_id, image_paths, user_claim, claim_object) come
    from the raw CSV row. Everything else is resolved by Stage 3.
    """
    # 1-4: pass-through
    user_id: str
    image_paths: str
    user_claim: str
    claim_object: str

    # 5-6: evidence standard
    evidence_standard_met: bool
    evidence_standard_met_reason: str

    # 7: risk flags (list internally; serialized to ;-joined or "none")
    risk_flags: list[str]

    # 8-9: issue + part (object-conditioned)
    issue_type: str
    object_part: str

    # 10-11: verdict
    claim_status: str
    claim_status_justification: str

    # 12: supporting images (list internally; serialized to ;-joined or "none")
    supporting_image_ids: list[str]

    # 13: image usability
    valid_image: bool

    # 14: severity
    severity: str

    def to_csv_row(self) -> dict[str, str]:
        """Emit the 14 fields as a dict with string values, contract-ready.

        Booleans → lowercase ``true``/``false``.
        Lists → semicolon-joined, or ``none`` if empty.
        """
        def bool_str(v: bool) -> str:
            return "true" if v else "false"

        def list_str(items: list[str]) -> str:
            if not items:
                return "none"
            return ";".join(items)

        return {
            "user_id": self.user_id,
            "image_paths": self.image_paths,
            "user_claim": self.user_claim,
            "claim_object": self.claim_object,
            "evidence_standard_met": bool_str(self.evidence_standard_met),
            "evidence_standard_met_reason": self.evidence_standard_met_reason,
            "risk_flags": list_str(self.risk_flags),
            "issue_type": self.issue_type,
            "object_part": self.object_part,
            "claim_status": self.claim_status,
            "claim_status_justification": self.claim_status_justification,
            "supporting_image_ids": list_str(self.supporting_image_ids),
            "valid_image": bool_str(self.valid_image),
            "severity": self.severity,
        }


# ---------------------------------------------------------------------------
# Validation / coercion floor
# ---------------------------------------------------------------------------

def coerce_verdict(
    raw: dict[str, Any],
    *,
    on_repair: Callable[[str], None] | None = None,
) -> Verdict:
    """Force a resolver-built dict into a clean, contract-valid Verdict.

    Same fail-closed discipline as Stage 1/2: out-of-vocabulary values are
    repaired to safe defaults (``unknown``, ``not_enough_information``,
    ``false``) and every repair is reported via ``on_repair``.
    """
    def note(msg: str) -> None:
        if on_repair:
            on_repair(msg)

    def pick(value: Any, allowed: tuple[str, ...], default: str, name: str) -> str:
        if value in allowed:
            return value
        note(f"{name}={value!r} not in vocabulary → {default!r}")
        return default

    def as_bool(value: Any, name: str, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        note(f"{name}={value!r} not a bool → {default}")
        return default

    def as_text(value: Any, name: str, cap: int) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            text = value
        else:
            note(f"{name} was {type(value).__name__}, not a string → ''")
            text = ""
        if len(text) > cap:
            text = text[:cap].rstrip()
            note(f"{name} capped to {cap} chars")
        return text

    # --- Pass-throughs (strings, no validation — they come from the CSV) ---
    user_id = str(raw.get("user_id", ""))
    image_paths = str(raw.get("image_paths", ""))
    user_claim = str(raw.get("user_claim", ""))
    claim_object = str(raw.get("claim_object", ""))

    # --- Object-conditioned part vocabulary ---
    if claim_object in OBJECT_PARTS:
        valid_parts = OBJECT_PARTS[claim_object]
    else:
        valid_parts = ("unknown",)
        if raw.get("object_part") not in (None, "unknown"):
            note(f"claim_object={claim_object!r} has no parts → object_part forced to 'unknown'")

    # --- Enum fields ---
    issue_type = pick(raw.get("issue_type"), ISSUE_TYPES, "unknown", "issue_type")
    object_part = pick(raw.get("object_part"), valid_parts, "unknown", "object_part")
    severity = pick(raw.get("severity"), SEVERITIES, "unknown", "severity")
    claim_status = pick(raw.get("claim_status"), CLAIM_STATUSES,
                        "not_enough_information", "claim_status")

    # --- risk_flags: keep only legal tokens, deduped, order-preserved ---
    risk_flags_raw = raw.get("risk_flags")
    if not isinstance(risk_flags_raw, list):
        note(f"risk_flags was {type(risk_flags_raw).__name__}, not a list → []")
        risk_flags_raw = []

    risk_flags: list[str] = []
    for f in risk_flags_raw:
        if f not in RISK_FLAGS or f == "none":
            if f != "none":
                note(f"risk_flags entry {f!r} not in vocabulary → dropped")
            continue
        if f not in risk_flags:
            risk_flags.append(f)

    # --- supporting_image_ids: list of strings, deduped ---
    sids_raw = raw.get("supporting_image_ids")
    if not isinstance(sids_raw, list):
        note(f"supporting_image_ids was {type(sids_raw).__name__}, not a list → []")
        sids_raw = []

    supporting_image_ids: list[str] = []
    for sid in sids_raw:
        if isinstance(sid, str) and sid and sid != "none" and sid not in supporting_image_ids:
            supporting_image_ids.append(sid)

    # --- Booleans ---
    evidence_standard_met = as_bool(raw.get("evidence_standard_met"),
                                     "evidence_standard_met")
    valid_image = as_bool(raw.get("valid_image"), "valid_image")

    # --- Text fields ---
    evidence_standard_met_reason = as_text(
        raw.get("evidence_standard_met_reason"),
        "evidence_standard_met_reason", REASON_CAP)
    claim_status_justification = as_text(
        raw.get("claim_status_justification"),
        "claim_status_justification", JUSTIFICATION_CAP)

    return Verdict(
        user_id=user_id,
        image_paths=image_paths,
        user_claim=user_claim,
        claim_object=claim_object,
        evidence_standard_met=evidence_standard_met,
        evidence_standard_met_reason=evidence_standard_met_reason,
        risk_flags=risk_flags,
        issue_type=issue_type,
        object_part=object_part,
        claim_status=claim_status,
        claim_status_justification=claim_status_justification,
        supporting_image_ids=supporting_image_ids,
        valid_image=valid_image,
        severity=severity,
    )
