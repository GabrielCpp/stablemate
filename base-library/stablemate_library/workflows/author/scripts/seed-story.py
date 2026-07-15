#!/usr/bin/env python3
"""Register ONE bullet as a new story inside an already-existing epic (story mode) — ostler-backed.

The ``author`` workflow's story mode authors a single story against an epic the operator chose,
instead of decomposing a whole backlog. This script is the setup node: it adds one seed to the
epic's ``epic.md`` (``ostler seed add``) and one story to its ``## Stories`` (``ostler create
story``, which scaffolds the ``story.md`` and allocates the id) — so the existing per-story
pipeline (gather → write → validate) runs unchanged. It does NOT re-run story-split, so sibling
stories are untouched. There is no ``seed.json`` / ``dependencies.json`` — seeds and the story DAG
fold into ``epic.md`` and ostler owns the mutation + id allocation.

Bullet resolution: if ``bullet`` matches an existing ``- [id] …`` line in the backlog, its id +
verbatim text are reused (and ``from_backlog`` is set so the tail can prune it); otherwise
``bullet`` is treated as literal text and a stable kebab id is derived from it.

Idempotent / resumable: if a story already covers the resolved id, that story is reused rather
than created again.

Story mode appends to an EXISTING epic; it never creates one. A missing epic (no ``epic.md``) is a
hard, non-zero exit with an actionable message.

Stdlib-only except for shelling out to the globally-installed ``ostler`` CLI.

Args:
    argv[1]  epic          : target epic slug (required)
    argv[2]  epics_dir      : repo-relative epics root (default docs/epics)
    argv[3]  bullet         : a backlog `[id]` or literal bullet text (required)
    argv[4]  knowledge_dir  : repo-relative knowledge root (reserved; unused)

Outputs JSON: {"epic_dir": "...", "story_slug": "...", "story_dir": "...",
               "story_path": "...", "bullet_id": "...", "from_backlog": "yes"|"no",
               "reason": "..."}
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Same backlog scope-item contract the coverage validator uses: `- [id] …`.
BACKLOG_ID_RE = re.compile(r"^\s*-\s*\[([A-Za-z0-9][A-Za-z0-9._-]*)\]\s*(.*)$")


def die(msg: str) -> None:
    """Hard-fail story setup with an actionable message (wrong/missing invocation target)."""
    sys.stderr.write(f"seed-story: {msg}\n")
    sys.exit(2)


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def _ostler() -> str:
    ostler = shutil.which("ostler")
    if not ostler:
        die("ostler CLI not found on PATH — story mode needs it to mutate the epic")
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
    """Lowercase kebab id from free text: alnum runs joined by single dashes."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "story"


def resolve_bullet(root: Path, bullet: str) -> tuple[str, str, bool]:
    """Return (id, sourceBullet, from_backlog)."""
    backlog_path = root / "docs" / "backlog.md"
    raw = bullet.strip()
    bare = raw[1:-1].strip() if raw.startswith("[") and raw.endswith("]") else raw

    if backlog_path.is_file():
        try:
            for line in backlog_path.read_text(encoding="utf-8").splitlines():
                m = BACKLOG_ID_RE.match(line)
                if not m:
                    continue
                bid, btext = m.group(1).strip(), m.group(2).strip()
                if bare == bid or raw == line.strip() or (btext and btext == raw):
                    return bid, line.strip().lstrip("-").strip(), True
        except OSError:
            pass

    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", bare):
        return bare, bare, False
    return kebab(raw), raw, False


def emit(**kwargs: str) -> None:
    payload = {
        "epic_dir": "", "story_slug": "", "story_dir": "", "story_path": "",
        "bullet_id": "", "from_backlog": "no", "reason": "",
    }
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def main() -> None:
    epic = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    epics_dir_rel = (sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else "") or "docs/epics"
    bullet = sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3] else ""

    if not epic:
        die("no epic supplied — story mode needs the target epic slug "
            "(PARAMS '{\"mode\":\"story\",\"epic\":\"<slug>\",\"bullet\":\"...\"}')")
    if not bullet:
        die("no bullet supplied — story mode needs a backlog [id] or literal bullet text "
            "(PARAMS '{\"mode\":\"story\",\"epic\":\"<slug>\",\"bullet\":\"...\"}')")

    root = find_repo_root()
    epic_dir = root / epics_dir_rel / epic
    epic_dir_rel = f"{epics_dir_rel}/{epic}"

    if not (epic_dir / "epic.md").is_file():
        die(f"epic '{epic}' does not exist at {epic_dir}/epic.md — story mode appends to an "
            "EXISTING epic and never creates one; run epic mode first or fix the epic slug")

    bullet_id, source_bullet, from_backlog = resolve_bullet(root, bullet)
    fb = "yes" if from_backlog else "no"

    # Idempotent: if a story already covers this id, reuse it (resumable rerun).
    stories = ostler_json(root, ["list", "--type", "story", "--epic", epic, "--json"], "[") or []
    for s in stories:
        if bullet_id in (s.get("covers") or []):
            slug = str(s.get("slug", ""))
            path = str(s.get("path", "")) or f"{epic_dir_rel}/stories/{slug}/story.md"
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            emit(epic_dir=epic_dir_rel, story_slug=slug, story_dir=str(Path(path).parent),
                 story_path=path, bullet_id=bullet_id, from_backlog=fb,
                 reason=f"story '{slug}' already covers '{bullet_id}' — reusing (idempotent)")

    # Add the seed to epic.md (best-effort: an already-present id is a no-op for our purpose).
    ostler_run(root, ["seed", "add", epic, bullet_id, "--status", "researched",
                      "--summary", source_bullet, "--source-bullet", source_bullet])

    # Create the story (scaffolds story.md + allocates the id via ostler).
    slug = kebab(source_bullet)
    res = ostler_json(root, ["create", "story", epic, slug, "--title", source_bullet,
                             "--covers", bullet_id, "--json"], "{")
    if not res or not res.get("ok"):
        msg = (res or {}).get("message", "unknown error")
        die(f"`ostler create story {epic} {slug}` failed: {msg}")

    story_dir_rel = f"{epic_dir_rel}/stories/{slug}"
    story_path = f"{story_dir_rel}/story.md"
    emit(epic_dir=epic_dir_rel, story_slug=slug, story_dir=story_dir_rel, story_path=story_path,
         bullet_id=bullet_id, from_backlog=fb,
         reason=f"registered story '{slug}' ({res.get('id', '?')}) covering seed item "
                f"'{bullet_id}' in epic '{epic}'")


if __name__ == "__main__":
    main()
