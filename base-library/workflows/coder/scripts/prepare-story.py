#!/usr/bin/env python3
"""Convergence node: resolve a story slug + epic to canonical filesystem paths via the ostler API.

Both story mode and epic mode flow through this node before entering the dev phase.
It ensures a single canonical source for pipeline vars (story_path, spec_dir, qa_dir,
story_slug) regardless of which mode produced the slug.

Args: <docs_path> <story_slug> <epic>
Outputs JSON: {"story_path": "...", "spec_dir": "...", "qa_dir": "...",
               "story_slug": "...", "story_epic": "..."}
"""
from __future__ import annotations

import json
import logging
import sys

from ostler import Ostler
from workhorse.scriptutil import find_docs_root


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
