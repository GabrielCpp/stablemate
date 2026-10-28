"""The decision step of `review-debt`: a cluster at the threshold is drafted into a proposed decision and its records are bound."""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from ostler import Ostler, adr
from ostler.result import Result
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow.engine import RunEnv

from review_debt.scripted import ScriptedReports, git_out, report
from workhorse_workflows.review_debt.nodes import select_candidates
from workhorse_workflows.review_debt.schemas import Cluster, TrendReport
from workhorse_workflows.review_debt.workflow import ReviewDebt

IDS = ["api-cart", "api-auth", "api-old", "web-cart", "web-nav"]
DRAFT = {
    "slug": "guard-cart-total",
    "title": "Guard every cart total",
    "context": "Three records share one unguarded total.",
    "decision": "Guard the total in one module.",
    "consequences": "Callers stop re-checking the total.",
}


@pytest.fixture
def shelf(file_record: Callable[..., str]) -> list[str]:
    """Five records in two repositories."""
    file_record("api-cart", repo_name="api-service", area="cart")
    file_record("api-auth", repo_name="api-service", area="auth")
    file_record("api-old", repo_name="api-service", area="cart")
    file_record("web-cart", repo_name="web-app", area="cart")
    file_record("web-nav", repo_name="web-app", area="nav")
    return IDS


def two_clusters() -> dict[str, Any]:
    return report(["api-cart", "api-auth", "web-cart"], ["api-old", "web-nav"])


def decisions(repo: Path) -> list[Path]:
    return sorted(repo.glob("docs/adrs/*/adr.md"))


def bound(repo: Path) -> dict[str, str]:
    return {r.id: r.decision for r in Ostler(repo).records().records}


def test_a_cluster_of_three_is_drafted_and_a_cluster_of_two_is_left(
    shelf: list[str],
    artifacts: Path,
    repo: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = ScriptedReports(two_clusters(), DRAFT)

    result = drive_flow(ReviewDebt(), env(), agent)

    files = decisions(repo)
    assert len(files) == 1, files
    decision = adr.Decision.read(files[0])
    assert result.decisions == [decision.id], result
    assert decision.status == "proposed"
    assert decision.repos == ["api-service", "web-app"]
    assert sorted(decision.evidence) == ["api-auth", "api-cart", "web-cart"]
    assert decision.title == DRAFT["title"] and decision.decision == DRAFT["decision"]
    assert bound(repo) == {
        "api-cart": decision.id, "api-auth": decision.id, "web-cart": decision.id,
        "api-old": "", "web-nav": "",
    }
    assert agent.turns == 2
    assert files[0] == repo / "docs" / "adrs" / DRAFT["slug"] / "adr.md"
    assert decision.id == DRAFT["slug"]
    assert git_out(artifacts, "log", "-1", "--format=%s").strip() == "init"


def test_the_draft_turn_is_given_the_cluster_and_the_shelf(
    shelf: list[str],
    artifacts: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = ScriptedReports(two_clusters(), DRAFT)

    drive_flow(ReviewDebt(), env(), agent)

    turn = agent.args[1]
    assert turn["name"] == "cause 1" and turn["cause"] == "the same flaw 1", turn
    assert turn["shelf"] == str(artifacts / "backlogs"), turn
    assert all(i in turn["listing"] for i in ("api-cart", "api-auth", "web-cart")), turn
    assert "api-old" not in turn["listing"], turn


def test_a_second_run_over_the_same_register_and_report_proposes_nothing(
    shelf: list[str],
    artifacts: Path,
    repo: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    drive_flow(ReviewDebt(), env(), ScriptedReports(two_clusters(), DRAFT))
    before = bound(repo)
    commits = git_out(artifacts, "rev-list", "--count", "HEAD")
    agent = ScriptedReports(two_clusters())

    result = drive_flow(ReviewDebt(), env("review-debt-again"), agent)

    assert agent.turns == 1
    assert result.decisions == [], result
    assert len(decisions(repo)) == 1
    assert bound(repo) == before
    assert git_out(artifacts, "rev-list", "--count", "HEAD") == commits


def test_bound_records_drop_out_of_a_larger_cluster(
    shelf: list[str],
    repo: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    drive_flow(ReviewDebt(), env(), ScriptedReports(two_clusters(), DRAFT))
    agent = ScriptedReports(report(["api-cart", "api-auth", "web-cart", "api-old"], singletons=("web-nav",)))

    result = drive_flow(ReviewDebt(), env("review-debt-again"), agent)

    assert agent.turns == 1
    assert result.decisions == []
    assert len(decisions(repo)) == 1


def test_a_lower_threshold_drafts_the_smaller_cluster_too(
    shelf: list[str],
    artifacts: Path,
    repo: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    agent = ScriptedReports(two_clusters(), DRAFT, {**DRAFT, "slug": "second-cause", "title": "Second"})

    result = drive_flow(ReviewDebt(decision_threshold=2), env(), agent)

    assert len(decisions(repo)) == 2
    assert len(result.decisions) == 2
    assert all(bound(repo).values())


def test_a_refusal_from_propose_ends_the_run_naming_it(
    shelf: list[str],
    artifacts: Path,
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> Result:
        return Result(False, "record 'web-cart' is already bound to decision 'x-1'")

    monkeypatch.setattr(adr, "propose", refuse)

    with pytest.raises(WorkflowFailed, match="web-cart"):
        drive_flow(ReviewDebt(), env(), ScriptedReports(two_clusters(), DRAFT))


def test_select_candidates_keeps_only_unbound_ids_at_the_threshold(
    shelf: list[str], repo: Path, logger: logging.Logger
) -> None:
    trends = TrendReport(
        clusters=[
            Cluster(name="big", cause="c", ids=["api-cart", "api-auth", "web-cart"]),
            Cluster(name="small", cause="c", ids=["api-old", "web-nav"]),
        ],
        singletons=[],
        summary="s",
    )

    found = select_candidates(logger, trends, 3, repo_dir=str(repo))

    assert [c.name for c in found.clusters] == ["big"]
    assert found.clusters[0].ids == ["api-cart", "api-auth", "web-cart"]
    assert len(found.clusters[0].lines) == 3
