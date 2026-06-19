"""Mandatory append-only dev log (AGENTS.md §2/§5, CLAUDE.md constraints).

Every agent, sub-agent, and worktree writes to the SAME file in the user's home
directory (it survives branch switches and git clean). Append-only: never
rewrite, reorder, or delete prior entries. Secrets are redacted before writing.
UTF-8, LF line endings even on Windows.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path


def log_path() -> Path:
    return Path.home() / "hackerrank_orchestrate" / "log.txt"


# Redact anything that looks like a key/token before it can reach the file.
_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|sk-ant-[A-Za-z0-9_\-]{8,}|"
    r"(?i:api[_-]?key|token|secret|password)\s*[=:]\s*\S+)"
)


def redact(text: str) -> str:
    return _SECRET_RE.sub("[REDACTED]", text)


def append(title: str, body: str) -> None:
    """Append one timestamped entry. Creates the parent dir if missing."""
    p = log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    entry = f"\n## [{ts}] {redact(title)}\n\n{redact(body)}\n"
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write(entry)
