#!/usr/bin/env python3
"""Select the next runnable story WITHIN a given epic — STORY selection only (ostler-backed).

Epic selection is a separate concern (select-next-epic.py); this script is told which
epic to work on (argv[1]) and only answers "which story next?". The story DAG now lives
in the epic's ``epic.md`` (``## Stories``) and is owned by ``ostler``; this shells out to
``ostler next-story <epic>`` which returns the first story in dependency order whose
status is not done (deps satisfied), or null when none remain.

When the epic has no more runnable story, it returns ``has_story="no"`` — the workflow
treats that as "this epic is finished for now": open its PR, merge, advance to the next
epic.

Per-run skip set: when ``qa_give_up`` gives up on a story it records the slug in
``<run_dir>/qa-skip-stories.txt``. This script (given the run dir as argv[3]) excludes
those slugs so a story that already exhausted its rework budget THIS run is never
re-selected and re-ground — we pick the next eligible story instead, or stop. The set
lives in the run dir, so a fresh run starts empty (the story is retried) and an operator
resets by clearing the file.

Args: <epic> [<docs_path>] [<run_dir>]
Outputs JSON: {"has_story": "yes"|"no", "story_path": "...", "spec_dir": "...",
               "story_slug": "...", "epic": "<epic>", "reason": "..."}
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from workhorse.scriptutil import find_docs_root


_EPIC = ""


def emit(**kwargs: str) -> None:
    payload = {
        "has_story": "no", "story_path": "", "spec_dir": "", "story_slug": "",
        "epic": _EPIC, "reason": "",
    }
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def _ostler_path(root: Path, subcmd: str, *args: str) -> str:
    ostler = shutil.which("ostler")
    if not ostler:
        return ""
    try:
        proc = subprocess.run([ostler, "-C", str(root), "path", subcmd, *args],
                              capture_output=True, text=True, timeout=30)
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _next_story(root: Path, epic: str) -> dict | None | str:
    """Return the next-story dict, None when none remain, or "" on a tooling failure."""
    ostler = shutil.which("ostler")
    if not ostler:
        return ""
    try:
        proc = subprocess.run([ostler, "-C", str(root), "next-story", epic, "--json"],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ""
    raw = (proc.stdout or "").strip()
    if raw in ("null", "(none)", ""):
        return None
    start = raw.find("{")
    if start == -1:
        return None
    try:
        return json.JSONDecoder().raw_decode(raw[start:])[0]
    except (json.JSONDecodeError, ValueError):
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

    Returns a dict {slug, path}, None when all stories are done/skipped/missing, or ""
    on error. The returned dict may include a "reason" key when a candidate story's
    story.md is absent. A skipped story is NOT treated as done — its dependents stay
    blocked, since they depend on work that did not pass.
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
    for s in stories:
        slug = str(s.get("slug", ""))
        if slug in done:
            continue
        deps = s.get("dependencies", [])
        if any(d not in done for d in deps):
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
    return None  # all done (or all blocked on unmet deps)


def main() -> None:
    global _EPIC
    _EPIC = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else ""
    docs_path_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    run_dir_arg = sys.argv[3] if len(sys.argv) > 3 else ""

    if not _EPIC:
        emit(reason="no epic supplied to select-next-story (epic selection is select-next-epic.py)")

    root = find_docs_root(docs_path_arg)
    skip = _load_skip_set(root, run_dir_arg)

    nxt = _next_story(root, _EPIC)
    # If ostler handed back a story we already gave up THIS run (its status marking
    # didn't take), don't re-select it — force the skip-aware json selection to look
    # for the next eligible story instead of re-grinding this one.
    forced_by_skip = isinstance(nxt, dict) and str(nxt.get("slug", "")) in skip
    if forced_by_skip:
        nxt = ""

    # Fall back to dependencies.json when ostler is unavailable, returns nothing useful,
    # or handed back a skipped story (forced_by_skip).
    if nxt == "" or nxt is None:
        json_nxt = _next_from_json(root, _EPIC, skip)
        if isinstance(json_nxt, dict) and json_nxt.get("_no_dep_file"):
            if forced_by_skip:
                emit(reason=f"only runnable story in epic '{_EPIC}' was given up this run — "
                            "stopping to avoid re-grinding; start a new run or clear the skip set to retry")
            emit(reason=f"no dependencies.json found for epic '{_EPIC}' — cannot select a story")
        if isinstance(json_nxt, dict) and json_nxt.get("_all_skipped"):
            emit(reason=f"remaining runnable stories in epic '{_EPIC}' were all given up this run — "
                        "stopping; start a new run or clear the skip set to retry")
        if isinstance(json_nxt, dict) and json_nxt.get("_missing_story_md"):
            emit(reason=f"next story's story.md not found: {json_nxt['_missing_story_md']}")
        if isinstance(json_nxt, dict) and "slug" in json_nxt:
            nxt = json_nxt
        elif json_nxt is None:
            nxt = None  # all done

    if not nxt:
        if forced_by_skip:
            emit(reason=f"remaining runnable stories in epic '{_EPIC}' were all given up this run — "
                        "stopping; start a new run or clear the skip set to retry")
        emit(reason=f"no runnable story in epic '{_EPIC}' — all done or none authored")

    slug = str(nxt.get("slug"))
    # Final guard: never hand back a story in this run's skip set (the fallback already
    # excludes them, so this only fires if a selection path regressed).
    if slug in skip:
        emit(reason=f"story '{slug}' was given up this run — stopping to avoid re-grinding; "
                    "start a new run or clear the skip set to retry")
    spec_dir = _ostler_path(root, "spec", slug) or f"docs/specs/{slug}"
    story_path = str(nxt.get("path") or "")

    emit(
        has_story="yes",
        story_path=story_path,
        spec_dir=spec_dir,
        story_slug=slug,
        epic=_EPIC,
    )


if __name__ == "__main__":
    main()
