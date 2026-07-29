#!/usr/bin/env python3
"""Thin deterministic grounding pre-gate for a written story — ostler-backed (fail-closed).

``validate-story.py`` checks a story is *structurally* a coder-ready contract. It cannot check
that the story is *grounded* — that it was written against the surface documentation instead of
from the author agent's imagination. This gate enforces those machine-checkable preconditions so
the adversarial ``audit-story`` agent isn't wasted re-judging a story that structurally cannot be
grounded. It is the author analog of the coder's ``verify_qa_evidence.py``.

Strictly presence/structure — **no semantic judgment** (that is the auditor's job):

  - every seed item this story ``covers`` exists in the epic's seeds (no phantom scope) — read
    from ``epic.md`` via the in-process ostler API (``Ostler.list``);
  - **iff** the graph actually holds OKF UI nodes: the story cites at least one of them, and
    every citation it does make resolves. A UI node's identity is a repo-relative path (or
    ``path#anchor``), so a citation is an ordinary markdown link and
    ``ostler query surfaces-referenced-by-story`` resolves it — ``kind: "ui"`` for a citation
    that lands on a node, ``kind: "missing"`` for one that lands on nothing.

    Armed on the *graph*, not on a configured path: author only ever **reads** the book (the
    okf-builder writes it, from code that exists), so as UI nodes accrue this check re-arms
    itself with no flag, and a greenfield repo whose book is still empty is not asked to cite
    what does not exist yet.

Stdlib-only except for the in-process ``ostler`` API (``from ostler import Ostler``).

Args:
    argv[1]  story_dir      : repo-relative story folder (…/stories/<slug>)
    argv[2]  epic_dir       : repo-relative epic folder (docs/epics/<epic>)
    argv[3]  features_dir   : repo-relative feature-doc root (informational)

Outputs JSON: {"story_grounding_ok": "yes"|"no", "story_grounding_errors": "<newline-joined>"}
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import NoReturn

from ostler import Ostler


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def emit(ok: bool, errors: list[str]) -> NoReturn:
    print(json.dumps({
        "story_grounding_ok": "yes" if ok else "no",
        "story_grounding_errors": "\n".join(errors),
    }))
    sys.exit(0)


def main(logger: logging.Logger) -> None:
    story_dir_rel = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    epic_dir_rel = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else ""

    errors: list[str] = []
    if not story_dir_rel or not epic_dir_rel:
        logger.warning("story_dir and epic_dir are required — nothing to check")
        emit(False, ["story_dir and epic_dir are required"])

    root = find_repo_root()
    okf = Ostler(root)
    slug = Path(story_dir_rel).name
    epic = Path(epic_dir_rel).name

    # ── this epic's seed ids + this story's covered seed items (read from epic.md) ──
    try:
        seeds = okf.list("seed", epic=epic)
    except (OSError, ValueError, RuntimeError):
        logger.warning("could not read the epic's seeds via the ostler API for %s", epic)
        emit(False, ["could not read the epic's seeds via the ostler API"])
    seed_ids = {str(s.get("id", "")).strip() for s in seeds if s.get("id")}

    stories = okf.list("story", epic=epic)
    story_row = next((s for s in stories if str(s.get("slug", "")).strip() == slug), None)
    story_seed_items = [str(x).strip() for x in ((story_row or {}).get("covers") or [])]

    for sid in story_seed_items:
        if seed_ids and sid not in seed_ids:
            errors.append(f"story claims seed item '{sid}' that is not in the epic's seeds (phantom scope)")

    # ── the story cites the OKF book (only once the book actually holds nodes) ──
    # Opt-in by presence of the nodes themselves: author reads the book, it never builds it,
    # so a repo whose okf-builder has not run yet has nothing to cite and must not hard-fail.
    if okf.graph.ui_nodes:
        refs = okf.query("surfaces-referenced-by-story", slug)
        cited = [r for r in refs if r.get("kind") == "ui"]
        dangling = [str(r.get("path", "")) for r in refs if r.get("kind") == "missing"]
        for path in dangling:
            errors.append(
                f"story cites '{path}', which resolves to no OKF node — cite the node's id "
                "exactly as the book spells it (a repo-relative path, or path#anchor)"
            )
        if not cited:
            logger.info("story '%s' cites no OKF node", slug)
            errors.append(
                "story cites no OKF node — link the ids of the surface/component/interaction "
                "nodes this story works on from its `## Context`, so the scope is grounded in "
                "the book instead of asserted"
            )

    logger.info("story '%s' grounding: %s", slug, "ok" if not errors else f"{len(errors)} error(s)")
    emit(not errors, errors)


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("check-story-grounding"))
