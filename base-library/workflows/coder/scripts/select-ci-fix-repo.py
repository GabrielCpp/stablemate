#!/usr/bin/env python3
"""Select the next workspace repo that needs a CI fix pass.

Called by the fix_ci flow's select_ci_repo node to iterate repos one at a time.
Each call returns the next unprocessed repo; the loop continues until all repos
have been visited (has_repo=no).

When `repo` is set explicitly, the repo is returned on the first call and
has_repo=no on the second — a single-repo fast path.

When `repo` is empty, all workspace repos are iterated in declaration order,
skipping any already listed in `processed_repos`.

Usage: select-ci-fix-repo.py <repo> <ci_summary> <docs_path> <processed_repos_json>
Prints one JSON object on stdout (parsed by the local-worker ScriptNode).
"""
from __future__ import annotations

import json
import logging
import sys

from workhorse.scriptutil import find_repo_root, resolve_workspace

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")

    repo_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    # ci_summary and docs_path are passed but not used for routing logic here —
    # repo ordering is workspace-based, not ci_summary-based. They're accepted so
    # the workflow can forward them without special-casing.
    # ci_summary = sys.argv[2] if len(sys.argv) > 2 else ""
    # docs_path  = sys.argv[3] if len(sys.argv) > 3 else ""
    processed_json = sys.argv[4] if len(sys.argv) > 4 else "[]"

    try:
        processed: list[str] = json.loads(processed_json)
        if not isinstance(processed, list):
            processed = []
    except (json.JSONDecodeError, ValueError):
        processed = []

    repos = resolve_workspace("CODER_WORKSPACE")

    if repo_arg:
        # Single-repo mode: yield the named repo once, then done.
        if repo_arg in processed:
            _done(processed)
            return
        repo_info = repos.get(repo_arg)
        if not repo_info:
            logger.warning("repo '%s' not found in workspace — skipping", repo_arg)
            _done(processed)
            return
        _found(repo_arg, repo_info, processed)
    else:
        # Multi-repo mode: pick the first repo not yet in processed.
        for name, info in repos.items():
            if name not in processed:
                _found(name, info, processed)
                return
        _done(processed)


def _found(name: str, info: dict, processed: list[str]) -> None:
    updated = processed + [name]
    print(json.dumps({
        "has_repo": "yes",
        "current_repo": name,
        "current_repo_cwd": str(info.get("path", find_repo_root())),
        "processed_repos": json.dumps(updated),
    }))


def _done(processed: list[str]) -> None:
    print(json.dumps({
        "has_repo": "no",
        "current_repo": "",
        "current_repo_cwd": "",
        "processed_repos": json.dumps(processed),
    }))


if __name__ == "__main__":
    main()
