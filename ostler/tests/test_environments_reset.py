"""`ostler env reset` brings a copy back up on its own targets and fixture sets with its data dropped."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from test_environments import FakeDocker, RunningDocker, _gone_pid, _repo

from ostler.environments import cli, commands, leases, runtime
from ostler.qa import addresses


def _manifest(root: Path, name: str) -> dict[str, object]:
    return runtime.read_manifest(runtime.copy_for(root, name).directory)


def _downs(docker: FakeDocker) -> list[list[str]]:
    return [call for call in docker.calls if call[:2] == ["docker", "compose"] and "down" in call]


def test_a_reset_drops_the_volumes_and_brings_the_recorded_targets_up_again(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    commands.cmd_up(root, ["api"], copy_name="story-1", fixtures=["schema", "users"], runner=FakeDocker())
    before = _manifest(root, "story-1")
    docker = FakeDocker()
    code, took, shown = commands.reset(root, "story-1", runner=docker)
    assert code == 0, shown
    assert took >= 0
    assert len(_downs(docker)) == 1 and "--volumes" in _downs(docker)[0]
    ups = [call for call in docker.calls if "up" in call and call[:2] == ["docker", "compose"]]
    assert ups
    after = _manifest(root, "story-1")
    assert after["targets"] == before["targets"]
    assert after["fixtures"] == before["fixtures"] == ["schema", "users"]
    assert after["env_files"] == before["env_files"]
    assert after["exec_prefix"] == before["exec_prefix"]


def test_a_reset_keeps_the_holder_the_starter_and_the_worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _repo(tmp_path)
    commands.cmd_up(root, ["web"], copy_name="story-1", holder=os.getpid(), runner=RunningDocker(),
                    cwd=tmp_path)
    before = _manifest(root, "story-1")
    before["worktree"] = "/trees/story-1"
    runtime.write_manifest(runtime.copy_for(root, "story-1"), before)
    monkeypatch.setenv(runtime.HOLDER_ENV, str(os.getpid()))
    code, _, shown = commands.reset(root, "story-1", runner=RunningDocker(["acme-story-1"]))
    assert code == 0, shown
    after = _manifest(root, "story-1")
    for key in ("holder", "started_by", "worktree"):
        assert after[key] == before[key], key
    assert after["holder"] == runtime.holder_stamp(os.getpid())
    assert after["used_at"]


def test_a_reset_leaves_a_copy_nobody_holds_unheld(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _repo(tmp_path)
    commands.cmd_up(root, ["web"], copy_name="story-1", runner=FakeDocker())
    monkeypatch.setenv(addresses.LEASE_ENV, "story-1")
    monkeypatch.setenv(runtime.HOLDER_ENV, str(os.getpid()))
    code, _, shown = commands.reset(root, "story-1", runner=FakeDocker())
    assert code == 0, shown
    assert _manifest(root, "story-1")["holder"] == {}


def test_a_copy_that_is_not_up_is_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = FakeDocker()
    code, _, shown = commands.reset(root, "story-9", runner=docker)
    assert code == 1
    assert shown == "no copy named story-9 is up: bring it up with ostler env up"
    commands.cmd_render(root, ["web"], copy_name="story-8")
    code, _, shown = commands.reset(root, "story-8", runner=docker)
    assert code == 1 and "no copy named story-8 is up" in shown
    assert docker.calls == []


def test_a_copy_another_live_process_holds_is_refused_and_nothing_runs(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    other = subprocess.Popen(["sleep", "60"])
    try:
        commands.cmd_up(root, ["web"], copy_name="story-1", holder=other.pid, runner=FakeDocker())
        docker = FakeDocker()
        before = _manifest(root, "story-1")
        code, _, shown = commands.reset(root, "story-1", runner=docker)
        assert code == 1
        assert shown == (f"story-1 is in use by pid {other.pid}: a reset would pull its data from "
                         "under a play")
        assert docker.calls == []
        assert _manifest(root, "story-1") == before
    finally:
        other.kill()
        other.wait()


def test_the_holder_itself_may_reset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _repo(tmp_path)
    commands.cmd_up(root, ["web"], copy_name="story-1", holder=os.getpid(), runner=FakeDocker())
    monkeypatch.setenv(runtime.HOLDER_ENV, str(os.getpid()))
    code, _, shown = commands.reset(root, "story-1", runner=FakeDocker())
    assert code == 0, shown


def test_a_play_run_under_the_lease_environment_of_a_workflow_is_the_holder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    commands.cmd_up(root, ["web"], copy_name="story-1", holder=os.getpid(), runner=FakeDocker())
    env = leases.run_env(root, "story-1", holder=os.getpid())
    assert env is not None
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    code, _, shown = commands.reset(root, "story-1", runner=FakeDocker())
    assert code == 0, shown


def test_a_play_that_carries_no_holder_is_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    commands.cmd_up(root, ["web"], copy_name="story-1", holder=os.getpid(), runner=FakeDocker())
    code, _, shown = commands.reset(root, "story-1", runner=FakeDocker())
    assert code == 1 and f"in use by pid {os.getpid()}" in shown


def test_a_dead_holder_does_not_block_a_reset(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    commands.cmd_up(root, ["web"], copy_name="story-1", holder=_gone_pid(), runner=FakeDocker())
    code, _, shown = commands.reset(root, "story-1", runner=FakeDocker())
    assert code == 0, shown


def test_a_failed_bring_up_returns_its_code_and_what_up_prints(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    commands.cmd_up(root, ["web"], copy_name="story-1", runner=FakeDocker())

    class Failing(FakeDocker):
        def __call__(self, argv, *, capture, stdin=None):
            done = super().__call__(argv, capture=capture, stdin=stdin)
            if "up" in argv:
                return subprocess.CompletedProcess(done.args, 3, "", "")
            return done

    code, _, shown = commands.reset(root, "story-1", runner=Failing())
    assert code == 1
    assert "docker compose could not bring" in shown and "(exit 3)" in shown


def test_the_command_prints_the_seconds_it_took(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path)
    commands.cmd_up(root, ["web"], copy_name="story-1", runner=FakeDocker())
    assert commands.cmd_reset(root, "story-1", runner=FakeDocker()) == 0
    assert capsys.readouterr().out.strip() in {f"reset story-1 in {n}s" for n in range(3)}


def test_the_command_line_names_the_copy_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    import argparse

    root = _repo(tmp_path)
    parser = argparse.ArgumentParser()
    cli.add_parser(parser.add_subparsers())
    args = parser.parse_args(["env", "reset", "--copy", "story-5"])
    assert cli.run(args, root) == 1
    assert "no copy named story-5 is up" in capsys.readouterr().err
