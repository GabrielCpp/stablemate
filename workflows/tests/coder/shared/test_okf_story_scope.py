"""A story's QA packet owes obligations for its own changes, not for every story on the run branch."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

import pytest
from workhorse_workflows.coder.shared import okf

LOGGER = logging.getLogger("test")

PAGE = "---\ntype: concept\ntitle: {title}\n---\n# {title}\n\n- code: `app/{name}.ts`\n"


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def story_commit(root: Path, name: str, story: str) -> None:
    (root / f"app/{name}.ts").write_text(f"export const {name} = '{story}'\n", encoding="utf-8")
    git(root, "add", f"app/{name}.ts")
    git(root, "commit", "-qm", f"feat(app): change {name}\n\nStory: {story}")


@pytest.fixture
def run_branch(tmp_path: Path) -> Path:
    """A book page per file, on main, and a run branch where story acme-1 changed F."""
    root = tmp_path / "app-repo"
    (root / "docs/services/demo").mkdir(parents=True)
    (root / "app").mkdir()
    for name in ("f", "g"):
        (root / f"docs/services/demo/{name}.md").write_text(
            PAGE.format(title=name.upper(), name=name), encoding="utf-8"
        )
        (root / f"app/{name}.ts").write_text(f"export const {name} = 0\n", encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "qa@example.com")
    git(root, "config", "user.name", "QA")
    git(root, "add", ".")
    git(root, "commit", "-qm", "chore: seed")
    git(root, "checkout", "-qb", "run")
    story_commit(root, "f", "acme-1")
    return root


def packet(root: Path, story: str) -> dict[str, Any]:
    result = okf.build_okf_context(
        LOGGER,
        spec_dir=str(root / "docs/spec"),
        source_roots=("demo=app",),
        base=okf.TRUNK,
        repo_dir=str(root),
        story_refs=(story,),
    )
    assert result.status == "passed", result.notes
    return result.ostler


def owned(context: dict[str, Any]) -> set[str]:
    return {
        reason["ref"]
        for node in context["directNodes"]
        for reason in node["reasons"]
        if reason["kind"] == "file-owner"
    }


def changed(context: dict[str, Any]) -> set[str]:
    return {row["path"] for row in context["changedCode"]}


def test_a_later_story_owes_nothing_for_a_file_only_an_earlier_story_changed(
    run_branch: Path,
) -> None:
    story_commit(run_branch, "g", "acme-2")

    context = packet(run_branch, "acme-2")

    assert owned(context) == {"app/g.ts"}
    assert "app/f.ts" not in changed(context)


def test_a_later_story_that_also_changes_the_file_keeps_it(run_branch: Path) -> None:
    story_commit(run_branch, "g", "acme-2")
    story_commit(run_branch, "f", "acme-2")

    context = packet(run_branch, "acme-2")

    assert owned(context) == {"app/f.ts", "app/g.ts"}


def test_an_uncommitted_edit_belongs_to_the_story_in_progress(run_branch: Path) -> None:
    story_commit(run_branch, "g", "acme-2")
    (run_branch / "app/f.ts").write_text("export const f = 'wip'\n", encoding="utf-8")

    context = packet(run_branch, "acme-2")

    assert owned(context) == {"app/f.ts", "app/g.ts"}


def test_a_story_with_no_commit_yet_maps_only_the_worktree(run_branch: Path) -> None:
    (run_branch / "app/g.ts").write_text("export const g = 'wip'\n", encoding="utf-8")

    context = packet(run_branch, "acme-2")

    assert context["base"] == "HEAD"
    assert owned(context) == {"app/g.ts"}


@pytest.fixture
def on_trunk(run_branch: Path) -> Path:
    """Commit delivery: the stories land on main itself, so the merge base with trunk is HEAD."""
    git(run_branch, "checkout", "-q", "main")
    git(run_branch, "merge", "-q", "--ff-only", "run")
    return run_branch


def test_on_trunk_a_story_owes_obligations_for_its_own_landed_commits(on_trunk: Path) -> None:
    story_commit(on_trunk, "g", "acme-2")

    context = packet(on_trunk, "acme-1")

    assert owned(context) == {"app/f.ts"}
    assert "app/g.ts" not in changed(context)


def test_on_trunk_a_story_with_no_commit_yet_maps_only_the_worktree(on_trunk: Path) -> None:
    (on_trunk / "app/g.ts").write_text("export const g = 'wip'\n", encoding="utf-8")

    context = packet(on_trunk, "acme-2")

    assert context["base"] == "HEAD"
    assert owned(context) == {"app/g.ts"}
