#!/usr/bin/env python3
"""Non-blocking operator-feedback poll for the author workflow.

Twin of coder/scripts/check_feedback.py (kept per-workflow, like await-operator.py).
Unlike await-operator.py (which HALTS until a human answers an agent-raised block),
this node NEVER halts and NEVER asks. It checks a feedback "inbox" file a human may
drop at any time while the run executes, and reports whether there is un-consumed
feedback to fold into one rework cycle. The workflow places it at the point a unit
(story) is otherwise considered done: with feedback it routes one rework pass; with
none it advances unchanged. Always exits 0.

Inbox file format (the only thing a human edits/creates):

    STATUS: NEW
    SCOPE: story        # optional; `epic` reserved for broader rework
    ## Feedback
    <free-text guidance>

State machine, read from the first whole-line ``STATUS:``:
  NEW                         -> consume: flip to CONSUMED, emit feedback (present=yes)
  CONSUMED / empty / missing  -> nothing to do (present=no)
  (no STATUS line, real
   content)                   -> treat as NEW: stamp CONSUMED, emit it (forgiving)

Args:
    argv[1]  feedback_path : repo-relative (or absolute) inbox path, e.g.
                             ``docs/epics/<epic>/stories/<slug>/feedback.md``

Stdlib-only. Prints JSON captured under the node's ``feedback`` output key:
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
_SCOPE_RE = re.compile(r"^SCOPE:[ \t]*(\S+)", re.MULTILINE)


def _find_repo_root() -> Path:
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
        logger.info("no feedback_path supplied")
        absent()

    root = _find_repo_root()
    inbox = root / feedback_path  # `root / abs` == abs (pathlib), so abs paths work too

    if not inbox.exists():
        logger.info("no feedback inbox at %s", inbox)
        absent()

    current = inbox.read_text()
    state = status_of(current)

    if state == NEW:
        inbox.write_text(set_status(current, CONSUMED))
        logger.info("feedback present (scope=%s)", scope_of(current))
        present(current)

    if state == "":
        if current.strip():
            inbox.write_text(f"STATUS: {CONSUMED}\n\n" + current)
            logger.info("untagged feedback content treated as NEW (scope=%s)", scope_of(current))
            present(current)
        logger.info("no unconsumed feedback")
        absent()

    logger.info("no unconsumed feedback (state=%s)", state)
    absent()


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("check_feedback"))
