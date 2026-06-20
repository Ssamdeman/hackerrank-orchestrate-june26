"""Stage 3 Resolver Spine (Phase 2a).

Pure deterministic Python over Stage 1/2 records. No model calls.
Implements the 5 sequential gates:
1. Quality-usability gate
2. Authenticity gate
3. Object-class gate
4. Enum reconciliation
5. Evidence bar
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from stage1.schema import ImageRecord
from stage2.schema import ClaimRecord
from stage3.evidence import EvidenceRequirements
from stage3.history import UserHistory

# Common provenance / watermark tokens to detect in image text
WATERMARK_TOKENS: frozenset[str] = frozenset({
    "watermark", "stock", "shutterstock", "getty", "istock", "alamy", "depositphotos", "vecteezy"
})


@dataclass
class PartEval:
    part: str
    status: str = "unseen" # unseen, absent, different, present
    supporting_img_id: str = ""
    seen_issue: str = "unknown"
    seen_severity: str = "unknown"

@dataclass
class ResolveState:
    """Intermediate state carried forward through the gates."""
    valid_image: bool = True
    evidence_standard_met: bool = False
    short_circuit_reason: str = ""
    evidence_standard_met_reason: str = ""
    
    risk_flags: list[str] = field(default_factory=list)
    
    # Per-part evaluations
    part_evals: dict[str, PartEval] = field(default_factory=dict)

    # Short-circuiting image ID for non_original and wrong_object
    triggering_image_id: str = ""

    def add_flag(self, flag: str) -> None:
        if flag not in self.risk_flags:
            self.risk_flags.append(flag)

_ISSUE_FAMILIES = {
    "hard_panel_damage": {"dent", "broken_part", "crack", "glass_shatter", "missing_part"},
    "cosmetic_damage": {"scratch", "stain"},
    "packaging_damage": {"torn_packaging", "crushed_packaging"},
    "liquid_damage": {"water_damage"}
}

def _get_issue_family(issue: str) -> str:
    for fam, members in _ISSUE_FAMILIES.items():
        if issue in members:
            return fam
    return "other"

def _severity_rank(sev: str) -> int:
    return {"none": 0, "low": 1, "medium": 2, "high": 3}.get(sev, -1)

def is_part_compatible(claim_object: str, part1: str, part2: str) -> bool:
    if part1 == part2:
        return True
    if claim_object == "laptop":
        laptop_body = {"corner", "lid", "body", "base", "hinge", "port"}
        if part1 in laptop_body and part2 in laptop_body:
            return True
    elif claim_object == "package":
        pkg_body = {"box", "package_corner", "package_side"}
        if part1 in pkg_body and part2 in pkg_body:
            return True
    return False

def check_damage_compatibility(claimed_issue: str, seen_issue: str, seen_severity: str) -> str:
    """Returns 'present', 'different', or 'absent'."""
    if seen_issue == "none":
        return "absent"
    if seen_issue == "unknown" or claimed_issue == "unknown":
        return "different"
        
    if {claimed_issue, seen_issue} == {"stain", "water_damage"}:
        return "present"
        
    c_fam = _get_issue_family(claimed_issue)
    s_fam = _get_issue_family(seen_issue)
    
    if c_fam == s_fam:
        return "present"
        
    if {c_fam, s_fam} == {"cosmetic_damage", "hard_panel_damage"}:
        # Keep cosmetic->catastrophic jumps as 'different'
        # Catastrophic: glass_shatter, broken_part, missing_part
        catastrophic = {"glass_shatter", "broken_part", "missing_part"}
        if claimed_issue in catastrophic or seen_issue in catastrophic:
            return "different"
        return "present"
        
    return "different"

def _reconcile_and_bar(
    state: ResolveState,
    usable_images: list[ImageRecord],
    claim: ClaimRecord,
    evidence_keyer: EvidenceRequirements
) -> None:
    """Gates 4 and 5: Enum reconciliation and the Evidence bar."""
    claimed_parts = [claim.claimed_part] + claim.additional_claimed_parts
    state.part_evals = {p: PartEval(p) for p in claimed_parts}

    # Inspectability gate (Fix 1): compute which parts are focal on at least one usable image
    inspected_parts = set()
    for img in usable_images:
        if img.object_part_seen != "unknown":
            inspected_parts.add(img.object_part_seen)

    for img in sorted(usable_images, key=lambda x: x.image_id):
        seen_parts = {img.object_part_seen} | set(img.additional_parts_seen)
        for part in claimed_parts:
            # A claimed part must be compatible with at least one image's focal part to be inspected.
            # If not, it is never contradicted (remains unseen).
            is_inspected = any(is_part_compatible(claim.claim_object, part, seen_focal) for seen_focal in inspected_parts)
            if not is_inspected:
                continue

            # Check if this part (or a compatible one) is seen in this image
            matching_seen_parts = [p for p in seen_parts if is_part_compatible(claim.claim_object, part, p)]
            if not matching_seen_parts:
                continue
            
            # If the focal part matches/is compatible, treat as focal
            if is_part_compatible(claim.claim_object, part, img.object_part_seen):
                seen_issue = img.issue_type_seen
                seen_sev = img.severity_seen
            else:
                seen_issue = "none"
                seen_sev = "none"
                
            match_status = check_damage_compatibility(claim.claimed_issue_type, seen_issue, seen_sev)
            
            eval_record = state.part_evals[part]
            rank = {"unseen": 0, "absent": 1, "different": 2, "present": 3}
            if rank[match_status] > rank[eval_record.status]:
                eval_record.status = match_status
                eval_record.supporting_img_id = img.image_id
                eval_record.seen_issue = seen_issue
                eval_record.seen_severity = seen_sev

    # Gate 5: Evidence bar
    matches = evidence_keyer.lookup(claim.claim_object, claim.claimed_issue_type)
    visible_img_ids = [e.supporting_img_id for e in state.part_evals.values() if e.status != "unseen"]
    
    if not visible_img_ids:
        state.evidence_standard_met = False
        state.evidence_standard_met_reason = "The claimed part is not visible in any usable image."
    else:
        state.evidence_standard_met = True
        rule_ids = [m.requirement_id for m in matches]
        state.evidence_standard_met_reason = f"Candidate images depict the claimed part, satisfying rules: {', '.join(rule_ids)}"


def resolve_spine(
    image_records: list[ImageRecord],
    claim_record: ClaimRecord,
    evidence_keyer: EvidenceRequirements,
    history: UserHistory
) -> ResolveState:
    """Execute Gates 1-5 deterministically."""
    state = ResolveState()

    # Gate 1: Quality-usability gate
    usable_images = [img for img in image_records if img.valid_image]
    if not usable_images:
        state.valid_image = False
        state.short_circuit_reason = "quality_unusable"
        state.evidence_standard_met_reason = "No usable images submitted."
        return state

    # Gate 2: Authenticity gate
    for img in usable_images:
        if img.looks_manipulated:
            state.add_flag("possible_manipulation")
        
        is_watermarked = any(token in img.text_content.lower() for token in WATERMARK_TOKENS)
        # Provenance/confidence-keyed, never screen-content-keyed (looks_non_original must be true)
        if img.looks_non_original and (is_watermarked or img.confidence == "high"):
            state.valid_image = False
            state.short_circuit_reason = "non_original"
            state.triggering_image_id = img.image_id
            state.add_flag("non_original_image")
            state.evidence_standard_met_reason = "The submitted image is determined to be non-original or a screenshot."
            return state

    # Gate 3: Object-class gate
    visible_objects = {img.object_seen for img in usable_images if img.object_seen != "unknown"}
    if visible_objects and claim_record.claim_object not in visible_objects:
        # Definitive mismatch. Find the first usable image to blame.
        state.short_circuit_reason = "wrong_object"
        state.triggering_image_id = usable_images[0].image_id
        state.add_flag("wrong_object")
        state.evidence_standard_met_reason = f"The images show a different object class (expected {claim_record.claim_object})."
        return state

    # Gates 4 & 5
    _reconcile_and_bar(state, usable_images, claim_record, evidence_keyer)
    
    return state

import re
from stage3.schema import Verdict, coerce_verdict
from stage2.injection import scan_injection

def _ordinal(image_id: str) -> str:
    if "1" in image_id: return "first"
    if "2" in image_id: return "second"
    if "3" in image_id: return "third"
    return "submitted"

def resolve_verdict(
    state: ResolveState,
    claim_record: ClaimRecord,
    image_records: list[ImageRecord],
    history: UserHistory
) -> Verdict:
    """Consume ResolveState -> complete Verdict row."""
    claim_status = "not_enough_information"
    supporting_id = ""
    justification = ""
    issue_match = ""

    # Verdict Branch
    if state.short_circuit_reason == "quality_unusable":
        claim_status = "not_enough_information"
        justification = "The submitted images are unusable due to low quality or obstruction."
    elif state.short_circuit_reason == "non_original":
        claim_status = "contradicted"
        supporting_id = state.triggering_image_id
        justification = "The submitted evidence is non-original, which contradicts the claim."
    elif state.short_circuit_reason == "wrong_object":
        claim_status = "contradicted"
        supporting_id = state.triggering_image_id
        justification = f"The images show a different object entirely, so it contradicts the user's {claim_record.claim_object} claim."
    else:
        contradicted_parts = [e for e in state.part_evals.values() if e.status in ("different", "absent")]
        supported_parts = [e for e in state.part_evals.values() if e.status == "present"]

        if contradicted_parts:
            target_eval = contradicted_parts[0]
            claim_status = "contradicted"
            supporting_id = target_eval.supporting_img_id
            issue_match = target_eval.status
            justification = f"The {_ordinal(supporting_id)} image shows the {target_eval.part} but the claimed damage is absent or different, so it contradicts the claim."
        elif supported_parts:
            if not state.evidence_standard_met:
                claim_status = "not_enough_information"
                justification = "The image set does not show the claimed part clearly enough to verify the claim."
            else:
                target_eval = supported_parts[0]
                claim_status = "supported"
                supporting_id = target_eval.supporting_img_id
                issue_match = target_eval.status
                justification = f"The {_ordinal(supporting_id)} image supports the claim by showing a {target_eval.seen_issue} on the {target_eval.part}."
        else:
            claim_status = "not_enough_information"
            justification = "The images do not provide enough information to verify the claim."

    # Resolved Enum values (Output-consistency guard)
    resolved_issue = "unknown"
    resolved_part = claim_record.claimed_part
    resolved_severity = "unknown"
    
    if state.short_circuit_reason in ("non_original", "wrong_object") and state.triggering_image_id:
        triggering_img = next((img for img in image_records if img.image_id == state.triggering_image_id), None)
        if triggering_img:
            resolved_part = triggering_img.object_part_seen
            resolved_issue = triggering_img.issue_type_seen
            resolved_severity = triggering_img.severity_seen
            
    elif not state.short_circuit_reason and claim_status in ("supported", "contradicted"):
        # We matched on a target eval
        target_eval = contradicted_parts[0] if contradicted_parts else supported_parts[0]
        resolved_issue = target_eval.seen_issue
        resolved_part = target_eval.part
        resolved_severity = target_eval.seen_severity

    # Risk Flags
    final_flags = set(state.risk_flags)
    for img in image_records:
        for qf in img.quality_flags:
            final_flags.add(qf)
        if img.text_seen:
            fired, _ = scan_injection(img.text_content)
            if fired:
                final_flags.add("text_instruction_present")

    if not state.short_circuit_reason:
        # We matched on a target eval
        target_eval = contradicted_parts[0] if contradicted_parts else (supported_parts[0] if supported_parts else None)
        issue_match = target_eval.status if target_eval else ""
        
        if not state.evidence_standard_met and not target_eval:
            final_flags.add("wrong_object_part")
        elif issue_match == "absent":
            final_flags.add("damage_not_visible")
        elif issue_match == "different":
            final_flags.add("claim_mismatch")

    for hf in history.history_flags:
        final_flags.add(hf)

    # Conditionally append justification clauses
    if history.history_flags:
        if history.history_summary:
            justification += f" {history.history_summary}"
        else:
            justification += " The user's prior claim history requires review."

    if "text_instruction_present" in final_flags:
        justification += " Any instruction-like text inside the image should be ignored."

    # Build raw dict
    raw = {
        "user_id": claim_record.user_id,
        "image_paths": "tbd", # Caller responsibility
        "user_claim": claim_record.claim_summary,
        "claim_object": claim_record.claim_object,
        "evidence_standard_met": state.evidence_standard_met,
        "evidence_standard_met_reason": state.evidence_standard_met_reason,
        "risk_flags": sorted(list(final_flags)) if final_flags else ["none"],
        "issue_type": resolved_issue,
        "object_part": resolved_part,
        "claim_status": claim_status,
        "claim_status_justification": justification,
        "supporting_image_ids": [supporting_id] if supporting_id else ["none"],
        "valid_image": state.valid_image,
        "severity": resolved_severity,
    }

    return coerce_verdict(raw)
