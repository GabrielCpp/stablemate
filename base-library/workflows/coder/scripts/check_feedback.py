#!/usr/bin/env python3
"""Non-blocking operator-feedback poll for the coder/author workflows.

Unlike ``await_operator.py`` (which HALTS the run until a human answers an
agent-raised block), this node NEVER halts and NEVER asks. It just checks a
feedback "inbox" file that a human may drop at any time while the run executes,
and reports whether there is un-consumed feedback to fold into one rework cycle.

The workflow places this check at safe points (after implementation, after QA).
When it reports feedback, the workflow routes one pass through the existing
rework agent (apply-review / apply-qa-fixes) with the feedback as required
changes; when it does not, the run proceeds exactly as before. Always exits 0 —
"no feedback" is the common, expected case, not an error.

Inbox file format (the only thing a human edits/creates):

    STATUS: NEW
    SCOPE: story        # optional; `epic` reserved for broader rework
    ## Feedback
    <free-text guidance>

State machine, read from the first whole-line ``STATUS:`` (so prose mentioning
the words is ignored):
  NEW                         -> consume: flip the line to CONSUMED, emit the
                                 feedback (present=yes), proceed
  CONSUMED / empty / missing  -> nothing to do (present=no), proceed
  (no STATUS line, but the
   file has real content)      -> treat as NEW: stamp CONSUMED, emit it — forgiving
                                 for a human who pasted notes without the header

Consuming (flip to CONSUMED) the instant we read NEW is what bounds the loop: the
next pass through the same checkpoint sees CONSUMED and proceeds, so each dropped
feedback triggers exactly one rework cycle.

Args:
    argv[1]  feedback_path : repo-relative (or absolute) path to the inbox file,
                             e.g. ``docs/specs/<story-slug>/feedback.md``

Stdlib-only (runs under the system ``python3``, like the other gate scripts).
Prints JSON captured under the node's ``feedback`` output key:
  {"feedback": {"present": "yes"|"no", "scope": "story"|"epic", "content": "<file text>"}}
"""
import json
import logging
import os
import re
import sys
from pathlib import Path

NEW = "NEW"
CONSUMED = "CONSUMED"

_STATUS_RE = re.compile(r"^STATUS:[ \t]*(\S+)", re.MULTILINE)
# Optional operator-chosen rework scope. `story` (default) reworks just this unit;
# `epic` is reserved for a broader rework the workflow may route on later.
_SCOPE_RE = re.compile(r"^SCOPE:[ \t]*(\S+)", re.MULTILINE)


def _find_repo_root() -> Path:
    """Resolve the consuming repo root. Scripts run from the workflow dir, not the
    repo, so honour AGENT_REPO_DIR (set in production and by the test harness),
    else walk up from CWD looking for the repo markers."""
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    cwd = Path.cwd()
    if (cwd / "docs" / "epics").is_dir() or (cwd / "agents.yml").exists() or (cwd / ".git").exists():
        return cwd
    for candidate in cwd.parents:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return cwd


def status_of(text: str) -> str:
    m = _STATUS_RE.search(text)
    return m.group(1).upper() if m else ""


def scope_of(text: str) -> str:
    m = _SCOPE_RE.search(text)
    val = m.group(1).lower() if m else "story"
    return "epic" if val == "epic" else "story"


def set_status(text: str, new: str) -> str:
    return _STATUS_RE.sub(f"STATUS: {new}", text, count=1)


def absent() -> None:
    print(json.dumps({"feedback": {"present": "no", "scope": "story", "content": ""}}))
    sys.exit(0)


def present(content: str) -> None:
    print(json.dumps({"feedback": {"present": "yes", "scope": scope_of(content), "content": content}}))
    sys.exit(0)


def main(logger: logging.Logger) -> None:
    feedback_path = sys.argv[1] if len(sys.argv) > 1 else ""
    if not feedback_path:
        # Nothing to poll — proceed (lets the node be wired defensively).
        logger.info("no feedback_path given — nothing to poll")
        absent()

    root = _find_repo_root()
    # `root / path` yields `path` when it is absolute (pathlib), so both repo-relative
    # and absolute inbox paths work — the test harness passes absolute sandbox paths.
    inbox = root / feedback_path

    if not inbox.exists():
        logger.info("no inbox file at %s — nothing to poll", inbox)
        absent()

    current = inbox.read_text()
    state = status_of(current)

    if state == NEW:
        inbox.write_text(set_status(current, CONSUMED))
        logger.info("consumed NEW feedback from %s", inbox)
        present(current)

    if state == "":
        # No STATUS line. Treat real content as NEW (forgiving); ignore whitespace-only.
        if current.strip():
            inbox.write_text(f"STATUS: {CONSUMED}\n\n" + current)
            logger.info("no STATUS line but %s has content — treating as NEW", inbox)
            present(current)
        logger.info("no STATUS line and %s is empty — nothing to do", inbox)
        absent()

    # CONSUMED (or any other recognized-but-not-NEW state): already handled / nothing new.
    logger.info("%s is %s — nothing new", inbox, state or "unrecognized")
    absent()


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("check_feedback"))
