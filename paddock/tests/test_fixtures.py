"""A benchmark whose stories name a fixture its repo never declared fails before a trial starts."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from paddock import fixtures, loader
from paddock.loader import Benchmark
from paddock.registry import TaskError

MakeBenchmark = Callable[..., Benchmark]

DECLARED = (
    "qa:\n"
    "  fixtures:\n"
    "    seeded_accounts:\n"
    "      tool: node\n"
    "      args: ['auth/seed.mjs']\n"
    "      provides: three identities in the auth emulator\n"
)


def _story_naming_a_fixture(data: Path, agents: str) -> None:
    story = data / "docs" / "specs" / "story"
    story.mkdir(parents=True)
    (data / "agents.yml").write_text(agents, encoding="utf-8")
    (story / "plan-context.json").write_text(
        json.dumps({"qa_stack": {"fixtures": ["seeded_accounts"]}}), encoding="utf-8"
    )


def test_a_story_naming_an_undeclared_fixture_stops_the_task_before_it_runs(
    make_benchmark: MakeBenchmark, root: Path
) -> None:
    benchmark = make_benchmark()
    _story_naming_a_fixture(benchmark.data, "qa:\n  fixtures: {}\n")

    with pytest.raises(TaskError, match="declares fixture 'seeded_accounts'"):
        loader.load_task(root, "smoke", "smoke")


def test_a_story_naming_a_declared_fixture_loads(make_benchmark: MakeBenchmark, root: Path) -> None:
    benchmark = make_benchmark()
    _story_naming_a_fixture(benchmark.data, DECLARED)

    _, task = loader.load_task(root, "smoke", "smoke")

    assert task.name == "smoke"
    assert fixtures.benchmark_problems(root, "smoke") == []


def test_a_benchmark_with_no_specs_has_no_fixture_problems(
    make_benchmark: MakeBenchmark, root: Path
) -> None:
    make_benchmark()

    assert fixtures.benchmark_problems(root, "smoke") == []
