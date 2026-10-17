"""An old seed keeps its spec folders by slug; a trial upgrades the layout when it unpacks one."""

from __future__ import annotations

import subprocess
from pathlib import Path

from test_materialize_tracked_copy import frozenapp

STORY_ID = "ONLY-01KZH7X2Y5C8VNQ0J3RTB6MFAW"


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def _old_layout(root: Path, *, agents: str | None = "name: demo\n") -> Path:
    story = root / "docs" / "epics" / "0001-demo" / "stories" / "only-story"
    story.mkdir(parents=True)
    (root / "docs" / "epics" / "0001-demo" / "epic.md").write_text(
        f"---\ntype: epic\nid: ONLY-01KZH7WQXB4SFVN2R6TDMK9JE0\ntitle: x\nstatus: planned\n---\n# Epic: x\n\n## Stories\n\n### only-story\n- title: x\n- id: {STORY_ID}\n- covers: (none)\n",
        encoding="utf-8",
    )
    (story / "story.md").write_text(
        f"---\ntype: story\nid: {STORY_ID}\nslug: only-story\nstatus: Not started\n---\n# Story: x\n\n## Dependencies\n\n(none)\n\n## Fixtures\n\n(none)\n\n## Context\n\nx\n",
        encoding="utf-8",
    )
    (root / "docs" / "specs" / "only-story").mkdir(parents=True)
    (root / "docs" / "specs" / "only-story" / "spec.md").write_text("spec\n", encoding="utf-8")
    if agents is not None:
        (root / "agents.yml").write_text(agents, encoding="utf-8")
    return root


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


def test_upgrade_moves_a_slug_folder_to_its_id_and_configures_the_root(tmp_path: Path) -> None:
    repo = _old_layout(tmp_path / "repo")

    frozenapp.upgrade_spec_layout(repo)

    assert frozenapp.spec_dir(repo, "only-story") == repo / "docs" / "specs" / STORY_ID
    assert (repo / "docs" / "specs" / STORY_ID / "spec.md").is_file()
    assert not (repo / "docs" / "specs" / "only-story").exists()
    assert "name: demo" in (repo / "agents.yml").read_text(encoding="utf-8")


def test_upgrade_creates_the_config_when_the_repo_has_none(tmp_path: Path) -> None:
    repo = _old_layout(tmp_path / "repo", agents=None)

    frozenapp.upgrade_spec_layout(repo)

    assert (repo / "docs" / "specs" / STORY_ID).is_dir()


def test_upgrade_merges_into_an_existing_organization_block(tmp_path: Path) -> None:
    repo = _old_layout(tmp_path / "repo", agents="organization:\n  docRoots:\n    epics: docs/epics\n")

    frozenapp.upgrade_spec_layout(repo)

    text = (repo / "agents.yml").read_text(encoding="utf-8")
    assert "epics: docs/epics" in text
    assert "specs: docs/specs" in text
    assert (repo / "docs" / "specs" / STORY_ID).is_dir()


def test_a_second_upgrade_changes_nothing(tmp_path: Path) -> None:
    repo = _old_layout(tmp_path / "repo")
    frozenapp.upgrade_spec_layout(repo)
    before = _snapshot(repo)

    frozenapp.upgrade_spec_layout(repo)

    assert _snapshot(repo) == before


def test_a_repo_without_in_repo_specs_is_untouched(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "agents.yml").write_text("name: demo\n", encoding="utf-8")
    before = _snapshot(repo)

    frozenapp.upgrade_spec_layout(repo)

    assert _snapshot(repo) == before


def test_materialize_accepts_an_old_layout_seed(tmp_path: Path) -> None:
    app = _old_layout(tmp_path / "app")
    (app / "stories" / "only-story").mkdir(parents=True)
    (app / "stories" / "only-story" / "diff.yml").write_text(
        "changed: []\nadded: []\npinned: []\n", encoding="utf-8"
    )
    _git("init", "--quiet", "--initial-branch", "main", cwd=app)
    _git("add", "--all", cwd=app)
    _git("commit", "--quiet", "-m", "app", cwd=app)

    dest = frozenapp.materialize(app, "only-story", tmp_path / "dest")

    assert (dest / "docs" / "specs" / STORY_ID / "spec.md").is_file()
