#!/usr/bin/env python3
"""Decide whether this run's docs are managed by ostler's OKF graph, so the story's
documentation step only fires where it can actually do something.

The coder workflow runs against many repos; most do not use ostler. This is the cheap
pre-gate that keeps `document_story` (an agent turn) from running where there is nothing
to document: it answers "yes" only when the `ostler` CLI is on PATH *and* the docs root
has a `docs/features/` tree (the home of OKF UI-profile nodes). Everything semantic —
which surfaces the story touched, whether it touched any — is left to the agent.

Args: [base_path] [features_subdir]
  base_path       docs/repo root; "" → AGENT_REPO_DIR (via find_docs_root).
  features_subdir where the OKF feature docs live, relative to base (or absolute);
                  default "docs/features". The author workflow passes cfg.features_dir.
Outputs JSON: {"has_okf": "yes"|"no", "features_root": "<abs path or ''>", "reason": "..."}
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from workhorse.scriptutil import find_docs_root


def emit(**kwargs: str) -> None:
    payload = {"has_okf": "no", "features_root": "", "reason": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def main() -> None:
    base_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    features_subdir = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else "docs/features"
    base = Path(find_docs_root(base_arg))
    sub = Path(features_subdir)
    features = sub if sub.is_absolute() else base / sub

    if shutil.which("ostler") is None:
        emit(has_okf="no", reason="ostler CLI not on PATH")
    if not features.is_dir():
        emit(has_okf="no", reason=f"no features dir at {features}")
    emit(has_okf="yes", features_root=str(features),
         reason=f"ostler present and {features} exists")


if __name__ == "__main__":
    main()
