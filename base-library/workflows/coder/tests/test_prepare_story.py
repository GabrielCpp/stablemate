"""prepare-story.py — path convergence, and the fail-closed gate on an unauthored story.

Every route into the dev phase (story mode and epic mode) passes through this node, which
makes it the one place coder can refuse an empty story before an agent starts inventing its
requirements. The author run that produced 44 bare `ostler create story` scaffolds would
otherwise have been planned, implemented and QA'd story by story, each one's acceptance
criteria conjured by the planner — work that looks finished and matches nothing anyone asked
for. "Authored" here is ostler's verdict (``Story.authored``), the same fact the author
workflow's gates and ``ostler doctor``'s ``unwritten-story`` finding read.

The guard is deliberately narrow: it fires only when the graph *knows* the story and says it
is unwritten. A graph that will not load, or a slug outside the epics tree, is a different
situation — story mode supports it — and must still resolve paths, which the last two tests
pin down.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from ostler import Ostler

SCRIPTS = Path(__file__).parent.parent / "scripts"


def _run(root: Path, slug: str, epic: str = "") -> subprocess.CompletedProcess:
    """Invoke prepare-story.py the way its node does: (docs_path, story_slug, epic)."""
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "prepare-story.py"), str(root), slug, epic],
        capture_output=True,
        text=True,
        cwd=str(root),
        env={**os.environ, "AGENT_REPO_DIR": str(root)},
    )


def _authored_body(root: Path, epic: str, slug: str) -> Path:
    """Fill the scaffold's required sections — what an author run is supposed to leave behind."""
    story_md = root / "docs/epics" / epic / "stories" / slug / "story.md"
    text = story_md.read_text(encoding="utf-8")
    text = text.replace(
        "## Context\n",
        "## Context\n\n- the operator needs to see yesterday's totals\n",
    ).replace(
        "## Acceptance Criteria\n",
        "## Acceptance Criteria\n\n- The dashboard shows a total for each of the last 7 days.\n",
    )
    story_md.write_text(text, encoding="utf-8")
    return story_md


def _epic_with_story(root: Path, epic: str = "epic-1", slug: str = "s-1") -> None:
    okf = Ostler(root)
    assert okf.create_epic(epic, "Epic One").ok
    assert okf.create_story(epic, slug, "Story One").ok


def test_bare_scaffold_is_refused(tmp_path):
    """The incident, from coder's side: a story.md that is all headings and no content.

    Exit 2 (not a swallowed warning) is what keeps the run from reaching `plan` — and the
    empty sections are named, because "not authored" alone does not tell the operator whether
    to rerun the author workflow or fix one story by hand.
    """
    _epic_with_story(tmp_path)

    proc = _run(tmp_path, "s-1", "epic-1")

    assert proc.returncode == 2, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "not authored" in proc.stderr
    assert "Context" in proc.stderr and "Acceptance Criteria" in proc.stderr
    assert not proc.stdout.strip(), "a refused story must emit no paths for the planner to use"


def test_missing_story_md_is_refused(tmp_path):
    """The other unauthored shape: the epic lists the story, but no story.md was ever written."""
    _epic_with_story(tmp_path)
    story_md = tmp_path / "docs/epics/epic-1/stories/s-1/story.md"
    story_md.unlink()

    proc = _run(tmp_path, "s-1", "epic-1")

    assert proc.returncode == 2, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "story.md is missing" in proc.stderr


def test_authored_story_resolves_its_paths(tmp_path):
    """The gate must not cost the happy path: a written story resolves as before."""
    _epic_with_story(tmp_path)
    _authored_body(tmp_path, "epic-1", "s-1")

    proc = _run(tmp_path, "s-1", "epic-1")

    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    out = json.loads(proc.stdout)
    assert out["story_slug"] == "s-1"
    assert out["story_epic"] == "epic-1"
    assert out["story_path"].endswith("docs/epics/epic-1/stories/s-1/story.md")
    assert out["qa_dir"] == out["spec_dir"] + "/qa"


def test_a_story_outside_the_graph_still_resolves(tmp_path):
    """Story mode may target a story the graph does not know — that is not an unauthored story.

    The guard can only speak about stories ostler can see; treating "not in the graph" as
    unauthored would break every sandbox and every hand-placed story, so it stays silent and
    the path fallbacks below it do the work.
    """
    story_md = tmp_path / "docs/epics/epic-1/stories/loose/story.md"
    story_md.parent.mkdir(parents=True)
    story_md.write_text("# Story: loose\n\n- **Status**: In progress\n", encoding="utf-8")

    proc = _run(tmp_path, "loose", "epic-1")

    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    out = json.loads(proc.stdout)
    assert out["story_path"].endswith("docs/epics/epic-1/stories/loose/story.md")


def test_no_slug_is_a_no_op(tmp_path):
    """Called with no story (the mode that has not selected one yet) → empty paths, exit 0."""
    proc = _run(tmp_path, "", "")

    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert json.loads(proc.stdout)["story_path"] == ""
