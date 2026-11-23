"""`ostler env reset` brings a copy back up on its own targets and fixture sets with its data dropped."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest
import yaml
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


def test_a_reset_waits_for_a_port_that_refuses_twice_then_accepts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    commands.cmd_up(root, ["web"], copy_name="story-1", runner=FakeDocker())
    tries: list[int] = []

    def probe(host: str, port: int) -> bool:
        tries.append(port)
        return tries.count(port) > 2

    monkeypatch.setattr(runtime, "port_probe", probe)
    code, _, shown = commands.reset(root, "story-1", runner=FakeDocker())
    assert code == 0, shown
    assert tries.count(49200) == 3

    monkeypatch.setattr(runtime, "port_probe", lambda host, port: False)
    code, _, shown = commands.reset(root, "story-1", 1, runner=FakeDocker())
    assert code == 1
    assert "did not accept a connection on localhost:" in shown


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


class PickingDocker(FakeDocker):
    """A docker that publishes a service on the host port its compose file fixes, else on the next free one."""

    def __init__(self, refuse: str = "") -> None:
        super().__init__()
        self.next_port = 40000
        self.published: dict[tuple[str, str], str] = {}
        self.refuse = refuse

    def __call__(self, argv: Sequence[str], *, capture: bool, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        args = list(argv)
        if "up" in args and self.refuse:
            self.calls.append(args)
            return subprocess.CompletedProcess(args, 1, "", self.refuse)
        done = super().__call__(args, capture=capture, stdin=stdin)
        if "up" in args:
            compose = yaml.safe_load(Path(args[args.index("--file") + 1]).read_text(encoding="utf-8"))
            self.published = {}
            for name, block in compose["services"].items():
                for mapping in block.get("ports", []):
                    _, host, container = mapping.split(":")
                    if not host:
                        self.next_port += 1
                        host = str(self.next_port)
                    self.published[(name, container)] = host
        if "port" in args:
            return subprocess.CompletedProcess(
                args, 0, f"127.0.0.1:{self.published[(args[-2], args[-1])]}\n", "")
        return done


def _compose_ports(root: Path, name: str) -> dict[str, list[str]]:
    text = (runtime.copy_for(root, name).directory / "compose.yml").read_text(encoding="utf-8")
    return {key: block["ports"] for key, block in yaml.safe_load(text)["services"].items()
            if "ports" in block}


def test_a_reset_publishes_each_target_on_the_host_port_it_had(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = PickingDocker()
    assert commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker).ok
    copy = runtime.copy_for(root, "story-1")
    before = commands.read_book(copy)
    assert set(before) == {"api", "gateway"}
    assert _compose_ports(root, "story-1") == {"api-api": ["127.0.0.1::8080"],
                                              "web-gateway": ["127.0.0.1::80"]}
    for _ in range(2):
        code, _, shown = commands.reset(root, "story-1", runner=docker)
        assert code == 0, shown
        assert commands.read_book(copy) == before
    api_port = before["api"].rpartition(":")[2]
    gateway_port = before["gateway"].rpartition(":")[2]
    assert _compose_ports(root, "story-1") == {"api-api": [f"127.0.0.1:{api_port}:8080"],
                                              "web-gateway": [f"127.0.0.1:{gateway_port}:80"]}


def test_a_target_with_no_recorded_port_is_left_to_docker(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = PickingDocker()
    assert commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker).ok
    copy = runtime.copy_for(root, "story-1")
    before = commands.read_book(copy)
    addresses.write_book(copy.directory / runtime.ADDRESSES, {"gateway": before["gateway"]})
    code, _, shown = commands.reset(root, "story-1", runner=docker)
    assert code == 0, shown
    gateway_port = before["gateway"].rpartition(":")[2]
    assert _compose_ports(root, "story-1") == {"api-api": ["127.0.0.1::8080"],
                                              "web-gateway": [f"127.0.0.1:{gateway_port}:80"]}
    after = commands.read_book(copy)
    assert after["gateway"] == before["gateway"]
    assert set(after) == {"api", "gateway"}


def test_a_start_that_cannot_rebind_a_pinned_port_says_so_and_takes_no_other(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert commands.cmd_up(root, ["web"], copy_name="story-1", runner=PickingDocker()).ok
    port = commands.read_book(runtime.copy_for(root, "story-1"))["gateway"].rpartition(":")[2]
    refusing = PickingDocker(refuse=f"Bind for 127.0.0.1:{port} failed: port is already allocated")
    code, _, shown = commands.reset(root, "story-1", runner=refusing)
    assert code == 1
    assert "docker compose could not bring story-1 up (exit 1)" in shown
    assert f"A reset pins the copy's host ports to the ones it had, and host port {port} was refused." in shown
    assert _compose_ports(root, "story-1")["web-gateway"] == [f"127.0.0.1:{port}:80"]


def test_a_failed_start_that_names_no_port_still_says_the_ports_are_pinned(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert commands.cmd_up(root, ["web"], copy_name="story-1", runner=PickingDocker()).ok
    code, _, shown = commands.reset(root, "story-1", runner=PickingDocker(refuse="boom"))
    assert code == 1
    assert "A reset pins the copy's host ports to the ones it had and never takes a new one." in shown


def test_the_command_prints_the_seconds_it_took(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path)
    commands.cmd_up(root, ["web"], copy_name="story-1", runner=FakeDocker())
    assert commands.cmd_reset(root, "story-1", runner=FakeDocker()) == 0
    assert re.fullmatch(r"reset story-1 in \d+s", capsys.readouterr().out.strip())


def test_the_command_line_names_the_copy_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    import argparse

    root = _repo(tmp_path)
    parser = argparse.ArgumentParser()
    cli.add_parser(parser.add_subparsers())
    args = parser.parse_args(["env", "reset", "--copy", "story-5"])
    assert cli.run(args, root) == 1
    assert "no copy named story-5 is up" in capsys.readouterr().err
