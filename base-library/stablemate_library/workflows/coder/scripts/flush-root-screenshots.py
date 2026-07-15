#!/usr/bin/env python3
"""Flush stray screenshot/image files left at the repo root into ``<spec_dir>/qa/``.

QA is supposed to write every screenshot to an **absolute** path under ``<spec_dir>/qa/``.
In practice the QA agent sometimes passes a bare or cwd-relative filename to
``page.screenshot()`` / ``browser_take_screenshot`` — which resolves against the agent's
working directory (the repo root) and dumps the image there instead. Left alone, the next
``commit-story.sh`` (``git add -A``) commits the clutter into the repo root.

This deterministic node runs **right before the commit** and relocates those strays into
``<spec_dir>/qa/``, so the evidence is preserved where it belongs and the repo root stays
clean. It is intentionally conservative:

  - **only top-level** image files are considered (``maxdepth 1``) — never anything in a
    subdirectory, so real assets under ``web/``, ``docs/``, etc. are untouched.
  - **only UNTRACKED** files are moved — a tracked root image is an intentional committed
    asset and is left alone.
  - moves (never deletes): a name collision gets a ``-1``/``-2`` suffix.
  - best-effort: a missing spec_dir, a git failure, or an unmovable file degrades to a
    logged no-op — it never aborts the coder run.

Usage: flush-root-screenshots.py <spec_dir>
  <spec_dir>  repo-relative path to the story's spec directory (e.g. docs/specs/<slug>).
              Evidence goes into ``<spec_dir>/qa/``.
Outputs JSON: {"screenshots_flushed": <n>, "screenshots_kept_tracked": <n>, "notes": "..."}
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from workhorse.scriptutil import list_tracked_files

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return here


def emit(flushed: int, kept_tracked: int, notes: str) -> None:
    print(json.dumps({
        "screenshots_flushed": flushed,
        "screenshots_kept_tracked": kept_tracked,
        "notes": notes,
    }))


def tracked_names(root: Path) -> set[str]:
    """Top-level files git already tracks — left untouched. Empty set if git is unavailable
    (then nothing is treated as tracked, but the move itself is still best-effort)."""
    return {path for path in list_tracked_files(root) if "/" not in path}  # top-level only


def dest_dir(root: Path, spec_dir_arg: str) -> Path | None:
    sd = spec_dir_arg.strip()
    if not sd:
        return None
    candidate = (root / sd)
    # Guard against a blank/garbage path resolving to (or above) the repo root.
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate == root:
        return None
    return candidate / "qa"


def unique_target(dest: Path, name: str) -> Path:
    target = dest / name
    if not target.exists():
        return target
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 1
    while (dest / f"{stem}-{n}{suffix}").exists():
        n += 1
    return dest / f"{stem}-{n}{suffix}"


def main() -> None:
    spec_dir_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    root = find_repo_root()

    strays = sorted(
        p for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    if not strays:
        emit(0, 0, "no stray images at repo root")
        return

    tracked = tracked_names(root)
    untracked = [p for p in strays if p.name not in tracked]
    kept_tracked = len(strays) - len(untracked)
    if not untracked:
        emit(0, kept_tracked, f"{kept_tracked} root image(s) are tracked assets — left in place")
        return

    dest = dest_dir(root, spec_dir_arg)
    if dest is None:
        emit(0, kept_tracked,
             f"could not resolve qa dir from spec_dir — left {len(untracked)} stray image(s) in place")
        return

    flushed = 0
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[flush-root-screenshots] could not create {dest}: {e}", file=sys.stderr)
        emit(0, kept_tracked, f"could not create qa dir — left {len(untracked)} stray image(s) in place")
        return

    for src in untracked:
        try:
            src.rename(unique_target(dest, src.name))
            flushed += 1
        except OSError as e:
            print(f"[flush-root-screenshots] could not move {src.name}: {e}", file=sys.stderr)

    rel = dest.relative_to(root)
    note = f"moved {flushed} stray image(s) to {rel}"
    if kept_tracked:
        note += f"; left {kept_tracked} tracked root image(s) in place"
    emit(flushed, kept_tracked, note)


if __name__ == "__main__":
    main()
