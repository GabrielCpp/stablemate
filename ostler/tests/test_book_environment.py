"""Which stack copy a book reaches: the run's word over the lease, the lease over the book's own name."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from ostler.book.environment import Environment
from ostler.environments import commands, runtime
from ostler.environments.render import COMPOSE_FILE
from ostler.qa import addresses
from ostler.qa.addresses import LEASE_ENV

from book_todo import run_book


def named(copy: str = "") -> Environment:
    return Environment("local", {"api": f"ostler:{copy}", "docs": "http://docs.test"})


@pytest.fixture(autouse=True)
def no_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LEASE_ENV, raising=False)


def test_the_copy_the_run_names_outranks_the_lease_and_the_book(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(LEASE_ENV, "lease")
    place = named("books-own")
    place.leased = "runs-own"
    assert place.copy() == "runs-own"


def test_the_lease_outranks_the_copy_the_book_names(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(LEASE_ENV, "lease")
    assert named("books-own").copy() == "lease"


def test_the_books_own_copy_serves_a_run_by_hand():
    assert named("books-own").copy() == "books-own"


def test_a_host_that_names_no_copy_reaches_the_shared_one():
    assert named().copy() == "shared"


def test_an_environment_of_plain_addresses_has_no_copy():
    assert Environment("remote", {"api": "http://api.test"}).copy() == ""


@pytest.fixture
def stack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "app"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv(runtime.HOME_ENV, str(tmp_path / "home"))
    monkeypatch.chdir(repo)
    return repo


def publish(repo: Path, copy: str, book: dict[str, str], rendered: bool = True) -> Path:
    directory = runtime.copy_for(repo, copy).directory
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / runtime.ADDRESSES
    target.write_text(json.dumps(book), encoding="utf-8")
    if rendered:
        (directory / COMPOSE_FILE).write_text("services: {}\n", encoding="utf-8")
    return target


def local(repo: Path, copy: str = "books-own") -> Environment:
    return Environment("local", {"api": f"ostler:{copy}", "docs": "http://docs.test"}, root=str(repo))


def test_an_address_is_read_from_the_copy_the_run_named(stack: Path):
    publish(stack, "runs-own", {"api": "http://127.0.0.1:4000/"})
    publish(stack, "books-own", {"api": "http://127.0.0.1:1111"})
    place = local(stack)
    place.leased = "runs-own"
    assert place.address("api") == "http://127.0.0.1:4000"
    assert place.address("docs") == "http://docs.test"


def test_two_calls_read_the_address_book_once(stack: Path, monkeypatch: pytest.MonkeyPatch):
    publish(stack, "books-own", {"api": "http://127.0.0.1:4000", "gateway": "http://127.0.0.1:4001"})
    reads: list[Path] = []
    original = addresses.read_book

    def spy(path: Path) -> dict[str, str]:
        reads.append(path)
        return original(path)

    monkeypatch.setattr(addresses, "read_book", spy)
    place = local(stack)
    assert place.address("api") == "http://127.0.0.1:4000"
    assert place.address("api") == "http://127.0.0.1:4000"
    assert len(reads) == 1


def test_a_rewritten_address_book_is_read_again(stack: Path):
    target = publish(stack, "books-own", {"api": "http://127.0.0.1:4000"})
    place = local(stack)
    assert place.address("api") == "http://127.0.0.1:4000"
    target.write_text(json.dumps({"api": "http://127.0.0.1:5000"}), encoding="utf-8")
    os.utime(target, ns=(target.stat().st_atime_ns, target.stat().st_mtime_ns + 1_000_000))
    assert place.address("api") == "http://127.0.0.1:5000"


def test_an_unknown_host_fails_with_the_text_the_command_prints(stack: Path):
    publish(stack, "books-own", {"gateway": "http://127.0.0.1:4001", "api": "http://127.0.0.1:4000"})
    place = Environment("local", {"report": "ostler:books-own"}, root=str(stack))
    expected = commands.cmd_address(stack, "report", copy_name="books-own").message
    with pytest.raises(RuntimeError) as raised:
        place.address("report")
    assert str(raised.value) == expected + "\n"


def test_a_copy_that_is_not_up_fails_with_the_text_the_command_prints(stack: Path):
    expected = commands.cmd_address(stack, "api", copy_name="books-own").message
    with pytest.raises(RuntimeError) as raised:
        local(stack).address("api")
    assert str(raised.value) == expected + "\n"
    assert "none, since it is not up" in expected


class Docker:
    def __init__(self, containers: list[str], gone: int = 0) -> None:
        self.calls: list[tuple[list[str], str | None]] = []
        self.containers = containers
        self.gone = gone

    def __call__(self, argv: Sequence[str], *, capture: bool, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        command = list(argv)
        self.calls.append((command, stdin))
        if "ps" in command:
            return subprocess.CompletedProcess(command, 0, self.containers.pop(0) + "\n", "")
        if command[:2] == ["docker", "exec"] and self.gone:
            self.gone -= 1
            return subprocess.CompletedProcess(command, 1, "", "Error response from daemon: No such container: old")
        return subprocess.CompletedProcess(command, 0, "done\n", "")


def test_a_command_runs_in_the_container_of_the_service(stack: Path):
    publish(stack, "books-own", {})
    docker = Docker(["abc123"])
    place = local(stack)
    place.runner = docker
    done = place.exec("api-db", ["psql", "-c", "SELECT 1"], stdin="input")
    assert done.stdout == "done\n"
    ps, run = docker.calls
    assert ps[0][-3:] == ["ps", "-q", "api-db"] and "docker" in ps[0] and "compose" in ps[0]
    assert run == (["docker", "exec", "-i", "abc123", "psql", "-c", "SELECT 1"], "input")


def test_a_command_without_input_leaves_the_container_input_closed(stack: Path):
    publish(stack, "books-own", {})
    docker = Docker(["abc123"])
    place = local(stack)
    place.runner = docker
    place.exec("api-db", ["true"])
    assert docker.calls[-1][0] == ["docker", "exec", "abc123", "true"]


def test_the_container_is_resolved_once_over_two_calls(stack: Path):
    publish(stack, "books-own", {})
    docker = Docker(["abc123"])
    place = local(stack)
    place.runner = docker
    place.exec("api-db", ["true"])
    place.exec("api-db", ["true"])
    assert sum("ps" in call[0] for call in docker.calls) == 1


def test_a_container_that_is_gone_is_resolved_again_once(stack: Path):
    publish(stack, "books-own", {})
    docker = Docker(["old", "new"], gone=1)
    place = local(stack)
    place.runner = docker
    done = place.exec("api-db", ["true"])
    assert done.returncode == 0
    assert [call[0][2] for call in docker.calls if call[0][:2] == ["docker", "exec"]] == ["old", "new"]


def test_a_container_still_gone_after_a_second_look_is_returned_not_raised(stack: Path):
    publish(stack, "books-own", {})
    docker = Docker(["old", "new"], gone=2)
    place = local(stack)
    place.runner = docker
    assert place.exec("api-db", ["true"]).returncode == 1


def test_a_failing_command_is_returned_not_raised(stack: Path):
    publish(stack, "books-own", {})

    def fail(argv: Sequence[str], *, capture: bool, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        command = list(argv)
        return subprocess.CompletedProcess(command, 0 if "ps" in command else 3, "abc\n", "boom")

    place = local(stack)
    place.runner = fail
    assert place.exec("api-db", ["false"]).returncode == 3


def test_a_one_shot_runs_compose_against_the_copy(stack: Path):
    publish(stack, "books-own", {})
    docker = Docker([])
    place = local(stack)
    place.runner = docker
    place.compose(["run", "--rm", "seed"], stdin="x")
    argv, stdin = docker.calls[0]
    assert argv[-3:] == ["run", "--rm", "seed"] and "--project-name" in argv and stdin == "x"
    assert argv == runtime.Compose(runtime.copy_for(stack, "books-own")).argv(["run", "--rm", "seed"])


def test_a_copy_not_rendered_runs_nothing(stack: Path):
    publish(stack, "books-own", {}, rendered=False)
    place = local(stack)
    place.runner = Docker([])
    with pytest.raises(RuntimeError, match="has not been rendered"):
        place.exec("api-db", ["true"])


def test_a_run_takes_the_copy_as_an_option(tmp_path: Path):
    done = run_book(["run", "services.api", "--no-stack", "--copy", "runs-own", "--out", str(tmp_path / "out"), "--print-exec"], 1)
    assert done.returncode == 0, done.stdout + done.stderr
