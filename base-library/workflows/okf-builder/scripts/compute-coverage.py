#!/usr/bin/env python3
"""okf-builder: compute the book's coverage — the verdict the agent used to emit.

The build's stop condition was ``coverage_complete``, a value the ``recheck`` agent emitted
*about its own work*. This node replaces that self-report with arithmetic: it joins the book's
``code:`` citations against the source inventory (``ostler coverage``) and emits the verdict.
The agent's role narrows to adjudicating the rows the join reports missing — it no longer votes
on whether it is finished.

A verdict this node cannot compute is **not a pass**. An unreadable inventory, an unloadable
graph, or a book with no units at all emits ``coverage_complete="no"`` with the reason attached,
because an empty inventory and a finished book are the same shape and only one of them is done.

Also writes the book's ``coverage.json`` (design §5.5). It is not an audit trinket: coverage is
meaningless without the exclude set it was computed under, the artifact is what makes staleness
visible to CI and to a reader, and its ``commit`` is the anchor a later delta build diffs against.

Args: [repo_root] [features_root] [service] [source_inventory_path] [waivers_path]
      [rescan_round]
Outputs JSON: {"coverage_complete","missing_count","missing_path","coverage_path",
               "coverage_summary","coverage_error","rescan_round"}
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import NoReturn


# The coverage re-scan counter, incremented once per run of this node — the only node that
# sits on the re-scan loop and nowhere else. It is a module global so that EVERY exit path,
# including the early error emits above, carries the increment forward. A path that emitted
# the default would reset the bound, and an error that recurs every pass would then loop
# forever on the one branch that exists to stop it.
_RESCAN_ROUND = 0


def emit(**kw: object) -> NoReturn:
    payload: dict[str, object] = {
        "coverage_complete": "no", "missing_count": 0, "missing_path": "",
        "coverage_path": "", "coverage_summary": "", "coverage_error": "",
        "rescan_round": _RESCAN_ROUND,
    }
    payload.update(kw)
    print(json.dumps(payload))
    sys.exit(0)


def _relative_source(source_root: str, repo_root: str) -> str:
    """The source root as the repo sees it, never as this machine does.

    `coverage.json` is committed, and §10.5 invalidates the anchor when its `sourceRoot` no
    longer matches the config. An absolute path would differ on every checkout, so every
    machine but the one that wrote it would read a valid anchor as stale and rebuild the whole
    book. The anchor has to mean the same thing to everyone who reads it.
    """
    if not source_root:
        return ""
    try:
        return Path(source_root).resolve().relative_to(Path(repo_root).resolve()).as_posix()
    except (ValueError, OSError):
        return source_root  # a source tree outside the repo: absolute is all there is


def _screen_count(okf, service: str) -> int:
    """Screens the book documents. The second axis of §9's verdict starts its life here."""
    from ostler import graph as graph_mod

    data = graph_mod.build(okf.graph, etype="screen", surface=service or None)
    return len(data["nodes"])


def main(logger: logging.Logger) -> None:
    repo_root = sys.argv[1] if len(sys.argv) > 1 else ""
    features_root = sys.argv[2] if len(sys.argv) > 2 else ""
    service = sys.argv[3] if len(sys.argv) > 3 else ""
    inventory_path = sys.argv[4] if len(sys.argv) > 4 else ""
    waivers_path = sys.argv[5] if len(sys.argv) > 5 else ""

    global _RESCAN_ROUND
    try:
        _RESCAN_ROUND = int(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[6] else 0
    except ValueError:
        _RESCAN_ROUND = 0
    _RESCAN_ROUND += 1
    logger.info("coverage re-scan %d", _RESCAN_ROUND)

    # Imported inside main() so an ostler that will not import emits a "no" verdict with its
    # reason, rather than dying at module scope before this script can say anything at all.
    try:
        from ostler import Ostler
        from ostler.coverage import is_complete, render
    except ImportError as exc:
        logger.warning("ostler is not importable — verdict is 'no', not a pass: %s", exc)
        emit(coverage_error=f"ostler is not importable by this interpreter: {exc}")

    if not inventory_path:
        logger.warning("no source inventory path — nothing to join against, verdict is 'no'")
        emit(coverage_error="no source inventory path — nothing to join the book against")

    try:
        okf = Ostler(repo_root)
        result = okf.coverage(inventory=inventory_path, surface=service or None,
                              waivers=waivers_path or None)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        logger.warning("coverage join failed — verdict is 'no', not a pass: %s", exc)
        emit(coverage_error=f"coverage join failed: {exc}")

    try:
        screens = _screen_count(okf, service)
    except (OSError, ValueError, RuntimeError):
        screens = 0

    # The missing list is the agent's input (§5.2): it adjudicates these rows, it does not
    # discover them. Written beside the worklist so a human can read what the run is arguing about.
    missing_path = ""
    if inventory_path:
        missing_file = Path(f"{inventory_path}.missing.json")
        missing_file.write_text(
            json.dumps({"surface": service, "missing": result["missing"]}, indent=2),
            encoding="utf-8")
        missing_path = str(missing_file)

    coverage_path = ""
    if features_root:
        anchor = ""
        try:
            from workhorse.scriptutil import short_sha
            anchor = short_sha(repo_root)
        except (OSError, ValueError, RuntimeError, ImportError):
            anchor = ""  # not a git checkout, or no HEAD yet: the anchor is absent, not faked
        book = Path(features_root)
        if book.is_dir():
            out = book / "coverage.json"
            out.write_text(json.dumps({
                "covered": result["covered"],
                "total": result["total"],
                "waived": result["waived"],
                "screens": screens,
                "generated_from": {
                    "sourceRoot": _relative_source(result.get("sourceRoot", ""), repo_root),
                    "excludes": result.get("excludes", []),
                    "commit": anchor,
                },
            }, indent=2) + "\n", encoding="utf-8")
            coverage_path = str(out)

    complete = is_complete(result)
    logger.info("coverage for %s: %d/%d units covered, %d waived, %d screens, %d missing "
                "→ complete=%s", service or "(whole book)", result["covered"],
                result["total"], result["waived"], screens, len(result["missing"]),
                "yes" if complete else "no")
    emit(coverage_complete="yes" if complete else "no",
         missing_count=len(result["missing"]),
         missing_path=missing_path,
         coverage_path=coverage_path,
         coverage_summary=render(result),
         coverage_error="; ".join(result["errors"]))


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("compute-coverage"))
