#!/usr/bin/env python3
"""Guard the "a workflow never gives up" rule."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

BANNED = (
    "giveup_reason",
    "operator_consulted",
    "QaGiveupRecord",
    "record_qa_giveup",
    "docs-not-passed",
    "zero-diff-streak",
    "MAX_ZERO_DIFF_COMMITS",
    "_zero_diff_gate",
    "zero_diff=",
)

SCANNED_ROOTS = ("workflows/",)


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", *SCANNED_ROOTS],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO / p for p in out.split("\0") if p]


def check_no_giveup() -> list[str]:
    offenders: list[str] = []
    scanned = 0
    for path in sorted(_tracked_files()):
        if not path.is_file():
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(REPO).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            for name in BANNED:
                if name in line:
                    offenders.append(f"{rel}:{lineno}: {name}")
    if not offenders:
        print(f"ok: no give-up vocabulary in {scanned} files under {', '.join(SCANNED_ROOTS)}")
    return offenders


def main() -> int:
    problems = check_no_giveup()
    if not problems:
        return 0
    print("\nFAIL check_no_giveup:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(
        "\nA workflow does not give up, it blocks: route a repair-budget exhaustion to "
        "the operator gate (Await), not a terminal WorkflowFailed. If this name is back, "
        "the give-up pattern it belonged to probably is too.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
