"""Stage 3 evidence-keyer tests — repeatable, offline, reads the real CSV.

Validates:
- All 11 rules load,
- Cross-cutting rules (claim_object=all) always returned for any object,
- Object-specific rules keyed correctly,
- Issue-family fuzzy matching (dent/scratch → REQ_CAR_BODY_PANEL),
- Non-matching issue on a specific rule returns only cross-cutting rules.

Run from code/:  python -m unittest stage3.tests.test_evidence
"""
from __future__ import annotations

import os
import unittest

from stage3.evidence import load_evidence_requirements, EvidenceRequirements


def _get_evidence() -> EvidenceRequirements:
    """Load from the real CSV in the repo."""
    code_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dataset_dir = os.path.join(os.path.dirname(code_dir), "dataset")
    return load_evidence_requirements(dataset_dir)


class TestEvidenceLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ev = _get_evidence()

    def test_loads_11_rules(self):
        self.assertEqual(len(self.ev.rules), 11)

    def test_all_requirement_ids_unique(self):
        ids = [r.requirement_id for r in self.ev.rules]
        self.assertEqual(len(ids), len(set(ids)))


class TestCrossCuttingRules(unittest.TestCase):
    """claim_object=all rules must appear for any object + any issue."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ev = _get_evidence()
        cls.cross_cut_ids = {"REQ_GENERAL_OBJECT_PART", "REQ_GENERAL_MULTI_IMAGE",
                             "REQ_REVIEW_TRUST"}

    def _check_cross_cut(self, claim_object: str, issue: str) -> None:
        matches = self.ev.lookup(claim_object, issue)
        matched_ids = {m.requirement_id for m in matches}
        self.assertTrue(
            self.cross_cut_ids.issubset(matched_ids),
            f"Missing cross-cut for {claim_object}/{issue}: "
            f"expected {self.cross_cut_ids}, got {matched_ids}")

    def test_car_dent(self):
        self._check_cross_cut("car", "dent")

    def test_laptop_crack(self):
        self._check_cross_cut("laptop", "crack")

    def test_package_water_damage(self):
        self._check_cross_cut("package", "water_damage")

    def test_car_unknown(self):
        self._check_cross_cut("car", "unknown")


class TestObjectSpecificRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ev = _get_evidence()

    def test_car_dent_gets_body_panel_rule(self):
        matches = self.ev.lookup("car", "dent")
        ids = {m.requirement_id for m in matches}
        self.assertIn("REQ_CAR_BODY_PANEL", ids)

    def test_car_scratch_gets_body_panel_rule(self):
        matches = self.ev.lookup("car", "scratch")
        ids = {m.requirement_id for m in matches}
        self.assertIn("REQ_CAR_BODY_PANEL", ids)

    def test_car_crack_gets_glass_light_mirror(self):
        matches = self.ev.lookup("car", "crack")
        ids = {m.requirement_id for m in matches}
        self.assertIn("REQ_CAR_GLASS_LIGHT_MIRROR", ids)

    def test_car_broken_part_gets_glass_light_mirror(self):
        matches = self.ev.lookup("car", "broken_part")
        ids = {m.requirement_id for m in matches}
        self.assertIn("REQ_CAR_GLASS_LIGHT_MIRROR", ids)

    def test_laptop_crack_gets_screen_keyboard_trackpad(self):
        matches = self.ev.lookup("laptop", "crack")
        ids = {m.requirement_id for m in matches}
        self.assertIn("REQ_LAPTOP_SCREEN_KEYBOARD_TRACKPAD", ids)

    def test_laptop_broken_part_gets_body_hinge_port(self):
        matches = self.ev.lookup("laptop", "broken_part")
        ids = {m.requirement_id for m in matches}
        self.assertIn("REQ_LAPTOP_BODY_HINGE_PORT", ids)

    def test_package_crushed_gets_exterior(self):
        matches = self.ev.lookup("package", "crushed_packaging")
        ids = {m.requirement_id for m in matches}
        self.assertIn("REQ_PACKAGE_EXTERIOR", ids)

    def test_package_water_damage_gets_label_or_stain(self):
        matches = self.ev.lookup("package", "water_damage")
        ids = {m.requirement_id for m in matches}
        self.assertIn("REQ_PACKAGE_LABEL_OR_STAIN", ids)

    def test_package_missing_part_gets_contents(self):
        matches = self.ev.lookup("package", "missing_part")
        ids = {m.requirement_id for m in matches}
        self.assertIn("REQ_PACKAGE_CONTENTS", ids)


class TestNoFalsePositives(unittest.TestCase):
    """Object-specific rules from other objects must NOT appear."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ev = _get_evidence()

    def test_car_rule_not_on_laptop(self):
        matches = self.ev.lookup("laptop", "dent")
        ids = {m.requirement_id for m in matches}
        self.assertNotIn("REQ_CAR_BODY_PANEL", ids)

    def test_package_rule_not_on_car(self):
        matches = self.ev.lookup("car", "water_damage")
        ids = {m.requirement_id for m in matches}
        self.assertNotIn("REQ_PACKAGE_LABEL_OR_STAIN", ids)

    def test_laptop_rule_not_on_package(self):
        matches = self.ev.lookup("package", "crack")
        ids = {m.requirement_id for m in matches}
        self.assertNotIn("REQ_LAPTOP_SCREEN_KEYBOARD_TRACKPAD", ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
