"""Deterministic injection floor — the un-suppressible half of the flag.

Runs over the RAW user_claim bytes, in code, outside any model field. Scope is
categorical and narrow: LLM-control syntax ONLY — attacks on the model itself
(ignore previous instructions, system prompt, override context, role injection).
It is defined by attack category, not mined from sample frequency.

EXPLICITLY OUT: business-logic imperatives ("you must approve", "refund now",
"approve regardless"). Those are indistinguishable from an angry but legitimate
claimant, so they belong to the model's semantic read, never to a deterministic
floor that fails open. This is a high-PRECISION floor, not high-recall: a false
positive on a furious customer is the failure mode we refuse.
"""
from __future__ import annotations

import re

EXCERPT_CAP = 200

# DOTALL so `.` spans the " | " turn separators; IGNORECASE for register.
_F = re.IGNORECASE | re.DOTALL

# Pattern categories (templates, not exact sample strings). Each targets the
# LLM-control register only.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # 1. ignore / override the previous|above|all instructions/prompt/context
    ("ignore_previous_instructions", re.compile(
        r"\b(?:ignore|disregard|forget|skip|override|bypass)\b.{0,40}?"
        r"\b(?:previous|prior|above|earlier|preceding|all|any|the)\b.{0,25}?"
        r"\b(?:instruction|instructions|prompt|prompts|message|messages|context|"
        r"rule|rules|direction|directions|guideline|guidelines)\b", _F)),

    # 2. references to the system/developer prompt itself
    ("system_prompt_reference", re.compile(
        r"\b(?:system|developer)\s+(?:prompt|message|instruction|instructions|role)\b", _F)),

    # 3. override/disable the system, guardrails, filters, safety
    ("override_guardrails", re.compile(
        r"\b(?:override|bypass|disable|circumvent|turn\s+off)\b.{0,30}?"
        r"\b(?:system|guardrail|guardrails|filter|filters|safety|restriction|"
        r"restrictions|moderation)\b", _F)),

    # 4. ignore your own instructions/guidelines/programming
    ("ignore_your_instructions", re.compile(
        r"\bignore\s+your\b.{0,20}?"
        r"\b(?:instruction|instructions|guideline|guidelines|rule|rules|"
        r"programming|training|prompt)\b", _F)),

    # 5. role reset — "you are now a/an/in ... / no longer / unrestricted"
    ("role_reset", re.compile(
        r"\byou\s+are\s+now\b.{0,30}?"
        r"\b(?:a|an|in|going\s+to|no\s+longer|free|unrestricted|dan|jailbroken)\b", _F)),

    # 6. impersonation — act as / pretend to be another agent or an AI role
    ("role_injection", re.compile(
        r"\b(?:act\s+as|pretend\s+(?:to\s+be|you(?:'re|\s+are)))\b.{0,30}?"
        r"\b(?:ai|assistant|chatbot|model|admin|administrator|developer|system|"
        r"dan|jailbroken|unrestricted|no\s+rules)\b", _F)),

    # 7. "new/updated/revised instructions:" — an instruction block handoff
    ("new_instructions", re.compile(
        r"\b(?:new|updated|revised)\s+(?:instruction|instructions|system\s+prompt)\b\s*:?", _F)),

    # 8. named jailbreaks / developer mode
    ("jailbreak_mode", re.compile(
        r"\b(?:developer\s+mode|jailbreak|jailbroken|dan\s+mode)\b", _F)),

    # 9. "do not follow the rules/instructions/policy"
    ("do_not_follow_rules", re.compile(
        r"\bdo\s+not\s+follow\b.{0,20}?"
        r"\b(?:instruction|instructions|rule|rules|guideline|guidelines|policy|policies)\b", _F)),
]


def scan_injection(user_claim: str) -> tuple[bool, str]:
    """Scan raw claim text for LLM-control injection.

    Returns (fired, excerpt). `excerpt` is the matched span (capped, inert) when
    fired, else "". First matching category wins.
    """
    if not isinstance(user_claim, str) or not user_claim:
        return False, ""
    for _name, pat in _PATTERNS:
        m = pat.search(user_claim)
        if m:
            return True, m.group(0).strip()[:EXCERPT_CAP]
    return False, ""
