#!/usr/bin/env python3
"""Operator gate for the MERGE stage (coder).

An epic's PR could not be merged by the bounded automated conflict-resolution loop
(merge conflict, branch behind base, branch protection, required reviews, or
required CI checks that never ran). Rather than finishing on an unmerged PR — which
the old `merge_final -> done` edge did silently — we follow the same human-in-the-
loop pattern as await_ci_operator: surface the situation in a per-epic
``merge-operator-context.md`` and HALT (non-zero exit). The operator resolves it
(merges by hand, updates the branch, relaxes branch protection, …), marks the file
``STATUS: ANSWERED``, and re-runs the workflow; auto-resume re-enters this node,
RESETS the merge conflict-resolution counter, and re-attempts the merge.

State machine, read from the first ``STATUS:`` line in the context file (matched as
a whole line, so prose that merely mentions the words is ignored):
  AWAITING_OPERATOR -> still waiting; halt (exit 2), file untouched
  ANSWERED          -> operator acted; flip the line to CONSUMED, reset the merge
                       counter, proceed back into the gate (exit 0)
  CONSUMED          -> we already consumed an answer but the merge failed AGAIN, so
                       it didn't resolve it: re-arm to AWAITING_OPERATOR and halt —
                       avoids an infinite "answered" loop on a stale answer
  (missing/unknown) -> ensure an AWAITING line exists, then halt

Args:
    argv[1]  epic  : the epic whose PR could not merge (names the context file)
    argv[2]  base  : the PR base branch (shown to the operator; optional)

Stdlib-only: scripts run under the system ``python3``, not the uv venv. On the
proceed path prints JSON (resets the per-epic merge budget so the re-attempt gets a
fresh loop allowance):
  {"operator_input": {"answered": true, "content": "<context.md>"},
   "merge_rework_count": {"value": 0}}
"""
import json
import os
import re
import sys
from pathlib import Path

AWAITING = "AWAITING_OPERATOR"
ANSWERED = "ANSWERED"
CONSUMED = "CONSUMED"

_STATUS_RE = re.compile(r"^STATUS:[ \t]*(\S+)", re.MULTILINE)

epic = sys.argv[1] if len(sys.argv) > 1 else ""
base = (sys.argv[2].strip() if len(sys.argv) > 2 else "") or "the base branch"


def _find_repo_root() -> Path:
    # Workflows run from the shared library, so the makefile-pinned AGENT_REPO_DIR is
    # the only reliable anchor to the starting repo; CWD/__file__ both point into the
    # library. The CWD probe below remains as a test-harness fallback.
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    cwd = Path.cwd()
    if (cwd / "docs" / "epics").is_dir() or (cwd / "agents.yml").exists() or (cwd / ".git").exists():
        return cwd
    for candidate in cwd.parents:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return cwd


root = _find_repo_root()

br = f"feat/{epic}" if epic else "the epic branch"
epic_docs = root / "docs" / "epics" / epic if epic else None
if epic_docs is not None and epic_docs.is_dir():
    ctx = epic_docs / "merge-operator-context.md"
elif epic:
    ctx = root / f"merge-operator-context.{epic}.md"
else:
    ctx = root / "merge-operator-context.md"


def status_of(text: str) -> str:
    m = _STATUS_RE.search(text)
    return m.group(1).upper() if m else ""


def set_status(text: str, new: str) -> str:
    return _STATUS_RE.sub(f"STATUS: {new}", text, count=1)


def banner() -> None:
    print(
        "\n".join([
            "============================================================",
            "⛔ MERGE FAILED — operator input required (expected, NOT a crash).",
            f"The PR for epic '{epic}' (branch {br} → {base}) could not be merged",
            "after the automated conflict-resolution loop exhausted its attempts.",
            "The run paused and will resume when you act.",
            f"    {ctx}",
            f"Resolve the merge on {br} (rebase/merge {base}, clear branch",
            "protection / required checks, or merge by hand), set the",
            f"'STATUS: {AWAITING}' line to 'STATUS: {ANSWERED}', then re-run the",
            "workflow to re-attempt the merge from a fresh attempt budget.",
            "============================================================",
        ]),
        file=sys.stderr,
    )


def fresh_body() -> str:
    return (
        "# Merge Operator Context — action required\n\n"
        f"STATUS: {AWAITING}\n\n"
        f"The coder run paused because the PR for `{br}` (→ `{base}`) could not be\n"
        "merged and the automated conflict-resolution loop could not resolve it.\n"
        "Common causes: a merge conflict the agent couldn't safely resolve, the\n"
        "branch being behind base under a 'require up to date' rule, required PR\n"
        "reviews, or required CI checks that never ran. Resolve it, change the\n"
        f"STATUS line above to `STATUS: {ANSWERED}`, then re-run the workflow. On\n"
        "resume the merge counter is reset and the merge is re-attempted.\n\n"
        "## Notes\n\n<!-- what you changed / what to watch -->\n"
    )


def halt(exit_code: int = 2) -> None:
    banner()
    sys.exit(exit_code)


if not ctx.exists():
    ctx.parent.mkdir(parents=True, exist_ok=True)
    ctx.write_text(fresh_body())
    print(f"[await-merge-operator] wrote {ctx}", file=sys.stderr)
    halt()

current = ctx.read_text()
state = status_of(current)

if state == ANSWERED:
    ctx.write_text(set_status(current, CONSUMED))
    print(json.dumps({
        "operator_input": {"answered": True, "content": current},
        "merge_rework_count": {"value": 0},
    }))
    sys.exit(0)

if state == AWAITING:
    print(f"[await-merge-operator] {ctx} still {AWAITING} — not answered yet", file=sys.stderr)
    halt()

if state == CONSUMED:
    rearmed = set_status(current, AWAITING) + (
        "\n\n## Still unmerged after your last action\n\n"
        "## Notes (follow-up)\n\n<!-- write here -->\n"
    )
    ctx.write_text(rearmed)
    print(f"[await-merge-operator] re-blocked after a consumed answer — re-armed {ctx}", file=sys.stderr)
    halt()

print(f"[await-merge-operator] {ctx} has no STATUS line — adding one and waiting", file=sys.stderr)
ctx.write_text(f"STATUS: {AWAITING}\n\n" + current)
halt()
