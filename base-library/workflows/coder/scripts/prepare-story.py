#!/usr/bin/env python3
"""Convergence node: resolve a story slug + epic to canonical filesystem paths via the ostler API.

Both story mode and epic mode flow through this node before entering the dev phase.
It ensures a single canonical source for pipeline vars (story_path, spec_dir, qa_dir,
story_slug) regardless of which mode produced the slug.

It is also the coder's **fail-closed gate on an unauthored story**: if ostler can see the story
in the graph and says it is not authored — story.md missing, or still the bare
``ostler create story`` scaffold with empty required sections — this node exits 2 rather than
handing an empty story to the planner. An author run once produced 44 stubs and reported
success; coder would have happily planned, implemented and QA'd against every one of them,
inventing the requirements as it went. A story with nothing in it is a broken input, not work.

Args: <docs_path> <story_slug> <epic>
Outputs JSON: {"story_path": "...", "spec_dir": "...", "qa_dir": "...",
               "story_slug": "...", "story_epic": "..."}
Exit codes: 0 normal; 2 the story exists in the graph but is not authored.
"""
from __future__ import annotations

import json
import logging
import sys

from ostler import Ostler
from workhorse.scriptutil import find_docs_root


def guard_authored(okf: Ostler, slug: str, logger: logging.Logger) -> None:
    """Exit 2 if the graph knows this story and reports it unauthored.

    "Authored" is ostler's verdict (``Story.authored``), never a local re-derivation — the same
    fact ``ostler doctor``'s ``unwritten-story`` finding and the author workflow's own gates read,
    so coder and author can never disagree about whether a story says anything.

    A graph that will not load, or a slug it does not know, is a *different* fault and is only
    logged: story mode can legitimately be pointed at a story outside the epics tree, and the
    path resolution below already tolerates an absent graph. This gate is about an unauthored
    story, which ostler can state positively.
    """
    try:
        found = okf.graph.find_story(slug)
    except (OSError, ValueError, RuntimeError) as exc:
        logger.info("could not load the doc graph to check '%s' is authored (%s)", slug, exc)
        return
    if found is None:
        logger.info("story '%s' is not in the doc graph — cannot check it is authored", slug)
        return
    story = found[1]
    if story.authored:
        return
    if story.story_md is None:
        detail = "story.md is missing"
    else:
        detail = ("story.md is still a bare scaffold — empty: "
                  + ", ".join(story.unwritten_sections))
    logger.error("story '%s' is not authored (%s); refusing to plan against it. "
                 "Run the author workflow for epic '%s' first.", slug, detail, found[0].name)
    sys.exit(2)


def main(logger: logging.Logger) -> None:
    docs_path_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    slug = sys.argv[2] if len(sys.argv) > 2 else ""
    epic = sys.argv[3] if len(sys.argv) > 3 else ""

    if not slug:
        logger.info("no story slug — nothing to resolve")
        print(json.dumps({
            "story_path": "", "spec_dir": "", "qa_dir": "", "story_slug": "", "story_epic": "",
        }))
        return

    docs_root = find_docs_root(docs_path_arg)

    if not epic:
        # Discover which epic owns this story by scanning epics/ for a matching story folder.
        matches = list(docs_root.glob(f"docs/epics/*/stories/{slug}/story.md"))
        if matches:
            epic = matches[0].parent.parent.parent.name  # epics/<epic>/stories/<slug>/story.md
        else:
            logger.warning("no epic given and no matching story folder found for '%s'", slug)

    okf = Ostler(docs_root)
    guard_authored(okf, slug, logger)

    try:
        spec_dir_rel = okf.spec_path(slug)
    except (OSError, ValueError, RuntimeError):
        spec_dir_rel = ""
    spec_dir_rel = spec_dir_rel or f"docs/specs/{slug}"
    spec_dir = str((docs_root / spec_dir_rel).resolve())

    story_path = ""
    if epic:
        try:
            story_path_rel = okf.story_path(epic, slug)
        except (OSError, ValueError, RuntimeError):
            story_path_rel = ""
        story_path_rel = story_path_rel or f"docs/epics/{epic}/stories/{slug}/story.md"
        story_path = str((docs_root / story_path_rel).resolve())

    print(json.dumps({
        "story_path": story_path,
        "spec_dir": spec_dir,
        "qa_dir": spec_dir + "/qa",
        "story_slug": slug,
        "story_epic": epic,
    }))


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("prepare-story"))
