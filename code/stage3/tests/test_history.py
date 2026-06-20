"""Stage 3 user-history loader tests — repeatable, offline, reads the real CSV.

Validates:
- All 48 users load (47 distinct user_ids, user_001–user_047),
- history_flags parsed correctly (semicolon-split, "none" filtered out),
- Known risky users have the right flags,
- Clean users have empty flags,
- Missing user returns graceful default (empty flags, empty summary, no error),
- history_summary populated.

Run from code/:  python -m unittest stage3.tests.test_history
"""
from __future__ import annotations

import os
import unittest

from stage3.history import load_user_history, UserHistoryLookup


def _get_history() -> UserHistoryLookup:
    """Load from the real CSV in the repo."""
    code_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    dataset_dir = os.path.join(os.path.dirname(code_dir), "dataset")
    return load_user_history(dataset_dir)


class TestHistoryLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.hist = _get_history()

    def test_loads_47_users(self):
        self.assertEqual(len(self.hist.user_ids), 47)

    def test_user_001_clean(self):
        h = self.hist.get("user_001")
        self.assertEqual(h.user_id, "user_001")
        self.assertEqual(h.history_flags, [])
        self.assertEqual(h.past_claim_count, 2)
        self.assertIn("Low-risk", h.history_summary)

    def test_user_005_has_user_history_risk(self):
        h = self.hist.get("user_005")
        self.assertIn("user_history_risk", h.history_flags)
        self.assertNotIn("manual_review_required", h.history_flags)

    def test_user_013_has_both_flags(self):
        h = self.hist.get("user_013")
        self.assertIn("user_history_risk", h.history_flags)
        self.assertIn("manual_review_required", h.history_flags)

    def test_user_032_has_manual_review_only(self):
        h = self.hist.get("user_032")
        self.assertIn("manual_review_required", h.history_flags)
        self.assertNotIn("user_history_risk", h.history_flags)


class TestGracefulMissingUser(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.hist = _get_history()

    def test_missing_user_returns_default(self):
        h = self.hist.get("user_999")
        self.assertEqual(h.user_id, "user_999")
        self.assertEqual(h.history_flags, [])
        self.assertEqual(h.history_summary, "")
        self.assertEqual(h.past_claim_count, 0)

    def test_missing_user_no_error(self):
        # Should not raise
        h = self.hist.get("completely_unknown_user")
        self.assertIsNotNone(h)

    def test_missing_user_different_from_real_user(self):
        real = self.hist.get("user_005")
        fake = self.hist.get("user_999")
        self.assertNotEqual(real.history_flags, fake.history_flags)


class TestHistoryCounts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.hist = _get_history()

    def test_user_037_high_counts(self):
        h = self.hist.get("user_037")
        self.assertEqual(h.past_claim_count, 14)
        self.assertEqual(h.rejected_claim, 6)
        self.assertEqual(h.last_90_days_claim_count, 9)

    def test_user_006_new_user(self):
        h = self.hist.get("user_006")
        self.assertEqual(h.past_claim_count, 0)
        self.assertEqual(h.accept_claim, 0)
        self.assertEqual(h.rejected_claim, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
