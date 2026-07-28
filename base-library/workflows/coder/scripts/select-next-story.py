#!/usr/bin/env python3
"""Select the next runnable story WITHIN a given epic — STORY selection only (ostler-backed).

Epic selection is a separate concern (select-next-epic.py); this script is told which
epic to work on (argv[1]) and only answers "which story next?". The story DAG now lives
in the epic's ``epic.md`` (``## Stories``) and is owned by ``ostler``; this drives the
in-process ``ostler`` Python API (``Ostler.next_story(epic)``) which returns the first
story in dependency order whose status is not done (deps satisfied), or ``None`` when
none remain.

**"No story" is not one answer, and the workflow must not treat it as one.** An epic can
run out of runnable stories because it is finished, or because its remaining stories were
given up on this run, or because they wait on a dependency nothing will satisfy, or
because they were never authored. Only the first means "merge it". So this script reports
``story_outcome``, and the workflow branches on that:

``story``    a story was selected — build it (``has_story="yes"``).
``done``     every story in the epic is done — prune the epic, open its PR, merge.
``blocked``  stories remain and none is runnable — set the epic aside for this run
             (``flag_epic_blocked``) and move to the next one. Its committed work stays on
             its branch, unmerged; a later run picks it up again.

``has_story`` is still emitted ("yes"/"no") for anything reading it, but it is the
outcome — not its absence — that decides whether an epic is merged. Conflating the two is
what merged an epic with 20 of 21 stories unbuilt after one story gave up on QA.

Per-run skip set: when ``qa_give_up`` gives up on a story it records the slug in
``<run_dir>/qa-skip-stories.txt``. This script (given the run dir as argv[3]) excludes
those slugs so a story that already exhausted its rework budget THIS run is never
re-selected and re-ground — we pick the next eligible story instead, or report ``blocked``.
The set lives in the run dir, so a fresh run starts empty (the story is retried) and an
operator resets by clearing the file.

Args: <epic> [<docs_path>] [<run_dir>]
Outputs JSON: {"has_story": "yes"|"no", "story_outcome": "story"|"done"|"blocked",
               "story_path": "...", "spec_dir": "...", "story_slug": "...",
               "epic": "<epic>", "reason": "..."}
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import NoReturn

from ostler import Ostler
from workhorse import worklist as wl
from workhorse.scriptutil import find_docs_root


_EPIC = ""
# Uniform queue-progress telemetry (done/total + remaining), folded into every emit so
# whichever outcome a run takes still carries "how far through this epic are we" to the
# dashboard. Set once from the ostler report in main(); empty until then / when the
# report can't say. See _progress_fields.
_PROGRESS = {"progress": "", "remaining_count": ""}


def emit(**kwargs: str) -> NoReturn:
    # `story_outcome` defaults to "blocked", not "done": an unexplained "no story" must
    # never be the reason an epic is merged. Every path that means "finished" says so.
    payload = {
        "has_story": "no", "story_outcome": "blocked", "story_path": "", "spec_dir": "",
        "story_slug": "", "epic": _EPIC, "reason": "",
        "progress": _PROGRESS["progress"], "remaining_count": _PROGRESS["remaining_count"],
    }
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def _progress_fields(report: dict | str) -> dict[str, str]:
    """Queue progress for the dashboard, computed through the shared worklist snapshot so
    coder's stories read the same "done/total" shape every workflow's queue will.

    The story queue *is* a worklist — ``report['done']`` finished items plus the
    ``report['remaining']`` not-done slugs — so we hand those to :func:`worklist.snapshot`
    rather than formatting the numbers here. Best-effort: a legacy/failed report (a bare
    string, or one without the counts) yields empty fields and the labels simply carry no
    progress, exactly as an unrenderable label is dropped."""
    if not isinstance(report, dict):
        return {"progress": "", "remaining_count": ""}
    done = int(report.get("done") or 0)
    remaining = [str(s) for s in (report.get("remaining") or [])]
    items = [{"id": f"__done_{i}", "status": "done"} for i in range(done)]
    items += [{"id": s, "status": "pending"} for s in remaining]
    snap = wl.snapshot(items)
    return {"progress": snap["progress"], "remaining_count": str(snap["remaining"])}


def _report(okf: Ostler, epic: str, skip: set[str]) -> dict | str:
    """Ostler's next-story report, or "" on a tooling failure.

    ``skip`` (slugs given up this run) is passed into ostler so a given-up story is not
    re-offered — without it, that story stays first-runnable forever and the epic prunes
    with other stories unbuilt. This is skip-aware selection at the source, replacing the
    old ``dependencies.json`` fallback that could no longer run (that file folded into
    ``epic.md``).

    The *report* rather than ``next_story``: it distinguishes "done" from "blocked", which
    is the whole difference between merging an epic and setting it aside.
    """
    try:
        return okf.next_story_report(epic, skip=skip)
    except (OSError, ValueError, RuntimeError):
        return ""


def _is_done(story_md: Path) -> bool:
    """Return True if the story's status line contains 'QA passed'."""
    try:
        return "QA passed" in story_md.read_text(encoding="utf-8")
    except OSError:
        return False


def _load_skip_set(root: Path, run_dir: str) -> set[str]:
    """The per-run skip set: story slugs qa_give_up has given up THIS run.

    ``run_dir`` is the current run directory (argv[3]); the set lives at
    ``<run_dir>/qa-skip-stories.txt`` (one slug per line). Missing dir/file → empty set,
    so this is a no-op on the first pass and on any run that never gave up a story.
    """
    if not run_dir:
        return set()
    p = Path(run_dir)
    if not p.is_absolute():
        p = root / p
    try:
        text = (p / "qa-skip-stories.txt").read_text(encoding="utf-8")
    except OSError:
        return set()
    return {ln.strip() for ln in text.splitlines() if ln.strip()}


def _next_from_json(root: Path, epic: str, skip: set[str]) -> dict | None | str:
    """Fallback: read dependencies.json from the epic directory and find the first
    runnable story (not done, not in the per-run skip set, all deps done), respecting
    dependency order.

    Returns a dict {slug, path}, ``None`` when every story is DONE, or "" on error. A
    skipped story is NOT treated as done — its dependents stay blocked, since they depend
    on work that did not pass.

    ``None`` means *done* and nothing else. The not-done-but-not-runnable cases each get
    their own sentinel (``_all_skipped``, ``_blocked``, ``_missing_story_md``,
    ``_no_dep_file``) because the caller merges the epic on "done" — so an epic that still
    has unbuilt stories in it must never come back as ``None``.
    """
    dep_file = root / "docs" / "epics" / epic / "dependencies.json"
    if not dep_file.is_file():
        return {"_no_dep_file": True}  # sentinel: caller emits the specific error
    try:
        data = json.loads(dep_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    stories = data.get("stories")
    if not isinstance(stories, list):
        return ""

    done: set[str] = set()
    for s in stories:
        slug = str(s.get("slug", ""))
        path = s.get("path", "")
        story_md = Path(path) if path else root / "docs" / "epics" / epic / "stories" / slug / "story.md"
        if _is_done(story_md):
            done.add(slug)

    skipped_runnable = False  # a story that WOULD run but for the per-run skip set
    waiting: list[str] = []   # not done, not runnable: deps unmet
    for s in stories:
        slug = str(s.get("slug", ""))
        if slug in done:
            continue
        deps = s.get("dependencies", [])
        if any(d not in done for d in deps):
            waiting.append(slug)
            continue
        if slug in skip:
            # Runnable (deps satisfied) but given up this run — exclude, and remember we
            # did so, so the caller can report "stopped on skip" vs "all done".
            skipped_runnable = True
            continue
        path = s.get("path", "")
        if not path:
            path = str(root / "docs" / "epics" / epic / "stories" / slug / "story.md")
        story_md = Path(path)
        if not story_md.is_file():
            # story listed in deps but story.md not authored yet → emit specific reason
            return {"_missing_story_md": path}
        return {"slug": slug, "path": path}

    if skipped_runnable:
        return {"_all_skipped": True}  # sentinel: remaining runnable stories were skipped
    if waiting:
        return {"_blocked": waiting}   # sentinel: remaining stories wait on unmet deps
    return None  # all done


def main(logger: logging.Logger) -> None:
    global _EPIC, _PROGRESS
    _EPIC = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else ""
    docs_path_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    run_dir_arg = sys.argv[3] if len(sys.argv) > 3 else ""

    if not _EPIC:
        logger.warning("no epic supplied to select-next-story")
        emit(reason="no epic supplied to select-next-story (epic selection is select-next-epic.py)")

    root = find_docs_root(docs_path_arg)
    okf = Ostler(root)
    skip = _load_skip_set(root, run_dir_arg)

    report = _report(okf, _EPIC, skip)
    _PROGRESS = _progress_fields(report)
    state = report.get("state", "") if isinstance(report, dict) else ""
    nxt = report.get("story") if isinstance(report, dict) else None

    # Selection is now skip-aware at the ostler level, so a given-up story is never handed
    # back here. This guard only fires if that contract regresses.
    forced_by_skip = isinstance(nxt, dict) and str(nxt.get("slug", "")) in skip
    if forced_by_skip:
        nxt, state = None, "blocked"

    if state == "done":
        logger.info("%s", report["detail"])
        emit(story_outcome="done", reason=report["detail"])
    if state == "blocked":
        detail = report["detail"] if isinstance(report, dict) and not forced_by_skip else (
            f"the story ostler offered for epic '{_EPIC}' was given up this run")
        logger.warning("epic '%s' is blocked: %s", _EPIC, detail)
        emit(reason=f"{detail} — setting this epic aside for this run; its work stays on its "
                    "branch, unmerged, and a later run retries it")

    # Fall back to dependencies.json only when ostler could not answer at all: it failed
    # (""), the epic is not in its graph, or the epic carries no stories there. A real
    # ostler verdict is authoritative — consulting the legacy file after it would let a
    # missing dependencies.json override a correct "all done".
    if not nxt:
        json_nxt = _next_from_json(root, _EPIC, skip)
        if isinstance(json_nxt, dict) and json_nxt.get("_no_dep_file"):
            emit(reason=f"no dependencies.json found for epic '{_EPIC}' — cannot select a story; "
                        "setting it aside rather than merging an epic we cannot read")
        if isinstance(json_nxt, dict) and json_nxt.get("_all_skipped"):
            emit(reason=f"remaining runnable stories in epic '{_EPIC}' were all given up this run — "
                        "setting it aside; start a new run or clear the skip set to retry")
        if isinstance(json_nxt, dict) and json_nxt.get("_blocked"):
            emit(reason=f"remaining stories in epic '{_EPIC}' wait on unmet dependencies "
                        f"({', '.join(json_nxt['_blocked'])}) — setting it aside")
        if isinstance(json_nxt, dict) and json_nxt.get("_missing_story_md"):
            emit(reason=f"next story's story.md not found: {json_nxt['_missing_story_md']} — "
                        "unauthored scope, so this epic is set aside rather than merged")
        if isinstance(json_nxt, dict) and "slug" in json_nxt:
            nxt = json_nxt
        elif json_nxt is None:
            emit(story_outcome="done",
                 reason=f"every story in epic '{_EPIC}' is done")
        else:
            emit(reason=f"could not read the story DAG for epic '{_EPIC}' — setting it aside")

    slug = str(nxt.get("slug"))
    # Final guard: never hand back a story in this run's skip set (the fallback already
    # excludes them, so this only fires if a selection path regressed).
    if slug in skip:
        logger.warning("story '%s' was given up this run — stopping to avoid re-grinding", slug)
        emit(reason=f"story '{slug}' was given up this run — setting the epic aside to avoid "
                    "re-grinding; start a new run or clear the skip set to retry")
    try:
        spec_dir = okf.spec_path(slug) or f"docs/specs/{slug}"
    except (OSError, ValueError, RuntimeError):
        spec_dir = f"docs/specs/{slug}"
    story_path = str(nxt.get("path") or "")

    logger.info("selected story '%s' in epic '%s'", slug, _EPIC)
    emit(
        has_story="yes",
        story_outcome="story",
        story_path=story_path,
        spec_dir=spec_dir,
        story_slug=slug,
        epic=_EPIC,
    )


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("select-next-story"))
