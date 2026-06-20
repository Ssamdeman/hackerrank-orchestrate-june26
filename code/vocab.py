"""Shared controlled vocabularies — the contract both stages emit into.

Stage 1 (Seeing) and Stage 2 (Reading the claim) classify into these exact
enums, so Stage 3 reconciles by string match rather than semantic guess. Neither
stage owns this contract; both import from here.

Enum lists are copied verbatim from problem_statement.md. No value here may
change without re-running both stages' tests — this is the join key between them.
"""
from __future__ import annotations

ISSUE_TYPES: tuple[str, ...] = (
    "dent", "scratch", "crack", "glass_shatter", "broken_part", "missing_part",
    "torn_packaging", "crushed_packaging", "water_damage", "stain", "none", "unknown",
)

# object_part is object-conditioned — the valid vocabulary depends on the object,
# so it can never be a single flat enum. A part legal for one object is illegal
# for another.
OBJECT_PARTS: dict[str, tuple[str, ...]] = {
    "car": ("front_bumper", "rear_bumper", "door", "hood", "windshield", "side_mirror",
            "headlight", "taillight", "fender", "quarter_panel", "body", "unknown"),
    "laptop": ("screen", "keyboard", "trackpad", "hinge", "lid", "corner", "port",
               "base", "body", "unknown"),
    "package": ("box", "package_corner", "package_side", "seal", "label", "contents",
                "item", "unknown"),
}

SEVERITIES: tuple[str, ...] = ("none", "low", "medium", "high", "unknown")

# Self-reported model confidence — shared shape across stages (Stage 1:
# perceptual confidence; Stage 2: extraction confidence).
CONFIDENCES: tuple[str, ...] = ("low", "medium", "high")
