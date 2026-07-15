#!/usr/bin/env python3
"""okf-builder: resolve paths and initialize the build worklist.

Creates (or reuses, for resume) the JSON worklist the drain loop drains. The
worklist is the crawl's memory: a list of typed items ``{kind,target,context,
status}`` where an item's investigation may append deeper items (a surface spawns
its elements, an element spawns its handler layer, a layer spawns its callees).

Args: [docs_path] [service] [source_path] [source_excludes]
Outputs JSON: {"worklist_path","features_root","repo_root","source_root","service",
               "ostler_ok","done_count"}
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from workhorse.scriptutil import find_docs_root


def emit(**kw: object) -> None:
    payload: dict[str, object] = {
        "worklist_path": "", "features_root": "", "repo_root": "", "source_root": "",
        "service": "", "source_excludes": "", "ostler_ok": "no", "done_count": 0,
    }
    payload.update(kw)
    print(json.dumps(payload))
    sys.exit(0)


def main() -> None:
    docs_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    service = sys.argv[2] if len(sys.argv) > 2 else ""
    source_arg = sys.argv[3] if len(sys.argv) > 3 else ""
    source_excludes = sys.argv[4] if len(sys.argv) > 4 else ""
    root = Path(find_docs_root(docs_arg))
    source_rel = source_arg or service
    source = (root / source_rel).resolve() if source_rel else root.resolve()
    try:
        source.relative_to(root.resolve())
    except ValueError:
        emit(repo_root=str(root), service=service)
    if not source.is_dir():
        emit(repo_root=str(root), service=service, source_root=str(source))
    features = root / "docs" / "features" / service if service else root / "docs" / "features"
    build_dir = root / ".agents" / "okf-build"
    build_dir.mkdir(parents=True, exist_ok=True)
    wl = build_dir / f"{service or 'all'}.worklist.json"
    if not wl.exists():
        wl.write_text(json.dumps({"items": []}, indent=2))
    ostler_ok = "yes" if shutil.which("ostler") else "no"
    emit(worklist_path=str(wl), features_root=str(features), repo_root=str(root),
         source_root=str(source),
         service=service, source_excludes=source_excludes, ostler_ok=ostler_ok, done_count=0)


if __name__ == "__main__":
    main()
