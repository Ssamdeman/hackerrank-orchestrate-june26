"""Stage 2 floor tests — repeatable, offline, no API key, no model call.

Locks the validate/repair discipline before any extraction is wired:
- enum repair to unknown (and confidence -> low),
- object-conditioned part rejection (a part legal for one object is illegal for
  another),
- the non-string text-field guard (the dict-in-text-field bug),
- claimed_issue_type 'none' -> unknown (a claim never asserts no-damage),
- injection_detected malformed -> True (never silence a possible injection),
- cap enforcement on the two text fields.

Run from code/:  python -m unittest stage2.tests.test_stage2
"""
from __future__ import annotations

import unittest

from stage2 import schema as s


def valid_raw(**overrides):
    raw = {
        "claimed_part": "door",
        "additional_claimed_parts": [],
        "claimed_issue_type": "dent",
        "claimed_severity": "low",
        "claim_summary": "Customer reports a dent on the car door.",
        "confidence": "high",
        "injection_detected": False,
        "injection_excerpt": "",
    }
    raw.update(overrides)
    return raw


class TestEnumRepair(unittest.TestCase):
    def test_out_of_vocab_to_unknown(self):
        repairs = []
        rec = s.coerce_claim(valid_raw(
            claimed_issue_type="exploded",   # not an issue -> unknown
            claimed_severity="apocalyptic",  # not a severity -> unknown
            confidence="pretty sure",        # -> low (fail closed)
        ), user_id="u1", claim_object="car", on_repair=repairs.append)
        self.assertEqual(rec.claimed_issue_type, "unknown")
        self.assertEqual(rec.claimed_severity, "unknown")
        self.assertEqual(rec.confidence, "low")
        self.assertEqual(len(repairs), 3)

    def test_valid_record_needs_no_repair(self):
        repairs = []
        rec = s.coerce_claim(valid_raw(), user_id="u1", claim_object="car",
                            on_repair=repairs.append)
        self.assertEqual(repairs, [])
        self.assertEqual(rec.claimed_part, "door")
        self.assertEqual(rec.confidence, "high")
        self.assertIs(rec.injection_detected, False)

    def test_issue_none_repaired_to_unknown(self):
        # 'none' is a vision finding ("no damage present") — illegal for a claim.
        repairs = []
        rec = s.coerce_claim(valid_raw(claimed_issue_type="none"),
                            user_id="u1", claim_object="car", on_repair=repairs.append)
        self.assertEqual(rec.claimed_issue_type, "unknown")
        self.assertEqual(len(repairs), 1)


class TestObjectConditionedParts(unittest.TestCase):
    def test_laptop_part_on_car_claim_rejected(self):
        # 'keyboard' is a laptop part; on a car claim it must be repaired.
        rec = s.coerce_claim(valid_raw(claimed_part="keyboard"),
                            user_id="u1", claim_object="car")
        self.assertEqual(rec.claimed_part, "unknown")

    def test_car_part_on_laptop_claim_rejected(self):
        rec = s.coerce_claim(valid_raw(claimed_part="windshield"),
                            user_id="u1", claim_object="laptop")
        self.assertEqual(rec.claimed_part, "unknown")

    def test_legal_part_accepted(self):
        rec = s.coerce_claim(valid_raw(claimed_part="seal"),
                            user_id="u1", claim_object="package")
        self.assertEqual(rec.claimed_part, "seal")

    def test_additional_parts_filtered_by_object(self):
        rec = s.coerce_claim(valid_raw(
            claimed_part="front_bumper",
            additional_claimed_parts=["headlight", "keyboard", "front_bumper", "door"],
        ), user_id="u1", claim_object="car")
        # keyboard dropped (laptop part); front_bumper dropped (== primary);
        # headlight and door kept, order preserved.
        self.assertEqual(rec.additional_claimed_parts, ["headlight", "door"])


class TestTextFieldGuards(unittest.TestCase):
    def test_dict_in_text_field_fails_closed(self):
        repairs = []
        rec = s.coerce_claim(valid_raw(
            claim_summary={"type": "string"},      # not a string -> ""
            injection_excerpt={"type": "string"},  # not a string -> ""
        ), user_id="u1", claim_object="car", on_repair=repairs.append)
        self.assertEqual(rec.claim_summary, "")
        self.assertEqual(rec.injection_excerpt, "")
        self.assertEqual(len(repairs), 2)

    def test_caps_enforced(self):
        rec = s.coerce_claim(valid_raw(
            claim_summary="x" * 500,
            injection_excerpt="y" * 500,
        ), user_id="u1", claim_object="car")
        self.assertEqual(len(rec.claim_summary), s.CLAIM_SUMMARY_CAP)
        self.assertEqual(len(rec.injection_excerpt), s.INJECTION_EXCERPT_CAP)


class TestInjectionFlagFailsOpen(unittest.TestCase):
    def test_malformed_flag_becomes_true(self):
        repairs = []
        rec = s.coerce_claim(valid_raw(injection_detected="yes"),  # non-bool
                            user_id="u1", claim_object="car", on_repair=repairs.append)
        self.assertIs(rec.injection_detected, True)
        self.assertEqual(len(repairs), 1)

    def test_none_flag_becomes_true(self):
        rec = s.coerce_claim(valid_raw(injection_detected=None),
                            user_id="u1", claim_object="car")
        self.assertIs(rec.injection_detected, True)

    def test_real_true_preserved(self):
        rec = s.coerce_claim(valid_raw(injection_detected=True),
                            user_id="u1", claim_object="car")
        self.assertIs(rec.injection_detected, True)


class TestVocabIsShared(unittest.TestCase):
    def test_stage2_imports_same_objects_as_vocab(self):
        # Stage 2 must not redefine the contract — it must BE the same objects.
        import vocab
        self.assertIs(s.OBJECT_PARTS, vocab.OBJECT_PARTS)
        self.assertIs(s.ISSUE_TYPES, vocab.ISSUE_TYPES)
        self.assertIs(s.SEVERITIES, vocab.SEVERITIES)
        self.assertIs(s.CONFIDENCES, vocab.CONFIDENCES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
