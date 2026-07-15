"""Direct tests for scripts/init-base.py.

init-base captures the PR / merge TARGET (the trunk). Regression: a prior,
unfinished run leaves HEAD on its ``feat/<epic>`` branch; a fresh run started
from that checkout must NOT capture the epic branch as the base (that makes
``gh pr create --base feat/<epic> --head feat/<epic>`` fail with base==head
and silently no-ops the open-PR / merge gate). These tests run the script against
a real temp git repo, since the workflow harness's git mock dispatches only on the
subcommand and can't tell ``rev-parse --abbrev-ref HEAD`` from ``rev-parse --verify``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "init-base.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_repo(tmp_path: Path, trunk: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", trunk)
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    (repo / "agents.yml").write_text("repo: {}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def _run(repo: Path) -> str:
    out = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=repo,
        env={"PATH": "/usr/bin:/bin", "AGENT_REPO_DIR": str(repo)},
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.stdout)["base_branch"]


def test_base_is_current_trunk_branch(tmp_path):
    repo = _init_repo(tmp_path, "master")
    assert _run(repo) == "master"


def test_epic_branch_resolves_to_trunk(tmp_path):
    """HEAD left on a feat/<epic> branch must resolve back to the trunk."""
    repo = _init_repo(tmp_path, "master")
    _git(repo, "checkout", "-q", "-b", "feat/live-fidelity")
    assert _run(repo) == "master"


def test_epic_branch_resolves_to_main_when_thats_trunk(tmp_path):
    repo = _init_repo(tmp_path, "main")
    _git(repo, "checkout", "-q", "-b", "feat/some-epic")
    assert _run(repo) == "main"


def test_legacy_rewrite_branch_still_resolves_to_trunk(tmp_path):
    """Leftover pre-rename rewrite/<epic> branches must also resolve to trunk."""
    repo = _init_repo(tmp_path, "master")
    _git(repo, "checkout", "-q", "-b", "rewrite/old-epic")
    assert _run(repo) == "master"
