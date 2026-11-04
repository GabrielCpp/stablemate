"""Every flow of every installed workflow dry-runs green with no launch parameter, and leaves the repository it ran in exactly as it found it."""
from __future__ import annotations

import hashlib
import importlib
import os
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path

import pytest
from workhorse.pyflow import Registry
from workhorse.references import missing_references
from workhorse.templates import turn_catalog

DRY_RUN_SECONDS = 60
REFRESHED_BY_GIT = Path(".git/index")


def _flows() -> list[tuple[str, str]]:
    """(module, flow) for the entry flow and each sub-flow of every workflow the distribution installs a command for."""
    found: list[tuple[str, str]] = []
    for script in distribution("workhorse-workflows").entry_points.select(group="console_scripts"):
        registry = getattr(importlib.import_module(script.module), "workflow", None)
        if isinstance(registry, Registry):
            found.extend((script.module, flow) for flow in registry.flow_names())
    return found


def _tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "folder"
        for path in root.rglob("*")
        if path.relative_to(root) != REFRESHED_BY_GIT
    }


def _install_skills_prompts_name(module: str, home: Path, repo: Path) -> None:
    """Stand in for `farrier install`, which a dry run requires and this test does not exercise."""
    registry = importlib.import_module(module).workflow
    for missing in missing_references(registry.directory(), turn_catalog(repo)):
        skill = home / ".claude/skills" / missing.name / "SKILL.md"
        skill.parent.mkdir(parents=True, exist_ok=True)
        _ = skill.write_text(f"---\nname: {missing.name}\ndescription: stub\n---\n", encoding="utf-8")


def _git(repo: Path, *args: str) -> None:
    _ = subprocess.run(["git", "-c", "user.name=seed", "-c", "user.email=seed@example.com", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def seeded_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "kept.txt").write_text("the tree a dry run must not touch\n", encoding="utf-8")
    _git(repo, "add", "kept.txt")
    _git(repo, "commit", "-qm", "seed")
    return repo


@pytest.mark.parametrize(("module", "flow"), _flows())
def test_a_bare_dry_run_passes_and_touches_nothing(module: str, flow: str, seeded_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before = _tree(seeded_repo)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    _install_skills_prompts_name(module, home, seeded_repo)
    env = {key: value for key, value in os.environ.items() if not key.startswith(("AGENT_", "WORKHORSE_"))}
    launch = f"from {module} import main; main()"

    done = subprocess.run(
        [sys.executable, "-c", launch, "run", flow, "--dry-run", "--runs-dir", str(tmp_path / "runs")],
        cwd=seeded_repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=DRY_RUN_SECONDS,
        check=False,
    )

    said = done.stdout + done.stderr
    assert done.returncode == 0, said
    assert "dry-run ok" in done.stdout, said
    assert _tree(seeded_repo) == before
