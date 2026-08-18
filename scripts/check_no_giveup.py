#!/usr/bin/env python3
"""Guard the "a workflow never gives up" rule. Wired into `make test`.

A pyflow state ends one of three ways: `Continue`, `Done`, or `Await` — checkpoint at a
path, park until a human changes it, resume. There used to be a fourth, unwritten way: a
repair-budget exhaustion inside a bounded rework loop (a QA-plan repair, a code-fix lap,
an operator-consult cap) would give up and raise `WorkflowFailed`, ending the run. That
looked like a normal failure and read nothing like one: the story was left uncommitted,
the run was over, and nobody watching a `/loop` tick could tell the difference between
"this needs a human" and "this needs code fixed and the run restarted from scratch."

The fix was architectural, not a new mechanism: every budget exhaustion now escalates to
the *already-existing* operator gate (`Await`) instead, unconditionally, with no cap on
how many times a story can bounce back to it across resumes. This check cannot verify
that rule structurally — telling "a budget exhaustion that correctly escalates" from "a
budget exhaustion that doesn't" needs the control-flow graph, not a grep. What it *can*
do is stop the specific vocabulary of the old pattern from quietly coming back: the
fields, the record type, and the node that used to spell "give up" were deleted in the
migration, and a reintroduction under the same name is the cheapest possible sign the
pattern itself is back too.

This is a narrow guard, not a proof. It does not cover the resolver-authority half of the
rule (a diagnosis prompt must never decide or answer on the operator's behalf) — that
needs the control-flow graph, not a grep, same as everything else this check cannot see
structurally. `author/workflow.py`, `author/surveyor/flow.py`, `coder/dev/flow.py`,
`coder/review/flow.py`, `coder/docs/flow.py` and `coder/workflow.py` are migrated and
scanned; `docs/flow.py`'s one budget-exhaustion raise now blocks through the same
resolver its reviewer-convergence exhaustion already used, and `workflow.py`'s
`blocked_docs` and zero-diff-streak exhaustions now escalate through `_zero_diff_gate` and
`docs_operator` the same way `_ci_gate`/`_merge_gate` always did. The remaining
`WorkflowFailed` sites across all six files — including `give_up`'s `target_env="dev"`
report path and `_require_documented`'s `docs-not-passed` — guard inputs no repair lap can
fix, or a story path this migration does not own the ending of, not a budget.

Run:
    uv run python scripts/check_no_giveup.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Vocabulary of the deleted give-up pattern. Each one names something this migration
#: removed outright (a field, a class, a function) — not a word that could legitimately
#: reappear in unrelated prose, so a plain substring match is precise enough here, unlike
#: `check_public.py`'s name sweep, which has to worry about incidental false positives.
BANNED = (
    "giveup_reason",
    "operator_consulted",
    "QaGiveupRecord",
    "record_qa_giveup",
)

#: Where the migration actually landed. Widening this to `workflows/` as the deferred
#: sibling sites migrate is the point of listing them above.
SCANNED_ROOTS = (
    "workflows/src/workhorse_workflows/coder/qa",
    "workflows/src/workhorse_workflows/coder/workflow.py",
    "workflows/tests/coder/qa",
    "workflows/tests/coder/test_workflow.py",
    "workflows/src/workhorse_workflows/author/workflow.py",
    "workflows/src/workhorse_workflows/author/surveyor/flow.py",
    "workflows/tests/author/test_workflow.py",
    "workflows/tests/author/surveyor/test_flow.py",
    "workflows/src/workhorse_workflows/coder/dev/flow.py",
    "workflows/tests/coder/dev/test_flow.py",
    "workflows/src/workhorse_workflows/coder/review/flow.py",
    "workflows/tests/coder/review/test_flow.py",
    "workflows/src/workhorse_workflows/coder/docs/flow.py",
    "workflows/tests/coder/docs/test_flow.py",
)


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
