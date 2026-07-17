#!/usr/bin/env python3
"""Operator gate for the CI stage (coder).

An epic's PR could not be turned green by the bounded automated fix loop (or the
fix could not be pushed). Rather than dying in a permanent `fail` terminal — which
re-running could only fast-forward back into — we follow the same human-in-the-loop
pattern as the plan-stage ``await_operator``: surface the situation in a per-epic
``ci-operator-context.md`` and HALT (non-zero exit). The operator investigates
(fixes CI on the branch, grants the token write access, etc.), marks the file
``STATUS: ANSWERED``, and re-runs the workflow; auto-resume re-enters this node,
RESETS the CI fix counter to zero, and re-attempts the fix loop (await_ci) — so the
workflow "attempts to fix it again" instead of dying there.

State machine, read from the first ``STATUS:`` line in the context file (matched as
a whole line, so prose that merely mentions the words is ignored):
  AWAITING_OPERATOR -> still waiting; halt (exit 2), file untouched
  ANSWERED          -> operator acted; flip the line to CONSUMED, reset the CI fix
                       counter, proceed back into the gate (exit 0)
  CONSUMED          -> we already consumed an answer but CI is red AGAIN, so it
                       didn't resolve it: append the new summary, re-arm the line to
                       AWAITING_OPERATOR, and halt — avoids an infinite "answered"
                       loop on a stale answer
  (missing/unknown) -> ensure an AWAITING line exists, then halt

Args:
    argv[1]  epic        : the epic whose PR/branch is red (names the context file)
    argv[2]  ci_summary  : last CI failure summary (shown to the operator; optional)

Stdlib-only: scripts run under the system ``python3``, not the uv venv. On the
proceed path prints JSON (resets the per-epic CI fix budget so the re-attempt gets
a fresh loop allowance):
  {"operator_input": {"answered": true, "content": "<context.md>"},
   "ci_rework_count": {"value": 0}}
"""
import json
import logging
import os
import re
import sys
from pathlib import Path

AWAITING = "AWAITING_OPERATOR"
ANSWERED = "ANSWERED"
CONSUMED = "CONSUMED"

_STATUS_RE = re.compile(r"^STATUS:[ \t]*(\S+)", re.MULTILINE)

epic = sys.argv[1] if len(sys.argv) > 1 else ""
summary = (sys.argv[2].strip() if len(sys.argv) > 2 else "") or "No CI summary was captured."

# Scripts run from the workflow dir, not the repo. Resolve the repo root.
# The test harness sets the process CWD to the sandbox (via WORKHORSE_DEFAULT_SCRIPT_CWD
# → subprocess cwd arg), so if the CWD already has the expected docs/epics structure
# we use it directly — this keeps context files inside the sandbox.
# Production runs have an arbitrary CWD, so we fall back to walking up from __file__.
def _find_repo_root() -> Path:
    # Workflows run from the shared library, so the makefile-pinned AGENT_REPO_DIR is
    # the only reliable anchor to the starting repo; CWD/__file__ both point into the
    # library. The CWD probe below remains as a test-harness fallback.
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    cwd = Path.cwd()
    # Prefer CWD when it looks like a project root (has docs/epics, agents.yml, or .git)
    if (cwd / "docs" / "epics").is_dir() or (cwd / "agents.yml").exists() or (cwd / ".git").exists():
        return cwd
    for candidate in cwd.parents:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    # Fall back to __file__-based resolution
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return cwd

root = _find_repo_root()

# Per-epic so two epics' CI escalations don't clobber each other. Prefer the epic's
# docs folder when it exists (discoverable next to the epic), else the repo root.
br = f"feat/{epic}" if epic else "the epic branch"
epic_docs = root / "docs" / "epics" / epic if epic else None
if epic_docs is not None and epic_docs.is_dir():
    ctx = epic_docs / "ci-operator-context.md"
elif epic:
    ctx = root / f"ci-operator-context.{epic}.md"
else:
    ctx = root / "ci-operator-context.md"


def status_of(text: str) -> str:
    m = _STATUS_RE.search(text)
    return m.group(1).upper() if m else ""


def set_status(text: str, new: str) -> str:
    return _STATUS_RE.sub(f"STATUS: {new}", text, count=1)


def banner() -> None:
    print(
        "\n".join([
            "============================================================",
            "⛔ CI FAILED — operator input required (expected, NOT a crash).",
            f"The PR for epic '{epic}' (branch {br}) is still red after the",
            "automated fix loop exhausted its attempts (or the fix could not be",
            "pushed). The run paused and will resume when you act.",
            f"    {ctx}",
            f"Fix CI on {br} (and/or grant the GitHub token Contents:Write), set the",
            f"'STATUS: {AWAITING}' line to 'STATUS: {ANSWERED}', then re-run the",
            "workflow to re-attempt the fix loop from a fresh attempt budget.",
            "============================================================",
        ]),
        file=sys.stderr,
    )


def fresh_body() -> str:
    return (
        "# CI Operator Context — action required\n\n"
        f"STATUS: {AWAITING}\n\n"
        f"The coder run paused because CI for `{br}` is red and the automated\n"
        "fix loop could not turn it green (or could not push its fix). Resolve the\n"
        "failure below, change the STATUS line above to\n"
        f"`STATUS: {ANSWERED}`, then re-run the workflow. On resume the CI fix\n"
        "counter is reset and the fix loop runs again.\n\n"
        f"## Last CI summary\n\n{summary}\n\n"
        "## Notes\n\n<!-- what you changed / what to watch -->\n"
    )


def halt(exit_code: int = 2) -> None:
    banner()
    sys.exit(exit_code)


def main(logger: logging.Logger) -> None:
    # `epic`, `summary`, `root`, `br`, `epic_docs`, and `ctx` are computed at module
    # scope (above) because banner()/fresh_body()/halt() close over them as globals;
    # moving that setup in here would leave those helpers with no `ctx`/`epic`/etc.
    # to reference. Only the state-machine logic itself is wrapped.
    if not ctx.exists():
        ctx.parent.mkdir(parents=True, exist_ok=True)
        ctx.write_text(fresh_body())
        logger.info("wrote %s", ctx)
        halt()

    current = ctx.read_text()
    state = status_of(current)

    if state == ANSWERED:
        # Consume the answer: flip to CONSUMED so a later re-block re-arms instead of
        # looping forever on the same stale answer. Reset the CI fix budget so the
        # re-attempt gets a fresh loop allowance.
        ctx.write_text(set_status(current, CONSUMED))
        logger.info("operator answered for epic %s — resetting CI fix budget", epic)
        print(json.dumps({
            "operator_input": {"answered": True, "content": current},
            "ci_rework_count": {"value": 0},
        }))
        sys.exit(0)

    if state == AWAITING:
        logger.info("%s still %s — not answered yet", ctx, AWAITING)
        halt()

    if state == CONSUMED:
        # We already consumed an answer but CI is red AGAIN — it didn't resolve it.
        # Re-arm and append the new summary so the operator sees the renewed ask.
        rearmed = set_status(current, AWAITING) + (
            "\n\n## Still red after your last action\n\n"
            f"{summary}\n\n## Notes (follow-up)\n\n<!-- write here -->\n"
        )
        ctx.write_text(rearmed)
        logger.warning("re-blocked after a consumed answer — re-armed %s", ctx)
        halt()

    # No recognizable STATUS line — ensure one exists so the operator has a marker to
    # flip, then halt without clobbering whatever they may have written.
    logger.warning("%s has no STATUS line — adding one and waiting", ctx)
    ctx.write_text(f"STATUS: {AWAITING}\n\n" + current)
    halt()


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("await-ci-operator"))
