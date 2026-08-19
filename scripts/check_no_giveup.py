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
rule (a resolver may *apply* a decision somebody already wrote down and must escalate
every question nobody has answered yet — see `coder/shared/resolution.py`) — that needs
the control-flow graph, not a grep, same as everything else this check cannot see
structurally. The scan is now the whole `workflows/` package rather than the handful of
migrated files it started as: every lane flow routes a blocked verdict to the operator
gate, `workflow.py`'s docs exhaustions escalate through `docs_operator` the way
`_ci_gate`/`_merge_gate` always did, and the zero-diff streak counter that used to end a
run for "no progress" is deleted rather than migrated — so a reintroduction anywhere in
the package is a regression, not an unmigrated sibling.

The remaining `WorkflowFailed` sites guard inputs no repair lap can fix — or, in
`give_up`'s `target_env="dev"` report path, a story path this migration does not own the
ending of. They are not budgets.

Run:
    uv run python scripts/check_no_giveup.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Vocabulary of the deleted give-up pattern. Each one names something this migration
#: removed outright (a field, a class, a function, a `failure_class` string) — not a word
#: that could legitimately reappear in unrelated prose, so a plain substring match is
#: precise enough here, unlike `check_public.py`'s name sweep, which has to worry about
#: incidental false positives.
BANNED = (
    "giveup_reason",
    "operator_consulted",
    "QaGiveupRecord",
    "record_qa_giveup",
    # The two `failure_class` strings a run used to die under. The first was raised when a
    # `Docs` handoff came back anything but passing, which is now an `Await` on the same
    # gate a `blocked` verdict takes; the second counted consecutive stories that committed
    # nothing, and went when the workflow stopped committing on the agent's behalf.
    "docs-not-passed",
    "zero-diff-streak",
)

#: The whole package. It started as the list of files the migration had reached, and the
#: point of the list was always to stop needing it.
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
