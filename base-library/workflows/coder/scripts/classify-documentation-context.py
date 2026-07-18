#!/usr/bin/env python3
"""Choose deterministic local diff mapping or semantic multi-repo documentation review."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from git.exc import GitError

from workhorse.scriptutil import find_docs_root, open_repo


def main(logger: logging.Logger) -> None:
    docs_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    roots_json = sys.argv[2] if len(sys.argv) > 2 else "[]"
    docs_root = Path(find_docs_root(docs_arg)).resolve()
    try:
        roots = json.loads(roots_json)
    except json.JSONDecodeError:
        roots = []
    roots = roots if isinstance(roots, list) else []

    try:
        repo = open_repo(docs_root)
        worktree = Path(repo.working_tree_dir).resolve()
    except (GitError, OSError, TypeError, ValueError, RuntimeError):
        worktree = None

    normalized: list[str] = []
    external: list[str] = []
    for raw in roots:
        surface, separator, source = str(raw).partition("=")
        if not separator or not surface.strip() or not source.strip():
            continue
        path = Path(source).resolve()
        if worktree is None or not path.is_relative_to(worktree):
            external.append(str(path))
            continue
        relative = path.relative_to(worktree).as_posix() or "."
        normalized.append(f"{surface.strip()}={relative}")

    mode = "local" if worktree is not None and normalized and not external else "semantic"
    if mode == "local":
        notes = "All affected source roots share the docs Git worktree; deterministic diff mapping enabled."
    else:
        notes = (
            "Affected sources span repositories or the docs root is not a Git worktree; "
            "doctor plus independent semantic review is authoritative."
        )
    logger.info("documentation context mode=%s", mode)
    print(
        json.dumps(
            {
                "documentation_context_mode": mode,
                "documentation_source_roots_json": json.dumps(normalized),
                "documentation_context_notes": notes,
            }
        )
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("classify-documentation-context"))
