#!/usr/bin/env python3
"""Convergence node: resolve a story slug + epic to canonical filesystem paths via ostler.

Both story mode and epic mode flow through this node before entering the dev phase.
It ensures a single canonical source for pipeline vars (story_path, spec_dir, qa_dir,
story_slug) regardless of which mode produced the slug.

Args: <docs_path> <story_slug> <epic>
Outputs JSON: {"story_path": "...", "spec_dir": "...", "qa_dir": "...",
               "story_slug": "...", "story_epic": "..."}
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from workhorse.scriptutil import find_docs_root


def _ostler_path(docs_root: Path, subcmd: str, *args: str) -> str:
    """Call ostler path <subcmd> and return stdout, stripped."""
    cmd = ["ostler", "-C", str(docs_root), "path", subcmd, *args]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def main() -> None:
    docs_path_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    slug = sys.argv[2] if len(sys.argv) > 2 else ""
    epic = sys.argv[3] if len(sys.argv) > 3 else ""

    if not slug:
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

    spec_dir_rel = _ostler_path(docs_root, "spec", slug) or f"docs/specs/{slug}"
    spec_dir = str((docs_root / spec_dir_rel).resolve())

    story_path = ""
    if epic:
        story_path_rel = _ostler_path(docs_root, "story", epic, slug) or f"docs/epics/{epic}/stories/{slug}/story.md"
        story_path = str((docs_root / story_path_rel).resolve())

    print(json.dumps({
        "story_path": story_path,
        "spec_dir": spec_dir,
        "qa_dir": spec_dir + "/qa",
        "story_slug": slug,
        "story_epic": epic,
    }))


if __name__ == "__main__":
    main()
