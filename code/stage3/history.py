"""User-history loader.

Reads ``dataset/user_history.csv`` (48 users, 8 columns), keyed on
``user_id``. Exposes a lookup returning parsed ``history_flags`` and
``history_summary``. Missing user → graceful default: no flags, empty summary,
no error.

Lookup only — no risk-flag emission (that belongs to the resolver in Phase 2).
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field

# The exact token set that appears in history_flags (from grounding).
HISTORY_FLAG_TOKENS: frozenset[str] = frozenset({
    "none",
    "user_history_risk",
    "manual_review_required",
})


@dataclass(frozen=True)
class UserHistory:
    """Parsed history for one user."""
    user_id: str
    past_claim_count: int
    accept_claim: int
    manual_review_claim: int
    rejected_claim: int
    last_90_days_claim_count: int
    history_flags: list[str]     # parsed from ;-separated, "none" filtered out
    history_summary: str


# Default for missing users — new user, no history, no risk.
_DEFAULT_HISTORY = UserHistory(
    user_id="",
    past_claim_count=0,
    accept_claim=0,
    manual_review_claim=0,
    rejected_claim=0,
    last_90_days_claim_count=0,
    history_flags=[],
    history_summary="",
)


class UserHistoryLookup:
    """Loader + keyed lookup for user_history.csv."""

    def __init__(self, csv_path: str) -> None:
        self._users: dict[str, UserHistory] = {}
        self._load(csv_path)

    def _load(self, csv_path: str) -> None:
        with open(csv_path, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                uid = row["user_id"].strip()

                # Parse history_flags: semicolon-separated, drop "none" and
                # unrecognised tokens.
                raw_flags = row.get("history_flags", "none").strip()
                flags: list[str] = []
                for tok in raw_flags.split(";"):
                    tok = tok.strip()
                    if tok and tok != "none" and tok in HISTORY_FLAG_TOKENS:
                        if tok not in flags:
                            flags.append(tok)

                self._users[uid] = UserHistory(
                    user_id=uid,
                    past_claim_count=int(row.get("past_claim_count", 0)),
                    accept_claim=int(row.get("accept_claim", 0)),
                    manual_review_claim=int(row.get("manual_review_claim", 0)),
                    rejected_claim=int(row.get("rejected_claim", 0)),
                    last_90_days_claim_count=int(row.get("last_90_days_claim_count", 0)),
                    history_flags=flags,
                    history_summary=row.get("history_summary", "").strip(),
                )

    def get(self, user_id: str) -> UserHistory:
        """Look up a user. Missing → graceful default (new user)."""
        if user_id in self._users:
            return self._users[user_id]
        # Return a copy with the requested user_id filled in.
        return UserHistory(
            user_id=user_id,
            past_claim_count=_DEFAULT_HISTORY.past_claim_count,
            accept_claim=_DEFAULT_HISTORY.accept_claim,
            manual_review_claim=_DEFAULT_HISTORY.manual_review_claim,
            rejected_claim=_DEFAULT_HISTORY.rejected_claim,
            last_90_days_claim_count=_DEFAULT_HISTORY.last_90_days_claim_count,
            history_flags=list(_DEFAULT_HISTORY.history_flags),
            history_summary=_DEFAULT_HISTORY.history_summary,
        )

    @property
    def user_ids(self) -> set[str]:
        """All known user IDs."""
        return set(self._users.keys())


def load_user_history(dataset_dir: str | None = None) -> UserHistoryLookup:
    """Convenience loader: resolves the default CSV path from the repo root."""
    if dataset_dir is None:
        code_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dataset_dir = os.path.join(os.path.dirname(code_dir), "dataset")
    csv_path = os.path.join(dataset_dir, "user_history.csv")
    return UserHistoryLookup(csv_path)
