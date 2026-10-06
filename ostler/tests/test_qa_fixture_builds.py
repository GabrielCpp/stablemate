"""A run says how often it built each book fixture and how long that took, so a slow per-scenario build shows on the fixture's page."""

from __future__ import annotations

import json
from pathlib import Path

from ostler.qa.drivers import FixtureBuild, PythonDriver, ScenarioResult
from ostler.qa.session import QaSession
from ostler.qa.v2 import _fixture_builds

SESSION = "docs/features/acme/fixtures/editor-session.md"
STACK = "docs/features/acme/fixtures/test-stack.md"


def _driver(repo: Path) -> PythonDriver:
    spec = repo / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "qa-okf-context.json").write_text(json.dumps({"featuresRoot": "docs/features"}), encoding="utf-8")
    session = QaSession.create(spec, "qa-fixture-builds-1", "story-1", {})
    return PythonDriver(session, "cli", {"driver": "cli"}, root=repo, variables={})


def _fixture(page: str, lifetime: str, seconds: float, *, reused: bool) -> dict[str, object]:
    return {"type": "fixture", "name": Path(page).stem, "page": page, "lifetime": lifetime,
            "reused": reused, "seconds": seconds, "ok": True}


def _passed() -> dict[str, object]:
    return {"type": "scenario", "id": "s-1", "status": "passed", "assertions": 0, "failures": 0}


def test_a_scenario_counts_the_fixtures_it_built_and_not_the_ones_its_lap_reused(repo: Path) -> None:
    records = [_fixture(STACK, "lap", 41.5, reused=True), _fixture(SESSION, "scenario", 2.25, reused=False), _passed()]

    result = _driver(repo)._grade("s-1", [], records, "", 0, timed_out=False)

    assert result.fixture_builds == [FixtureBuild("editor-session", SESSION, "scenario", 2.25)]


def test_the_run_totals_each_fixtures_builds_slowest_first() -> None:
    results = {
        "s-1": ScenarioResult("passed", fixture_builds=[FixtureBuild("test-stack", STACK, "lap", 40.0),
                                                        FixtureBuild("editor-session", SESSION, "scenario", 2.0)]),
        "s-2": ScenarioResult("passed", fixture_builds=[FixtureBuild("editor-session", SESSION, "scenario", 2.5)]),
    }

    assert _fixture_builds(results) == [
        {"name": "test-stack", "page": STACK, "lifetime": "lap", "builds": 1, "seconds": 40.0},
        {"name": "editor-session", "page": SESSION, "lifetime": "scenario", "builds": 2, "seconds": 4.5},
    ]
