"""Stage 3 schema tests — repeatable, offline, no API key, no model call.

Locks the Verdict validation floor and CSV serialisation contract:
- enum repair to fail-closed defaults,
- object-conditioned part rejection,
- risk_flags vocabulary filtering + dedup + "none" sentinel,
- supporting_image_ids list handling + "none" sentinel,
- boolean coercion,
- text-field caps,
- to_csv_row() column ordering + ;-join + none sentinels,
- vocab.py identity (same objects, not copies).

Run from code/:  python -m unittest stage3.tests.test_schema
"""
from __future__ import annotations

import unittest

from stage3 import schema as s


def valid_raw(**overrides: object) -> dict:
    """Minimal valid Verdict dict for a car claim."""
    raw: dict = {
        "user_id": "user_001",
        "image_paths": "images/test/case_001/img_1.jpg",
        "user_claim": "The rear bumper has a dent.",
        "claim_object": "car",
        "evidence_standard_met": True,
        "evidence_standard_met_reason": "The rear bumper is visible.",
        "risk_flags": [],
        "issue_type": "dent",
        "object_part": "rear_bumper",
        "claim_status": "supported",
        "claim_status_justification": "The image shows a dent on the rear bumper.",
        "supporting_image_ids": ["img_1"],
        "valid_image": True,
        "severity": "medium",
    }
    raw.update(overrides)
    return raw


class TestEnumRepair(unittest.TestCase):
    def test_out_of_vocab_to_defaults(self):
        repairs: list[str] = []
        v = s.coerce_verdict(valid_raw(
            issue_type="exploded",
            severity="apocalyptic",
            claim_status="maybe",
        ), on_repair=repairs.append)
        self.assertEqual(v.issue_type, "unknown")
        self.assertEqual(v.severity, "unknown")
        self.assertEqual(v.claim_status, "not_enough_information")
        self.assertEqual(len(repairs), 3)

    def test_valid_record_needs_no_repair(self):
        repairs: list[str] = []
        v = s.coerce_verdict(valid_raw(), on_repair=repairs.append)
        self.assertEqual(repairs, [])
        self.assertEqual(v.issue_type, "dent")
        self.assertEqual(v.claim_status, "supported")

    def test_issue_type_none_is_legal(self):
        # Unlike Stage 2, the output CAN have issue_type=none (part visible, no damage).
        v = s.coerce_verdict(valid_raw(issue_type="none"))
        self.assertEqual(v.issue_type, "none")


class TestObjectConditionedParts(unittest.TestCase):
    def test_laptop_part_on_car_claim_rejected(self):
        v = s.coerce_verdict(valid_raw(object_part="keyboard"))
        self.assertEqual(v.object_part, "unknown")

    def test_car_part_on_laptop_claim_rejected(self):
        v = s.coerce_verdict(valid_raw(claim_object="laptop", object_part="windshield"))
        self.assertEqual(v.object_part, "unknown")

    def test_legal_part_accepted(self):
        v = s.coerce_verdict(valid_raw(claim_object="package", object_part="seal"))
        self.assertEqual(v.object_part, "seal")


class TestRiskFlags(unittest.TestCase):
    def test_valid_flags_preserved(self):
        v = s.coerce_verdict(valid_raw(
            risk_flags=["blurry_image", "user_history_risk"]))
        self.assertEqual(v.risk_flags, ["blurry_image", "user_history_risk"])

    def test_invalid_flag_dropped(self):
        repairs: list[str] = []
        v = s.coerce_verdict(valid_raw(
            risk_flags=["blurry_image", "totally_fake_flag"]),
            on_repair=repairs.append)
        self.assertEqual(v.risk_flags, ["blurry_image"])
        self.assertTrue(any("totally_fake_flag" in r for r in repairs))

    def test_none_token_dropped(self):
        v = s.coerce_verdict(valid_raw(risk_flags=["none"]))
        self.assertEqual(v.risk_flags, [])

    def test_deduplication(self):
        v = s.coerce_verdict(valid_raw(
            risk_flags=["blurry_image", "blurry_image"]))
        self.assertEqual(v.risk_flags, ["blurry_image"])

    def test_non_list_repaired(self):
        repairs: list[str] = []
        v = s.coerce_verdict(valid_raw(risk_flags="blurry_image"),
                             on_repair=repairs.append)
        self.assertEqual(v.risk_flags, [])
        self.assertTrue(len(repairs) >= 1)


class TestSupportingImageIds(unittest.TestCase):
    def test_valid_ids_preserved(self):
        v = s.coerce_verdict(valid_raw(supporting_image_ids=["img_1", "img_2"]))
        self.assertEqual(v.supporting_image_ids, ["img_1", "img_2"])

    def test_deduplication(self):
        v = s.coerce_verdict(valid_raw(supporting_image_ids=["img_1", "img_1"]))
        self.assertEqual(v.supporting_image_ids, ["img_1"])

    def test_none_string_dropped(self):
        v = s.coerce_verdict(valid_raw(supporting_image_ids=["none"]))
        self.assertEqual(v.supporting_image_ids, [])

    def test_non_list_repaired(self):
        v = s.coerce_verdict(valid_raw(supporting_image_ids="img_1"))
        self.assertEqual(v.supporting_image_ids, [])


class TestBooleanCoercion(unittest.TestCase):
    def test_non_bool_evidence_standard_met(self):
        repairs: list[str] = []
        v = s.coerce_verdict(valid_raw(evidence_standard_met="yes"),
                             on_repair=repairs.append)
        self.assertIs(v.evidence_standard_met, False)

    def test_non_bool_valid_image(self):
        v = s.coerce_verdict(valid_raw(valid_image=1))
        self.assertIs(v.valid_image, False)

    def test_true_preserved(self):
        v = s.coerce_verdict(valid_raw(valid_image=True))
        self.assertIs(v.valid_image, True)


class TestTextFieldCaps(unittest.TestCase):
    def test_reason_capped(self):
        v = s.coerce_verdict(valid_raw(
            evidence_standard_met_reason="x" * 500))
        self.assertLessEqual(len(v.evidence_standard_met_reason), s.REASON_CAP)

    def test_justification_capped(self):
        v = s.coerce_verdict(valid_raw(
            claim_status_justification="y" * 500))
        self.assertLessEqual(len(v.claim_status_justification), s.JUSTIFICATION_CAP)

    def test_dict_in_text_field(self):
        repairs: list[str] = []
        v = s.coerce_verdict(valid_raw(
            evidence_standard_met_reason={"type": "string"}),
            on_repair=repairs.append)
        self.assertEqual(v.evidence_standard_met_reason, "")


class TestToCsvRow(unittest.TestCase):
    def test_column_order(self):
        v = s.coerce_verdict(valid_raw())
        row = v.to_csv_row()
        self.assertEqual(tuple(row.keys()), s.OUTPUT_COLUMNS)

    def test_booleans_serialized(self):
        v = s.coerce_verdict(valid_raw(
            evidence_standard_met=True, valid_image=False))
        row = v.to_csv_row()
        self.assertEqual(row["evidence_standard_met"], "true")
        self.assertEqual(row["valid_image"], "false")

    def test_risk_flags_joined(self):
        v = s.coerce_verdict(valid_raw(
            risk_flags=["blurry_image", "user_history_risk"]))
        row = v.to_csv_row()
        self.assertEqual(row["risk_flags"], "blurry_image;user_history_risk")

    def test_risk_flags_empty_is_none(self):
        v = s.coerce_verdict(valid_raw(risk_flags=[]))
        row = v.to_csv_row()
        self.assertEqual(row["risk_flags"], "none")

    def test_supporting_ids_joined(self):
        v = s.coerce_verdict(valid_raw(
            supporting_image_ids=["img_1", "img_2"]))
        row = v.to_csv_row()
        self.assertEqual(row["supporting_image_ids"], "img_1;img_2")

    def test_supporting_ids_empty_is_none(self):
        v = s.coerce_verdict(valid_raw(supporting_image_ids=[]))
        row = v.to_csv_row()
        self.assertEqual(row["supporting_image_ids"], "none")

    def test_all_14_columns_present(self):
        v = s.coerce_verdict(valid_raw())
        row = v.to_csv_row()
        self.assertEqual(len(row), 14)
        for col in s.OUTPUT_COLUMNS:
            self.assertIn(col, row)


class TestVocabIsShared(unittest.TestCase):
    def test_stage3_imports_same_objects_as_vocab(self):
        """Stage 3 must not redefine the contract — it must BE the same objects."""
        import vocab
        self.assertIs(s.ISSUE_TYPES, vocab.ISSUE_TYPES)
        self.assertIs(s.OBJECT_PARTS, vocab.OBJECT_PARTS)
        self.assertIs(s.SEVERITIES, vocab.SEVERITIES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
