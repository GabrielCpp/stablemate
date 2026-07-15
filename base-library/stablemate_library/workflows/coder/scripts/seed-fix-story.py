#!/usr/bin/env python3
"""Register ONE drained backlog bullet as a single-AC story in the `fixes` bucket — ostler-backed.

Twin of `author/scripts/seed-story.py`, adapted for the coder fix loop:

- Story mode's `seed-story.py` hard-fails if its target epic doesn't already exist (an operator
  must have created it). The fix loop has no such operator step — it self-creates a small,
  perpetual `fixes` epic bucket the first time it's needed (idempotent: an "already exists"
  result from `ostler create epic` is treated as success, not an error). This bucket is never
  registered in the epics queue (`ostler todo add`) that `select_epic`/`prune_epic` manage, so it
  never collides with or gets picked up by epic-mode story selection.
- The bullet id/text are handed in directly by `select-next-fix-item.py`'s output (it already did
  the backlog scan), so there's no `resolve_bullet()` re-parse step here.
- `ostler create story` scaffolds an empty `## Acceptance Criteria` section; this script fills it
  with the bullet text as the SINGLE AC line — the literal enactment of "1 fix = 1 AC."

Idempotent / resumable: if a story already covers the bullet id, that story is reused rather than
created again (and its AC section is left alone if already populated).

Stdlib-only except for shelling out to the globally-installed `ostler` CLI.

Args:
    argv[1]  bullet_id    : the backlog item id (required, from select-next-fix-item.py)
    argv[2]  bullet_text  : the backlog item text (required, from select-next-fix-item.py)
    argv[3]  epics_dir    : repo-relative epics root (default docs/epics)
    argv[4]  epic         : the fix-stories epic bucket name (default "fixes")
    argv[5]  docs_path    : optional explicit docs root override (passed to find_docs_root)

Outputs JSON: {"epic": "...", "epic_dir": "...", "story_slug": "...", "story_dir": "...",
               "story_path": "...", "bullet_id": "...", "reason": "..."}
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from workhorse.scriptutil import find_docs_root


def die(msg: str) -> None:
    sys.stderr.write(f"seed-fix-story: {msg}\n")
    sys.exit(2)


def _ostler() -> str:
    ostler = shutil.which("ostler")
    if not ostler:
        die("ostler CLI not found on PATH — seed-fix-story needs it to mutate the fixes epic")
    return ostler


def ostler_run(root: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([_ostler(), *args], cwd=str(root), capture_output=True,
                          text=True, timeout=120)


def ostler_json(root: Path, args: list[str], opener: str):
    try:
        proc = ostler_run(root, args)
    except (OSError, subprocess.SubprocessError):
        return None
    raw = (proc.stdout or "").strip()
    start = raw.find(opener)
    if start == -1:
        return [] if opener == "[" else None
    try:
        return json.JSONDecoder().raw_decode(raw[start:])[0]
    except (json.JSONDecodeError, ValueError):
        return None


def kebab(text: str, *, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "fix"


def emit(**kwargs: str) -> None:
    payload = {
        "epic": "", "epic_dir": "", "story_slug": "", "story_dir": "", "story_path": "",
        "bullet_id": "", "reason": "",
    }
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def ensure_fixes_epic(root: Path, epics_dir_rel: str, epic: str) -> None:
    epic_dir = root / epics_dir_rel / epic
    if (epic_dir / "epic.md").is_file():
        return
    res = ostler_json(root, ["create", "epic", epic, "--title", "Coder-filed fixes", "--json"], "{")
    if res and res.get("ok"):
        return
    # Idempotent: a concurrent/prior run may have created it between our check and this call.
    if (epic_dir / "epic.md").is_file():
        return
    msg = (res or {}).get("message", "unknown error")
    die(f"could not self-create the '{epic}' epic bucket: {msg}")


def inject_ac_line(story_path: Path, bullet_text: str) -> None:
    """Fill the freshly-scaffolded empty `## Acceptance Criteria` section with the bullet text
    as the single AC line — a no-op if the section already has content (idempotent re-run)."""
    try:
        text = story_path.read_text(encoding="utf-8")
    except OSError:
        return
    heading = "## Acceptance Criteria"
    idx = text.find(heading)
    if idx == -1:
        return
    after = idx + len(heading)
    rest = text[after:]
    next_heading = re.search(r"\n## ", rest)
    section_body = rest[:next_heading.start()] if next_heading else rest
    if section_body.strip():
        return  # already populated — leave it alone
    replacement = f"\n\n- {bullet_text}\n"
    if next_heading:
        new_rest = replacement + "\n" + rest[next_heading.start() + 1:]
    else:
        new_rest = replacement
    story_path.write_text(text[:after] + new_rest, encoding="utf-8")


def main() -> None:
    bullet_id = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    bullet_text = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else ""
    epics_dir_rel = (sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3] else "") or "docs/epics"
    epic = (sys.argv[4].strip() if len(sys.argv) > 4 and sys.argv[4] else "") or "fixes"
    docs_path_arg = sys.argv[5] if len(sys.argv) > 5 else ""

    if not bullet_id:
        die("no bullet_id supplied (expected select-next-fix-item.py's fix_bullet_id output)")
    if not bullet_text:
        die("no bullet_text supplied (expected select-next-fix-item.py's fix_bullet_text output)")

    root = find_docs_root(docs_path_arg)
    epic_dir_rel = f"{epics_dir_rel}/{epic}"

    ensure_fixes_epic(root, epics_dir_rel, epic)

    # Idempotent: if a story already covers this id, reuse it (resumable rerun).
    stories = ostler_json(root, ["list", "--type", "story", "--epic", epic, "--json"], "[") or []
    for s in stories:
        if bullet_id in (s.get("covers") or []):
            slug = str(s.get("slug", ""))
            path = str(s.get("path", "")) or f"{epic_dir_rel}/stories/{slug}/story.md"
            story_path = root / path
            inject_ac_line(story_path, bullet_text)
            emit(epic=epic, epic_dir=epic_dir_rel, story_slug=slug,
                 story_dir=str(Path(path).parent), story_path=path, bullet_id=bullet_id,
                 reason=f"story '{slug}' already covers '{bullet_id}' — reusing (idempotent)")

    ostler_run(root, ["seed", "add", epic, bullet_id, "--status", "researched",
                      "--summary", bullet_text, "--source-bullet", bullet_text])

    slug = kebab(bullet_text)
    res = ostler_json(root, ["create", "story", epic, slug, "--title", bullet_text,
                             "--covers", bullet_id, "--json"], "{")
    if not res or not res.get("ok"):
        msg = (res or {}).get("message", "unknown error")
        die(f"`ostler create story {epic} {slug}` failed: {msg}")

    story_dir_rel = f"{epic_dir_rel}/stories/{slug}"
    story_path_rel = f"{story_dir_rel}/story.md"
    inject_ac_line(root / story_path_rel, bullet_text)

    emit(epic=epic, epic_dir=epic_dir_rel, story_slug=slug, story_dir=story_dir_rel,
         story_path=story_path_rel, bullet_id=bullet_id,
         reason=f"registered fix story '{slug}' ({res.get('id', '?')}) covering '{bullet_id}' "
                f"in '{epic}' with a single injected AC line")


if __name__ == "__main__":
    main()
