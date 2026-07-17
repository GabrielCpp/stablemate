#!/usr/bin/env python3
"""Resolve all workspace repo paths from CODER_WORKSPACE for early add_dirs injection.

Used by agent nodes that run before resolve-impl-context (which resolves
affected_repo_paths from the plan). This gives every early node (plan, review)
access to all workspace repos for skill discovery and file access.

Args: <docs_path>
Outputs JSON: {"workspace_dirs": ["/abs/path/repo1", ...]}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from workhorse.scriptutil import find_docs_root, resolve_workspace


def main() -> None:
    docs_path_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    docs_root = find_docs_root(docs_path_arg)

    repos = resolve_workspace("CODER_WORKSPACE")
    dirs = [r["path"] for r in repos.values() if Path(r["path"]).is_dir()]

    # Always include the docs root even if it's not in the workspace file.
    docs_root_str = str(docs_root)
    if docs_root_str not in dirs:
        dirs = [docs_root_str, *dirs]

    print(json.dumps({"workspace_dirs": dirs}))


if __name__ == "__main__":
    main()
