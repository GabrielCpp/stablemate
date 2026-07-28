"""Story status stamping — the record every later loop iteration reads.

``ostler next-story`` (the primary selector) reads story.md's FRONTMATTER
``status:``; select-next-story.py's dependencies.json fallback reads the body's
``- **Status**:`` line. Nothing else marks a story finished — not the git log, not
the epic PR — so a story whose status is never written is re-selected, re-planned
and re-QA'd forever, and its epic never reads as complete.

Two layers:
  * ``story_status.mark`` — graph-first with the body rewrite as the fallback
    (in-process; a real ostler graph for the graph path, a bare tree for the other).
  * ``commit-story.py`` — the success path stamps ``QA passed`` and COMMITS it,
    without disturbing the ``committed`` answer the zero-diff churn guard counts.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import script_dir_on_path

SCRIPTS = Path(__file__).parent.parent / "scripts"


def _story_status():
    spec = importlib.util.spec_from_file_location("story_status", SCRIPTS / "story_status.py")
    mod = importlib.util.module_from_spec(spec)
    with script_dir_on_path(SCRIPTS):
        spec.loader.exec_module(mod)
    return mod


def _write_story(root: Path, epic: str, slug: str, body: str) -> Path:
    story_md = root / "docs" / "epics" / epic / "stories" / slug / "story.md"
    story_md.parent.mkdir(parents=True, exist_ok=True)
    story_md.write_text(body, encoding="utf-8")
    return story_md


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(root), check=True, capture_output=True, text=True
    ).stdout


def _seed_git_repo(root: Path) -> None:
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")


def _run_commit_story(root: Path, args: list[str]) -> dict:
    """Run commit-story.py as a subprocess and return its JSON output."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "commit-story.py"), *args],
        capture_output=True,
        text=True,
        cwd=str(root),
        env={**os.environ, "AGENT_REPO_DIR": str(root)},
    )
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    return json.loads(proc.stdout)


# --------------------------------------------------------------------------- #
# story_status.mark                                                           #
# --------------------------------------------------------------------------- #

def test_mark_writes_frontmatter_through_the_graph(tmp_path):
    """With a resolvable graph the status lands in FRONTMATTER — what ostler reads."""
    from ostler import Ostler

    okf = Ostler(tmp_path)
    assert okf.create_epic("epic-1", "Epic One").ok
    assert okf.create_story("epic-1", "s-1", "Story One").ok

    written = _story_status().mark(tmp_path, "s-1", "QA passed", epic="epic-1")

    assert written, "the graph path must report the paths it wrote"
    text = (tmp_path / "docs/epics/epic-1/stories/s-1/story.md").read_text(encoding="utf-8")
    assert "\nstatus: QA passed\n" in text, "frontmatter is what `ostler next-story` reads"
    assert "- **Status**: QA passed" in text, "the body line is the JSON fallback's oracle"


def test_mark_rewrites_the_body_line_without_a_graph(tmp_path):
    """No frontmatter (the workflow test sandboxes) → the body line is rewritten in place."""
    story_md = _write_story(
        tmp_path, "epic-1", "s-1", "# Story: s-1\n\n- **Status**: In progress\n"
    )

    written = _story_status().mark(tmp_path, "s-1", "QA passed", epic="epic-1")

    assert written == [story_md]
    assert story_md.read_text(encoding="utf-8") == "# Story: s-1\n\n- **Status**: QA passed\n"


def test_mark_appends_a_status_line_when_there_is_none(tmp_path):
    story_md = _write_story(tmp_path, "epic-1", "s-1", "# Story: s-1\n")

    _story_status().mark(tmp_path, "s-1", "QA passed", epic="epic-1")

    assert story_md.read_text(encoding="utf-8").endswith("- **Status**: QA passed\n")


def test_mark_prefers_an_explicit_story_path(tmp_path):
    """A story.md outside the conventional layout is still stamped (the workflow
    passes prepare_story's resolved path for exactly this case)."""
    story_md = tmp_path / "elsewhere" / "story.md"
    story_md.parent.mkdir(parents=True)
    story_md.write_text("- **Status**: In progress\n", encoding="utf-8")

    written = _story_status().mark(
        tmp_path, "s-1", "QA passed", epic="epic-1", story_path=str(story_md)
    )

    assert written == [story_md]
    assert story_md.read_text(encoding="utf-8") == "- **Status**: QA passed\n"


def test_mark_is_degraded_not_fatal_when_there_is_nothing_to_stamp(tmp_path):
    """No graph AND no story.md → report nothing written; never raise. The caller's
    own belt-and-braces (per-run skip set / commit history) still applies."""
    assert _story_status().mark(tmp_path, "s-1", "QA passed", epic="epic-1") == []


# --------------------------------------------------------------------------- #
# commit-story.py — the success path                                          #
# --------------------------------------------------------------------------- #

def test_commit_story_stamps_and_commits_qa_passed(tmp_path):
    """The story's work is committed, then the status is stamped AND committed —
    an uncommitted stamp is what makes a resumed run re-litigate a finished story."""
    story_md = _write_story(
        tmp_path, "epic-1", "s-1", "# Story: s-1\n\n- **Status**: In progress\n"
    )
    _seed_git_repo(tmp_path)
    (tmp_path / "src.txt").write_text("work\n", encoding="utf-8")

    out = _run_commit_story(tmp_path, ["epic-1", "s-1", "docs/specs/s-1", str(story_md)])

    assert out == {"committed": "yes"}
    assert "- **Status**: QA passed" in story_md.read_text(encoding="utf-8")
    assert not _git(tmp_path, "status", "--porcelain").strip(), "the stamp must be committed"
    subjects = _git(tmp_path, "log", "--format=%s").splitlines()
    assert subjects[0] == "epic-1: s-1 [QA passed]", "the stamp is its own scoped commit"
    assert subjects[1] == "epic-1: s-1", "...made AFTER the story's work commit"


def test_status_stamp_does_not_count_as_the_story_committing_work(tmp_path):
    """A no-op story still answers committed="no" even though the stamp itself
    changed and committed a file — otherwise every story would always look like it
    landed work and the zero-diff churn guard could never trip again.
    """
    story_md = _write_story(
        tmp_path, "epic-1", "s-1", "# Story: s-1\n\n- **Status**: In progress\n"
    )
    _seed_git_repo(tmp_path)  # nothing left uncommitted → the story staged no work

    out = _run_commit_story(tmp_path, ["epic-1", "s-1", "docs/specs/s-1", str(story_md)])

    assert out == {"committed": "no"}
    assert "- **Status**: QA passed" in story_md.read_text(encoding="utf-8")
    assert _git(tmp_path, "log", "--format=%s").splitlines() == [
        "epic-1: s-1 [QA passed]",
        "seed",
    ], "only the stamp commit — the story itself committed nothing"


def test_commit_story_survives_an_unstampable_story(tmp_path):
    """No graph and no story.md → the story's work still commits and the node still
    reports its answer; the missing status is logged, not raised."""
    _seed_git_repo(tmp_path)
    (tmp_path / "src.txt").write_text("work\n", encoding="utf-8")

    out = _run_commit_story(tmp_path, ["epic-1", "s-1", "docs/specs/s-1"])

    assert out == {"committed": "yes"}
    assert _git(tmp_path, "log", "--format=%s").splitlines()[0] == "epic-1: s-1"


# --------------------------------------------------------------------------- #
# flag-qa-failure.py — the give-up path                                       #
# --------------------------------------------------------------------------- #

def test_give_up_stamps_an_honest_status_never_qa_passed(tmp_path):
    """The give-up path shares the stamping module with the success path but must
    never claim a pass: dependents of a given-up story have to stay blocked.
    """
    story_md = _write_story(
        tmp_path, "epic-1", "s-1", "# Story: s-1\n\n- **Status**: In progress\n"
    )
    _seed_git_repo(tmp_path)
    run_dir = tmp_path / ".runs" / "r1"

    env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")}
    proc = subprocess.run(
        [
            sys.executable, str(SCRIPTS / "flag-qa-failure.py"),
            "epic-1", "s-1", "3", str(story_md), str(run_dir),
        ],
        capture_output=True, text=True, cwd=str(tmp_path),
        env={**env, "AGENT_REPO_DIR": str(tmp_path)},
    )

    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert json.loads(proc.stdout) == {"qa_flagged": "yes"}
    status_line = "- **Status**: QA give-up after 3 attempts — needs manual review"
    assert status_line in story_md.read_text(encoding="utf-8")
    assert not _git(tmp_path, "status", "--porcelain").strip(), "the stamp must be committed"
    assert (run_dir / "qa-skip-stories.txt").read_text(encoding="utf-8") == "s-1\n"
