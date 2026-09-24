"""A recorded turn runs again from the tree it started on, and reports what it cost."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from _fakes import FakeBackend, FakeClock
from workhorse import gitstate, otel, sessions
from workhorse.cli import replay
from workhorse.config_run import AgentResilience
from workhorse.runner import ladder
from workhorse.runner.backends import AgentProfile
from workhorse.runner.turn_record import TurnRecord
from workhorse.runner.usage import TurnUsage
from workhorse.testing import make_git_repo


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _started_repo(tmp_path: Path) -> Path:
    repo = make_git_repo(tmp_path / "app")
    (repo / ".gitignore").write_text("ignored.log\n", encoding="utf-8")
    _ = _git(repo, "add", ".gitignore")
    _ = _git(repo, "commit", "-q", "-m", "ignore")
    (repo / "README.md").write_text("# edited\n", encoding="utf-8")
    (repo / "draft.md").write_text("half a page\n", encoding="utf-8")
    return repo


def _wander(repo: Path) -> None:
    (repo / "README.md").write_text("# rewritten by the turn\n", encoding="utf-8")
    (repo / "draft.md").unlink()
    (repo / "stray.txt").write_text("left behind\n", encoding="utf-8")
    (repo / "ignored.log").write_text("noise\n", encoding="utf-8")
    _ = _git(repo, "add", "stray.txt")
    _ = _git(repo, "commit", "-q", "-m", "the turn committed")


def test_restore_puts_back_the_commit_edits_and_untracked_files(tmp_path):
    repo = _started_repo(tmp_path)
    start = gitstate.snapshot_tree(repo)
    _wander(repo)

    gitstate.restore_tree(start)

    assert _git(repo, "rev-parse", "HEAD") == start.head
    assert (repo / "README.md").read_text(encoding="utf-8") == "# edited\n"
    assert (repo / "draft.md").read_text(encoding="utf-8") == "half a page\n"
    assert not (repo / "stray.txt").exists()
    assert (repo / "ignored.log").read_text(encoding="utf-8") == "noise\n"
    assert gitstate.snapshot_tree(repo).tree == start.tree


def test_restore_refuses_a_start_with_no_commit(tmp_path):
    with pytest.raises(gitstate.RestoreError, match="no commit"):
        gitstate.restore_tree(gitstate.snapshot_tree(tmp_path))


class _ScriptedRunner(ladder.AgentRunner):
    def __init__(self, repo: Path, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.repo = repo
        self.calls: list[dict[str, Any]] = []
        self.found: list[str] = []

    def turn(self, prompt, node_id, session_id_path, model=None, **kwargs):
        self.calls.append(
            {"prompt": prompt, "node": node_id, "session": session_id_path, "model": model, **kwargs}
        )
        self.found.append((self.repo / "README.md").read_text(encoding="utf-8"))
        _wander(self.repo)
        otel.turn_result(TurnUsage(input_tokens=100, cache_read_input_tokens=900, output_tokens=40, total_cost_usd=0.25, steps=7))
        otel.turn_result(TurnUsage(input_tokens=10, output_tokens=5, total_cost_usd=0.05, steps=1))
        return "page written"


def _runner(repo: Path) -> _ScriptedRunner:
    return _ScriptedRunner(
        repo, backend=FakeBackend(), resilience=AgentResilience(), clock=FakeClock()
    )


def _record(repo: Path) -> TurnRecord:
    return TurnRecord(
        node="write-page",
        backend=FakeBackend().name,
        profile="opencode",
        model="some/model",
        effort="high",
        silence_budget_s=1800,
        base_timeout_s=900,
        timeout_scale=2.0,
        cwd=str(repo),
        add_dirs=[str(repo / "docs")],
        agent=AgentProfile(name="writer", steps=40),
        start=[gitstate.snapshot_tree(repo)],
    )


def test_each_repeat_starts_from_the_recorded_tree_with_the_recorded_settings(tmp_path):
    repo = _started_repo(tmp_path)
    record = _record(repo)
    runner = _runner(repo)
    into = tmp_path / "run" / "replays" / "000-00023-write-page"

    first = replay.replay_turn(runner, record, "Write the page.", into)
    second = replay.replay_turn(runner, record, "Write the page.", into)

    assert runner.found == ["# edited\n", "# edited\n"]
    assert (first.index, second.index) == (1, 2)
    call = runner.calls[0]
    assert call["prompt"] == "Write the page."
    assert call["node"] == "write-page"
    assert call["session"] == sessions.chain_path(first.directory, "write-page")
    assert runner.calls[1]["session"] == sessions.chain_path(second.directory, "write-page")
    assert call["model"] == "some/model"
    assert call["timeout"] == 1800
    assert call["budget_scale"] == 2.0
    assert call["base_timeout_s"] == 900
    assert call["cwd"] == str(repo)
    assert call["add_dirs"] == [str(repo / "docs")]
    assert call["effort"] == "high"
    assert call["agent"] == AgentProfile(name="writer", steps=40)


def test_a_repeat_keeps_its_reply_and_its_summed_usage(tmp_path):
    repo = _started_repo(tmp_path)
    into = tmp_path / "replays" / "000-00023-write-page"

    done = replay.replay_turn(_runner(repo), _record(repo), "Write the page.", into)

    assert done.directory == into / "1"
    assert (done.directory / "reply.md").read_text(encoding="utf-8") == "page written"
    usage = json.loads((done.directory / "usage.json").read_text(encoding="utf-8"))
    assert usage["input_tokens"] == 110
    assert usage["cache_read_input_tokens"] == 900
    assert usage["output_tokens"] == 45
    assert usage["total_cost_usd"] == pytest.approx(0.30)
    assert usage["steps"] == 8
    assert "wall_s" in usage
    assert "$0.30" in replay._summary(done)


def test_a_replay_leaves_the_telemetry_it_found(tmp_path):
    repo = _started_repo(tmp_path)
    recorder = otel.UsageRecorder()
    previous = otel.install(otel.TelemetryHost(active=recorder))
    try:
        _ = replay.replay_turn(_runner(repo), _record(repo), "Write the page.", tmp_path / "r")
        otel.turn_result(TurnUsage(steps=3))
    finally:
        _ = otel.install(previous)

    assert recorder.usages == [TurnUsage(steps=3)]


def _recorded_run(tmp_path: Path, repo: Path) -> Path:
    visit = tmp_path / "runs" / "okf-book-r1" / "turns" / "000-00023-write-page"
    visit.mkdir(parents=True)
    _ = (visit / "turn.json").write_text(_record(repo).model_dump_json(), encoding="utf-8")
    _ = (visit / "prompt.md").write_text("Write the page.", encoding="utf-8")
    return visit.parent.parent


def _args(run_dir: Path, **overrides: Any) -> argparse.Namespace:
    values: dict[str, Any] = {
        "turn": "000-00023-write-page",
        "run": str(run_dir),
        "runs_dir": None,
        "prompt": None,
        "max_prompt_chars": None,
        "repeat": 1,
        "profile": None,
        "config": None,
        "discard": False,
        "registry": SimpleNamespace(name="okf-book"),
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_a_dirty_tree_is_refused_and_the_message_names_the_ways_out(tmp_path, capsys):
    repo = _started_repo(tmp_path)
    run_dir = _recorded_run(tmp_path, repo)

    with pytest.raises(SystemExit):
        replay.run(_args(run_dir))

    err = capsys.readouterr().err
    assert str(repo) in err
    assert "copy of the checkout" in err
    assert "--discard" in err
    assert (repo / "draft.md").exists()


def test_a_branch_moved_past_the_start_is_refused_and_keeps_its_commits(tmp_path, capsys):
    repo = _started_repo(tmp_path)
    run_dir = _recorded_run(tmp_path, repo)
    _ = _git(repo, "add", "-A")
    _ = _git(repo, "commit", "-q", "-m", "work after the turn")
    after = _git(repo, "rev-parse", "HEAD")

    with pytest.raises(SystemExit):
        replay.run(_args(run_dir))

    err = capsys.readouterr().err
    assert "dropping every commit after it" in err
    assert "--discard" in err
    assert _git(repo, "rev-parse", "HEAD") == after


def test_run_replays_under_the_recorded_profile_and_prints_the_cost(tmp_path, capsys, monkeypatch):
    repo = _started_repo(tmp_path)
    run_dir = _recorded_run(tmp_path, repo)
    variant = tmp_path / "variant.md"
    _ = variant.write_text("Write it shorter.", encoding="utf-8")
    runner = _runner(repo)
    picked: list[str] = []

    def _select(config_path, profile, cli):
        picked.append(profile)
        return FakeBackend()

    monkeypatch.setattr(replay, "backend_for_profile", _select)
    monkeypatch.setattr(replay.AgentRunner, "from_config", lambda config: runner)

    replay.run(_args(run_dir, discard=True, repeat=2, prompt=str(variant)))

    out = capsys.readouterr().out.splitlines()
    assert picked == ["opencode"]
    assert [c["prompt"] for c in runner.calls] == ["Write it shorter.", "Write it shorter."]
    assert [line.split(":")[0] for line in out] == ["replay 1", "replay 2"]
    assert (run_dir / "replays" / "000-00023-write-page" / "2" / "usage.json").is_file()


def test_a_variant_over_twice_the_recorded_prompt_is_refused_with_its_size(tmp_path, capsys):
    repo = _started_repo(tmp_path)
    run_dir = _recorded_run(tmp_path, repo)
    variant = tmp_path / "variant.md"
    _ = variant.write_text("x" * 31, encoding="utf-8")

    with pytest.raises(SystemExit):
        replay.run(_args(run_dir, discard=True, prompt=str(variant)))

    err = capsys.readouterr().err
    assert "31 characters, over the 30 allowed" in err
    assert "--max-prompt-chars" in err


def test_a_stated_limit_replaces_the_recorded_prompt_budget(tmp_path, capsys):
    repo = _started_repo(tmp_path)
    run_dir = _recorded_run(tmp_path, repo)
    variant = tmp_path / "variant.md"
    _ = variant.write_text("Write the page.", encoding="utf-8")

    with pytest.raises(SystemExit):
        replay.run(_args(run_dir, discard=True, prompt=str(variant), max_prompt_chars=10))

    assert "15 characters, over the 10 allowed (--max-prompt-chars)" in capsys.readouterr().err


def test_a_missing_turn_says_where_turns_live(tmp_path, capsys):
    run_dir = tmp_path / "runs" / "okf-book-r1"
    run_dir.mkdir(parents=True)

    with pytest.raises(SystemExit):
        replay.run(_args(run_dir))

    assert "turns/" in capsys.readouterr().err
