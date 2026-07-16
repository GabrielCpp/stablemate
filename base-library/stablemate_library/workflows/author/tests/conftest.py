"""Shared fixtures/helpers for author-workflow script tests (OKF / ostler model).

The author workflow's correctness lives in its deterministic Python scripts
(selectors + validators). Under the OKF model the planning graph is on-disk Markdown that
the globally-installed ``ostler`` CLI reads back — there is no ``seed.json`` /
``dependencies.json`` / ``epics-todo.json`` / ``inventory.json`` anymore. So these tests
build a real Markdown repo fixture (``epic.md`` + ``index.md`` + ``story.md`` + knowledge /
feature Concepts + ``backlog.md`` + a root marker so root-detection works), then run each
script as a subprocess with ``AGENT_REPO_DIR`` pointed at it — the same way the local-worker
runs them — and assert on the emitted JSON.

The ostler-backed scripts shell out to the real ``ostler`` CLI; the helpers below produce the
exact Markdown ostler parses, so the tests are true integration tests against the installed
binary. A fixture that ostler can load needs the ``docs/epics`` layout and a root marker
(``agents.yml`` or ``.git``), both of which :func:`init_repo` writes.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"

# Skip the ostler-backed integration tests if the CLI isn't installed (the deterministic,
# stdlib-only scripts — validate-story, reconcile-artifacts — don't need it and never skip).
requires_ostler = pytest.mark.skipif(
    shutil.which("ostler") is None, reason="ostler CLI not installed"
)


def run_script(name: str, *args: str, repo: Path) -> dict:
    """Run scripts/<name> with AGENT_REPO_DIR=repo; return parsed JSON stdout.

    Raises AssertionError (with stderr) if the script exits non-zero or its stdout
    is not JSON — both are real failures for the nodes that consume these scripts.
    """
    env = dict(os.environ, AGENT_REPO_DIR=str(repo))
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, f"{name} exited {proc.returncode}\nstderr:\n{proc.stderr}"
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:  # pragma: no cover - failure path
        raise AssertionError(f"{name} stdout not JSON: {e}\nstdout:\n{proc.stdout}")


def run_script_raw(
    name: str,
    *args: str,
    repo: Path,
    timeout: float | None = None,
) -> subprocess.CompletedProcess:
    """Run scripts/<name> and return the raw CompletedProcess (for exit-code tests)."""
    env = dict(os.environ, AGENT_REPO_DIR=str(repo))
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        capture_output=True, text=True, env=env, timeout=timeout,
    )


def init_repo(repo: Path) -> None:
    """Lay down the minimum a fixture repo needs: a root marker + the docs/epics layout.

    ``agents.yml`` (and the ``docs/epics`` dir) are what the scripts' ``find_repo_root`` and
    ostler key off, so this makes ``repo`` a loadable graph root even before any epic exists.
    """
    (repo / "agents.yml").write_text("name: testrepo\n", encoding="utf-8")
    (repo / "docs" / "epics").mkdir(parents=True, exist_ok=True)


# ── Markdown fixture builders (the on-disk forms ostler parses) ───────────────────────────

def _front_matter(fields: dict) -> str:
    lines = ["---"]
    for k, v in fields.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


GOOD_STORY_BODY = """\
## Context

Bring the {slug} surface to parity with the legacy reference editor. Done means the page
renders and behaves like the legacy editor for a signed-in user.

## Acceptance Criteria

- Typing in one field changes only that field; checking one box checks only that box.
- Section titles and field labels show the translated names, not internal codes.
- The page shows the same sections, navigation, and controls as the legacy editor.

## Implementation Status

- **Status**: Not started
"""


def write_story(repo: Path, epic: str, slug: str, *, body: str | None = None,
                status: str = "not_started") -> Path:
    """Write a ``story.md`` (good minimal contract by default) and return its repo-relative dir.

    ``body`` (when given) is the FULL story markdown after the front-matter; otherwise the good
    template is used. Returns the repo-relative ``docs/epics/<epic>/stories/<slug>`` path.
    """
    story_dir = repo / "docs" / "epics" / epic / "stories" / slug
    story_dir.mkdir(parents=True, exist_ok=True)
    fm = _front_matter({"type": "story", "slug": slug, "status": status})
    content = body if body is not None else (
        f"{fm}\n\n# Story: {slug}\n\n" + GOOD_STORY_BODY.format(slug=slug)
    )
    (story_dir / "story.md").write_text(content, encoding="utf-8")
    return Path("docs/epics") / epic / "stories" / slug


def write_epic(repo: Path, epic: str, *, seeds: list[dict], stories: list[dict],
               title: str | None = None, queue: bool = True) -> Path:
    """Write an ``epic.md`` (and queue it in ``index.md``) + each story's ``story.md``.

    ``seeds`` entries: {id, status?, surface?, legacySurface?, sourceBullet?, summary?}.
    ``stories`` entries: {slug, id?, title?, covers?(list), deps?(list), write?(bool, default
    True), body?, status?}. A story with ``write: False`` is listed in ``## Stories`` but its
    ``story.md`` is not created (the partial-run case).

    Returns the repo-relative epic dir.
    """
    init_repo(repo)
    epic_dir = repo / "docs" / "epics" / epic
    epic_dir.mkdir(parents=True, exist_ok=True)

    parts: list[str] = [
        _front_matter({"type": "epic", "id": f"E-{epic}", "title": title or epic,
                       "status": "in_progress"}),
        "",
        f"# {title or epic}",
        "",
        "## Seeds",
        "",
    ]
    for s in seeds:
        sid = s["id"]
        parts.append(f"### {sid}")
        parts.append("")
        parts.append(f"- status: {s.get('status', 'researched')}")
        if s.get("surface"):
            parts.append(f"- surface: {s['surface']}")
        if s.get("legacySurface"):
            parts.append(f"- legacySurface: {s['legacySurface']}")
        parts.append(f"- sourceBullet: {s.get('sourceBullet', sid)}")
        parts.append("")
        parts.append(s.get("summary", f"Summary of {sid}."))
        parts.append("")

    parts.append("## Stories")
    parts.append("")
    for st in stories:
        slug = st["slug"]
        covers = st.get("covers", [])
        deps = st.get("deps", [])
        parts.append(f"### {slug}")
        parts.append("")
        parts.append(f"- title: {st.get('title', slug)}")
        parts.append(f"- id: {st.get('id', 'S-' + slug)}")
        parts.append(f"- covers: {', '.join(covers) if covers else '(none)'}")
        parts.append(f"- depends on: {', '.join(deps) if deps else '(none)'}")
        parts.append("")

    (epic_dir / "epic.md").write_text("\n".join(parts) + "\n", encoding="utf-8")

    for st in stories:
        if st.get("write", True):
            write_story(repo, epic, st["slug"], body=st.get("body"),
                        status=st.get("status", "not_started"))

    if queue:
        write_queue(repo, [epic], title_by={epic: title or epic}, append=True)

    return Path("docs/epics") / epic


def write_queue(repo: Path, epics: list[str], *, title_by: dict | None = None,
                append: bool = False) -> None:
    """Write/extend the epics queue ``docs/epics/index.md`` (ostler ``todo list``)."""
    title_by = title_by or {}
    index = repo / "docs" / "epics" / "index.md"
    index.parent.mkdir(parents=True, exist_ok=True)

    existing: list[str] = []
    if append and index.is_file():
        existing = index.read_text(encoding="utf-8").splitlines()

    lines = existing if existing else ["# Epics", ""]
    listed = "\n".join(lines)
    for e in epics:
        bullet = f"- [{e}]({e}/epic.md) — {title_by.get(e, e)}"
        if f"]({e}/epic.md)" not in listed:
            lines.append(bullet)
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_knowledge(repo: Path, surface_slug: str, *, area: str = "area",
                    route: str | None = None,
                    journeys: list | None = None, sources: list | None = None,
                    knowledge_dir: str = "docs/knowledge") -> Path:
    """Write a knowledge Concept (markdown + YAML front-matter). Returns repo-relative path."""
    rec_path = repo / knowledge_dir / area / f"{surface_slug}.md"
    rec_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["---", "type: knowledge", f"surface: {area}/{surface_slug}"]
    if route:
        lines.append(f"route: {route}")
    if journeys is not None:
        if not journeys:
            lines.append("journeys: []")
        else:
            lines.append("journeys:")
            for j in journeys:
                name = j.get("name", j.get("id", "journey")) if isinstance(j, dict) else str(j)
                lines.append(f"  - name: {name}")
    if sources is not None:
        lines.append("provenance:")
        lines.append("  iteration: 1")
        lines.append("  sourcesRead:")
        for s in sources:
            lines.append(f"    - {s}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Surface knowledge: {area}/{surface_slug}")

    rec_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return Path(knowledge_dir) / area / f"{surface_slug}.md"


def write_feature(repo: Path, slug: str, *, area: str = "area", title: str | None = None,
                  route: str | None = None, features_dir: str = "docs/features") -> Path:
    """Write a feature Concept (markdown + YAML front-matter). Returns repo-relative path."""
    p = repo / features_dir / area / f"{slug}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = {"type": "feature", "slug": slug, "area": area, "title": title or slug.title()}
    if route:
        fm["route"] = route
    p.write_text(f"{_front_matter(fm)}\n\n# {title or slug}\n", encoding="utf-8")
    return Path(features_dir) / area / f"{slug}.md"


def write_backlog(repo: Path, ids: list[str], *, texts: dict | None = None,
                  path: str = "docs/backlog.md") -> None:
    """Write a backlog file with one ``- [id] <text>`` bullet per id."""
    texts = texts or {}
    backlog = repo / path
    backlog.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Backlog", ""] + [f"- [{i}] {texts.get(i, 'do ' + i)}" for i in ids]
    backlog.write_text("\n".join(lines) + "\n", encoding="utf-8")
