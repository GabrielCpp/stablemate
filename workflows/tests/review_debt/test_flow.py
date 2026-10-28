"""End-to-end `review-debt` runs against a scripted trend-report agent."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from ostler import Ostler
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow.engine import RunEnv

from review_debt.scripted import ScriptedReports, git_out, report, trend_ids
from workhorse_workflows.review_debt.workflow import ReviewDebt

IDS = ["api-cart", "api-auth", "api-old", "web-cart", "web-nav"]


@pytest.fixture
def shelf(file_record: Callable[..., str]) -> list[str]:
    """Five records in two repositories, one of them closed."""
    file_record("api-cart", repo_name="api-service", area="cart")
    file_record("api-auth", repo_name="api-service", area="auth")
    file_record("api-old", repo_name="api-service", area="cart", status="dropped")
    file_record("web-cart", repo_name="web-app", area="cart")
    file_record("web-nav", repo_name="web-app", area="nav")
    return IDS


def _trends(artifacts: Path) -> Path:
    return artifacts / "backlogs" / "trends.md"


def _commits(artifacts: Path) -> int:
    return int(git_out(artifacts, "rev-list", "--count", "HEAD"))


def test_a_complete_report_writes_trends_naming_every_id(
    shelf: list[str],
    artifacts: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = ScriptedReports(report(["api-cart", "web-cart"], ["api-auth", "api-old"], singletons=("web-nav",)))
    before = _commits(artifacts)

    drive_flow(ReviewDebt(), env(), agent)

    text = _trends(artifacts).read_text(encoding="utf-8")
    assert sorted(trend_ids(text)) == sorted(shelf), text
    assert "5 records reviewed" in text, text
    assert "- api-old (api-service/cart, dropped): summary of api-old" in text, text
    assert agent.turns == 1
    assert _commits(artifacts) == before


def test_the_first_turn_is_given_the_listing_and_no_feedback(
    shelf: list[str],
    artifacts: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = ScriptedReports(report(shelf[:2], shelf[2:4], singletons=(shelf[4],)))

    drive_flow(ReviewDebt(), env(), agent)

    first = agent.args[0]
    assert first["feedback"] == "", first
    assert first["shelf"] == str(artifacts / "backlogs"), first
    assert all(i in first["listing"] for i in shelf), first


def test_a_report_missing_an_id_is_sent_back_naming_it(
    shelf: list[str],
    artifacts: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    short = report(["api-cart", "web-cart"], singletons=("api-auth", "api-old"))
    full = report(["api-cart", "web-cart"], singletons=("api-auth", "api-old", "web-nav"))
    agent = ScriptedReports(short, full)

    drive_flow(ReviewDebt(), env(), agent)

    assert agent.turns == 2
    assert "web-nav" in agent.args[1]["feedback"], agent.args[1]
    assert sorted(trend_ids(_trends(artifacts).read_text(encoding="utf-8"))) == sorted(shelf)


def test_three_bad_reports_fail_the_run_with_the_gap_and_write_nothing(
    shelf: list[str],
    artifacts: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    short = report(["api-cart", "web-cart"], singletons=("api-auth", "api-old"))
    agent = ScriptedReports(short, short, short)
    before = _commits(artifacts)

    with pytest.raises(WorkflowFailed, match="web-nav"):
        drive_flow(ReviewDebt(), env(), agent)

    assert agent.turns == 3
    assert not _trends(artifacts).exists()
    assert _commits(artifacts) == before


def test_duplicated_and_unknown_ids_are_named_in_the_feedback(
    shelf: list[str],
    artifacts: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    bad = report(["api-cart", "web-cart"], singletons=("api-cart", "api-auth", "api-old", "web-nav", "ghost"))
    good = report(["api-cart", "web-cart"], singletons=("api-auth", "api-old", "web-nav"))
    agent = ScriptedReports(bad, good)

    drive_flow(ReviewDebt(), env(), agent)

    feedback = agent.args[1]["feedback"]
    assert "ghost" in feedback and "api-cart" in feedback, feedback


def test_an_empty_register_ends_without_a_turn_or_a_file(
    artifacts: Path,
    repo: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = ScriptedReports()

    result = drive_flow(ReviewDebt(), env(), agent)

    assert agent.turns == 0
    assert result.ids == [], result
    assert not _trends(artifacts).exists()
    assert Ostler(repo).records().records == ()
