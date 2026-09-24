"""A turn records what it started from, so it can be started again on its own."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from _fakes import FakeBackend, FakeClock
from workhorse import gitstate
from workhorse.config_run import AgentResilience
from workhorse.context import WorkflowContext
from workhorse.runner.turn_record import parse_turn_record
from workhorse.runner import ladder
from workhorse.runner.backends import AgentProfile
from workhorse.runner.spec import AgentNode, OutputSpec
from workhorse.testing import make_git_repo


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _dirty_repo(tmp_path: Path) -> Path:
    repo = make_git_repo(tmp_path / "app")
    (repo / "README.md").write_text("# edited\n", encoding="utf-8")
    (repo / "new.txt").write_text("untracked\n", encoding="utf-8")
    (repo / ".gitignore").write_text("ignored.log\n", encoding="utf-8")
    (repo / "ignored.log").write_text("noise\n", encoding="utf-8")
    return repo


def test_snapshot_holds_edits_and_untracked_files_but_not_ignored_ones(tmp_path):
    repo = _dirty_repo(tmp_path)
    index_before = _git(repo, "ls-files", "--stage")

    start = gitstate.snapshot_tree(repo)

    assert start.head == _git(repo, "rev-parse", "HEAD")
    assert _git(repo, "show", f"{start.tree}:README.md") == "# edited"
    assert _git(repo, "show", f"{start.tree}:new.txt") == "untracked"
    assert "ignored.log" not in _git(repo, "ls-tree", "--name-only", start.tree).split()
    assert _git(repo, "ls-files", "--stage") == index_before
    assert "?? new.txt" in _git(repo, "status", "--porcelain")


def test_snapshot_outside_a_repository_names_no_tree(tmp_path):
    start = gitstate.snapshot_tree(tmp_path)

    assert (start.head, start.tree) == ("", "")


class _ScriptedRunner(ladder.AgentRunner):
    def turn(self, prompt, node_id, session_id_path, model=None, **kwargs):
        return json.dumps({"decision": "approve"})


def test_a_turn_writes_its_settings_and_start_beside_its_prompt(tmp_path):
    repo = _dirty_repo(tmp_path)
    run_dir = tmp_path / "run"
    visit_dir = run_dir / "turns" / "000-00001-review"
    node = AgentNode(
        type="agent",
        id="review",
        prompt="Review.",
        outputs=[OutputSpec(key="decision")],
        power="high",
        timeout=120,
        cwd=str(repo),
        agent=AgentProfile(name="reviewer", tools={"bash": False}, steps=12),
        next=None,
    )
    runner = _ScriptedRunner(
        backend=FakeBackend(), resilience=AgentResilience(), clock=FakeClock()
    )

    with patch.object(ladder, "render", lambda tmpl, ctx, wdir: "Rendered prompt"):
        _ = runner.run(
            node, WorkflowContext(initial={}), Path("."), None,
            run_dir=run_dir, visit_dir=visit_dir,
        )

    record = parse_turn_record((visit_dir / "turn.json").read_text(encoding="utf-8"))
    assert (visit_dir / "prompt.md").read_text(encoding="utf-8") == "Rendered prompt"
    assert (run_dir / "review" / "turn.json").read_text(encoding="utf-8") == (
        visit_dir / "turn.json"
    ).read_text(encoding="utf-8")
    assert record.node == "review"
    assert record.backend == FakeBackend().name
    assert record.power == "high"
    assert record.base_timeout_s == 120
    assert record.cwd == str(repo)
    assert record.agent == AgentProfile(name="reviewer", tools={"bash": False}, steps=12)
    assert [s.path for s in record.start] == [str(repo)]
    assert _git(repo, "show", f"{record.start[0].tree}:new.txt") == "untracked"
