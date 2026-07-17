#!/usr/bin/env python3
"""okf-builder: resolve paths and initialize the build worklist.

Creates (or reuses, for resume) the JSON worklist the drain loop drains. The
worklist is the crawl's memory: a list of typed items ``{kind,target,context,
status}`` where an item's investigation may append deeper items (a surface spawns
its elements, an element spawns its handler layer, a layer spawns its callees).

**The worklist is keyed to the book it remembers.** It is a memory of work whose product is
the book, so a worklist carrying `done` items for a book that no longer exists is not a
resume — it is a false memory, and its `done` counter makes a bounded run instantly
over-budget and hand out zero items. When the stamped book is gone or the service changed,
the memory is void and the run starts fresh, saying so.

Args: [docs_path] [service] [source_path] [source_excludes]
Outputs JSON: {"worklist_path","features_root","repo_root","source_root","service",
               "ostler_ok","done_baseline","worklist_reset","prepare_error"}
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import NoReturn

from workhorse.scriptutil import find_docs_root


def emit(**kw: object) -> NoReturn:
    payload: dict[str, object] = {
        "worklist_path": "", "features_root": "", "repo_root": "", "source_root": "",
        "service": "", "source_excludes": "", "ostler_ok": "no", "done_baseline": 0,
        "worklist_reset": "no", "prepare_error": "",
    }
    payload.update(kw)
    print(json.dumps(payload))
    sys.exit(0)


def book_has_docs(features: Path) -> bool:
    """Whether the book exists as more than a directory entry."""
    return features.is_dir() and any(features.rglob("*.md"))


def load_worklist(wl: Path, service: str, features: Path) -> tuple[dict, bool]:
    """The worklist to drain, and whether a stale one was discarded.

    Reuse requires the stamped service to match and the remembered work to still have a
    product. A worklist claiming completed investigations against a book with no docs is
    remembering a book that was deleted underneath it (see the module docstring).
    """
    fresh: dict = {"service": service, "book": str(features), "items": []}
    if not wl.exists():
        return fresh, False
    try:
        data = json.loads(wl.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fresh, True
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return fresh, True
    if data.get("service", service) != service:
        return fresh, True
    done = sum(1 for i in data["items"] if i.get("status") == "done")
    if done and not book_has_docs(features):
        return fresh, True
    data.setdefault("service", service)
    data["book"] = str(features)
    return data, False


def ostler_loads(root: Path) -> tuple[str, str]:
    """Whether ostler can load an OKF graph at this root, and why not if it cannot.

    The import sits here rather than at module scope so an ostler that will not import is
    reported as ``ostler_ok="no"`` — the branch this script exists to feed. At module scope
    it killed the script with a traceback before ``main()`` could emit anything, so the
    fail-soft guard could not fire for the one condition it is named after.
    """
    try:
        from ostler import Ostler
    except ImportError as exc:
        return "no", f"ostler is not importable by this interpreter: {exc}"
    try:
        _ = Ostler(root).graph
    except (OSError, ValueError, RuntimeError) as exc:
        return "no", f"ostler cannot load a graph at {root}: {exc}"
    return "yes", ""


def main(logger: logging.Logger) -> None:
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
        logger.warning("source path %s is outside the repo root %s — refusing to prepare",
                       source, root)
        emit(repo_root=str(root), service=service,
             prepare_error=f"source path {source} is outside the repo root {root}")
    if not source.is_dir():
        logger.warning("source root %s is not a directory — refusing to prepare", source)
        emit(repo_root=str(root), service=service, source_root=str(source),
             prepare_error=f"source root {source} is not a directory")
    features = root / "docs" / "features" / service if service else root / "docs" / "features"
    build_dir = root / ".agents" / "okf-build"
    build_dir.mkdir(parents=True, exist_ok=True)
    wl = build_dir / f"{service or 'all'}.worklist.json"
    data, reset = load_worklist(wl, service, features)
    if reset:
        # The stamped memory was void (wrong service, unreadable, or a book that no longer
        # exists). Silently starting from zero would look like a resume that lost its work.
        logger.warning("discarded a stale worklist at %s — starting fresh for service %r",
                       wl, service)
    wl.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # The run's budget baseline: `max_items` bounds *this* run's investigations, not the
    # worklist's lifetime total, so a resume gets its own allowance.
    baseline = sum(1 for i in data["items"] if i.get("status") == "done")
    logger.info("prepared %s: book %s, source %s, worklist %s (%d items, %d done at baseline)",
                service or "(whole tree)", features, source, wl, len(data["items"]), baseline)
    ostler_ok, why = ostler_loads(root)
    if ostler_ok != "yes":
        logger.warning("ostler cannot load a graph — the build will branch away: %s", why)
    emit(worklist_path=str(wl), features_root=str(features), repo_root=str(root),
         source_root=str(source), service=service, source_excludes=source_excludes,
         ostler_ok=ostler_ok, done_baseline=baseline,
         worklist_reset="yes" if reset else "no", prepare_error=why)


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("prepare"))
