"""Evidence-requirements loader and keyer.

Reads ``dataset/evidence_requirements.csv`` (11 rules) and exposes a lookup:
given ``claim_object`` + ``claimed_issue_type``, return matching rule(s).

Matching logic:
- Rules where ``claim_object`` matches exactly, OR where ``claim_object=all``
  (cross-cutting rules REQ_GENERAL_*, REQ_REVIEW_TRUST).
- Fuzzy-match the claimed issue against the ``applies_to`` family. E.g.
  ``applies_to="dent or scratch"`` matches ``issue_type ∈ {dent, scratch}``.

Returns applicable ``minimum_image_evidence`` text(s) and rule IDs. Keying
only — no pass/fail judgment (that belongs to the resolver in Phase 2).
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# applies_to → issue_type set mapping
# ---------------------------------------------------------------------------
# Each applies_to string covers an "issue family". We parse the natural-
# language description into a set of vocab.py issue_type tokens.

_APPLIES_TO_MAP: dict[str, set[str]] = {
    "general claim review": set(),               # cross-cutting, always matches
    "multi-image rows": set(),                    # cross-cutting, always matches
    "reviewability": set(),                       # cross-cutting, always matches
    "dent or scratch": {"dent", "scratch"},
    "crack, broken, or missing part": {"crack", "glass_shatter", "broken_part", "missing_part"},
    "vehicle identity or orientation": set(),     # context rule, always matches for cars
    "screen, keyboard, or trackpad": {"crack", "glass_shatter", "broken_part", "missing_part",
                                       "stain", "water_damage", "scratch", "dent"},
    "hinge, lid, corner, body, or port": {"broken_part", "crack", "dent", "scratch"},
    "crushed, torn, or seal damage": {"crushed_packaging", "torn_packaging"},
    "water, stain, or label damage": {"water_damage", "stain"},
    "contents or inner item": {"missing_part", "broken_part"},
}

# Families with empty sets are "always-match" (cross-cutting or context).
_ALWAYS_MATCH_FAMILIES = {k for k, v in _APPLIES_TO_MAP.items() if len(v) == 0}


@dataclass(frozen=True)
class EvidenceRule:
    """One row from evidence_requirements.csv."""
    requirement_id: str
    claim_object: str           # "car", "laptop", "package", or "all"
    applies_to: str             # issue family description
    minimum_image_evidence: str  # the requirement text


@dataclass(frozen=True)
class EvidenceMatch:
    """A rule matched by the keyer, returned to the resolver."""
    requirement_id: str
    applies_to: str
    minimum_image_evidence: str


class EvidenceRequirements:
    """Loader + keyer for evidence_requirements.csv."""

    def __init__(self, csv_path: str) -> None:
        self._rules: list[EvidenceRule] = []
        self._load(csv_path)

    def _load(self, csv_path: str) -> None:
        with open(csv_path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                self._rules.append(EvidenceRule(
                    requirement_id=row["requirement_id"].strip(),
                    claim_object=row["claim_object"].strip(),
                    applies_to=row["applies_to"].strip(),
                    minimum_image_evidence=row["minimum_image_evidence"].strip(),
                ))

    @property
    def rules(self) -> list[EvidenceRule]:
        """All loaded rules (read-only view)."""
        return list(self._rules)

    def lookup(self, claim_object: str, claimed_issue_type: str) -> list[EvidenceMatch]:
        """Return evidence rules matching this claim.

        A rule matches when:
        1. Its claim_object == the claim's object, OR claim_object == "all".
        2. Its applies_to family either always-matches (cross-cutting) or
           contains the claimed issue_type.

        Returns a list of EvidenceMatch (may be empty if no rules match,
        though in practice at least the cross-cutting rules always match).
        """
        matches: list[EvidenceMatch] = []
        for rule in self._rules:
            # Object filter: exact match or "all".
            if rule.claim_object != "all" and rule.claim_object != claim_object:
                continue

            # Issue-family filter.
            family_issues = _APPLIES_TO_MAP.get(rule.applies_to)
            if family_issues is None:
                # Unknown applies_to — conservative: treat as always-match.
                matches.append(EvidenceMatch(
                    requirement_id=rule.requirement_id,
                    applies_to=rule.applies_to,
                    minimum_image_evidence=rule.minimum_image_evidence,
                ))
                continue

            if rule.applies_to in _ALWAYS_MATCH_FAMILIES:
                matches.append(EvidenceMatch(
                    requirement_id=rule.requirement_id,
                    applies_to=rule.applies_to,
                    minimum_image_evidence=rule.minimum_image_evidence,
                ))
                continue

            if claimed_issue_type in family_issues:
                matches.append(EvidenceMatch(
                    requirement_id=rule.requirement_id,
                    applies_to=rule.applies_to,
                    minimum_image_evidence=rule.minimum_image_evidence,
                ))

        return matches


def load_evidence_requirements(dataset_dir: str | None = None) -> EvidenceRequirements:
    """Convenience loader: resolves the default CSV path from the repo root."""
    if dataset_dir is None:
        # Resolve: code/stage3/evidence.py → code/ → repo root → dataset/
        code_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dataset_dir = os.path.join(os.path.dirname(code_dir), "dataset")
    csv_path = os.path.join(dataset_dir, "evidence_requirements.csv")
    return EvidenceRequirements(csv_path)
