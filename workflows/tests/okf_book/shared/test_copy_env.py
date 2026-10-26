"""A run's scenarios find the stack copy's address book in their environment, and only while they run."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from ostler.environments import runtime
from ostler.qa import addresses
from workhorse_workflows.okf_book.shared import book_run
from workhorse_workflows.okf_book.shared.book_run import StackReadiness, book_lease, copy_env, run_plan
from workhorse_workflows.okf_book.shared.scenarios import RunSummary, Scenario, ScenarioOutcome


@pytest.fixture(autouse=True)
def env_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "env-home"
    monkeypatch.setenv(runtime.HOME_ENV, str(home))
    monkeypatch.delenv(addresses.BOOK_ENV, raising=False)
    return home


def test_a_book_with_a_stack_file_runs_against_its_own_copys_address_book(tmp_path: Path) -> None:
    root = tmp_path / "acme"
    stack = root / "docs" / "services" / "web" / "ops" / "stack.yml"
    stack.parent.mkdir(parents=True)
    _ = stack.write_text("services: {}\n", encoding="utf-8")

    book = runtime.copy_for(root, "okf-web").directory / runtime.ADDRESSES

    assert book_lease(root, "web") == "okf-web"
    assert copy_env(root, "web") == {addresses.LEASE_ENV: "okf-web", runtime.HOLDER_ENV: str(os.getpid()), addresses.BOOK_ENV: str(book)}


def test_a_book_no_stack_file_covers_adds_nothing_to_the_environment(tmp_path: Path) -> None:
    (tmp_path / "docs" / "services" / "web").mkdir(parents=True)

    assert book_lease(tmp_path, "web") == ""
    assert copy_env(tmp_path, "web") == {}


def test_the_scenarios_see_the_stacks_environment_only_while_they_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[str | None] = []

    def _plan_scenarios(*_args: object) -> tuple[tuple[Scenario, ...], tuple[str, ...]]:
        return (Scenario(id="docs-a-from-the-book"),), ()

    def _run_scenarios(_root: Path, _spec: Path, only: tuple[str, ...], _lap: Path, _check: object = None) -> RunSummary:
        seen.append(os.environ.get(addresses.BOOK_ENV))
        return RunSummary(status="passed", scenarios={name: ScenarioOutcome(status="passed") for name in only})

    monkeypatch.setattr(book_run, "plan_scenarios", _plan_scenarios)
    monkeypatch.setattr(book_run, "run_scenarios", _run_scenarios)
    stack = StackReadiness(up=True, serving=True, notes="", env={addresses.BOOK_ENV: "/copies/acme/addresses.json"})

    _ = run_plan(tmp_path, tmp_path / "spec", (), stack)

    assert seen == ["/copies/acme/addresses.json"]
    assert addresses.BOOK_ENV not in os.environ
