"""The lease a run holds on an `ostler env` copy: brought up under it, reclaimed when its holder is gone, and named in the environment a command runs in."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from test_environments import SERVICES, FakeDocker, _gone_pid, _repo

from ostler.environments import commands, leases, runtime
from ostler.environments import render as render_mod
from ostler.qa import addresses


def test_a_run_copy_comes_up_under_its_lease_and_names_the_front_service(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    outcome = leases.up(root, lease="story-1", near=root / SERVICES / "web", runner=FakeDocker())
    assert outcome is not None and outcome.ok, outcome
    assert outcome.data["entry_url"] == "http://localhost:49200"
    assert outcome.data["lease"] == "story-1"
    assert leases.run_env(root, "story-1") == {
        addresses.LEASE_ENV: "story-1",
        addresses.BOOK_ENV: outcome.data["address_book"],
    }
    down = leases.down(root, lease="story-1", runner=FakeDocker())
    assert down is not None and down.ok
    assert runtime.copies(root) == []


def test_a_copy_whose_run_is_gone_is_reclaimed_at_the_next_lease(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = FakeDocker()
    commands.cmd_up(root, ["web"], copy_name="by-hand", runner=docker)
    commands.cmd_up(root, ["web"], copy_name="story-1", holder=_gone_pid(), runner=docker)
    live = leases.up(root, lease="story-2", near=root / SERVICES / "web", holder=os.getpid(),
                     runner=docker)
    assert live is not None and live.ok, live
    assert live.data["reclaimed"] == ["acme-story-1"]
    later = commands.cmd_up(root, ["web"], copy_name="story-3", runner=docker)
    assert later.data["reclaimed"] == []
    assert [copy.name for copy in runtime.copies(root)] == ["by-hand", "story-2", "story-3"]


def test_a_resumed_run_restamps_its_copy_and_survives_reclaim(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    docker = FakeDocker()
    up = commands.cmd_up(root, ["web"], copy_name="story-1", holder=_gone_pid(), runner=docker)
    directory = Path(up.data["directory"])
    assert not runtime.holder_alive(runtime.read_manifest(directory)["holder"])
    assert runtime.hold(root, "story-1", os.getpid())
    assert runtime.read_manifest(directory)["holder"] == runtime.holder_stamp(os.getpid())
    assert commands.reclaim(runner=docker) == []
    assert [copy.name for copy in runtime.copies(root)] == ["story-1"]


def test_holding_a_copy_that_does_not_exist_does_nothing(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert not runtime.hold(root, "story-9", os.getpid())
    assert runtime.copies(root) == []


def test_a_reused_pid_does_not_pass_for_the_run_that_held_the_copy() -> None:
    stamp = runtime.holder_stamp(os.getpid())
    assert runtime.holder_alive(stamp)
    assert runtime.holder_alive({})
    if stamp["started"]:
        assert not runtime.holder_alive({**stamp, "started": "1"})


def test_a_command_run_under_a_lease_names_its_holder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    env = leases.run_env(root, "story-1", holder=os.getpid())
    assert env is not None and env[runtime.HOLDER_ENV] == str(os.getpid())
    monkeypatch.setenv(addresses.LEASE_ENV, env[addresses.LEASE_ENV])
    monkeypatch.setenv(runtime.HOLDER_ENV, env[runtime.HOLDER_ENV])
    up = commands.cmd_up(root, ["web"], copy_name="story-1", runner=FakeDocker())
    assert runtime.read_manifest(Path(up.data["directory"]))["holder"] == \
        runtime.holder_stamp(os.getpid())


def test_a_named_copy_brought_up_under_a_lease_is_not_held_by_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _repo(tmp_path)
    docker = FakeDocker()
    monkeypatch.setenv(addresses.LEASE_ENV, "story-1")
    monkeypatch.setenv(runtime.HOLDER_ENV, str(_gone_pid()))
    prod = commands.cmd_up(root, ["web"], copy_name="prod", runner=docker)
    assert runtime.read_manifest(Path(prod.data["directory"]))["holder"] == {}
    lease = commands.cmd_up(root, ["web"], copy_name="story-1", runner=docker)
    assert lease.data["reclaimed"] == []
    assert [copy.name for copy in runtime.copies(root)] == ["prod", "story-1"]


def test_a_command_run_without_a_lease_names_the_shared_copy(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    env = leases.run_env(root)
    assert env == {
        addresses.LEASE_ENV: render_mod.SHARED,
        addresses.BOOK_ENV: str(runtime.copy_for(root, render_mod.SHARED).directory / runtime.ADDRESSES),
    }


def test_the_book_near_the_run_is_the_only_one_brought_up(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert leases.books_near(root, root / SERVICES / "api" / "ops") == ["api"]
    assert leases.books_near(root) == ["api", "web"]
    assert leases.books_near(root, tmp_path) == []
