"""Accounting: every id the review read appears in the report exactly once."""
from __future__ import annotations

import logging

from workhorse_workflows.review_debt.nodes import account
from workhorse_workflows.review_debt.schemas import Cluster, Singleton, TrendReport

READ = ["a", "b", "c", "d"]


def _report(clusters: list[list[str]], singletons: list[str]) -> TrendReport:
    return TrendReport(
        clusters=[Cluster(name=f"c{n}", cause="shared", ids=ids) for n, ids in enumerate(clusters)],
        singletons=[Singleton(id=i, cause="alone") for i in singletons],
        summary="s",
    )


def test_an_exact_cover_is_ok(logger: logging.Logger) -> None:
    accounting = account(logger, READ, _report([["a", "b"]], ["c", "d"]))

    assert accounting.ok, accounting
    assert (accounting.missing, accounting.duplicated, accounting.unknown) == ([], [], [])


def test_a_missing_id_is_named(logger: logging.Logger) -> None:
    accounting = account(logger, READ, _report([["a", "b"]], ["c"]))

    assert not accounting.ok
    assert accounting.missing == ["d"]
    assert (accounting.duplicated, accounting.unknown) == ([], [])


def test_a_duplicated_id_is_named_across_a_cluster_and_a_singleton(logger: logging.Logger) -> None:
    accounting = account(logger, READ, _report([["a", "b"]], ["b", "c", "d"]))

    assert not accounting.ok
    assert accounting.duplicated == ["b"]
    assert (accounting.missing, accounting.unknown) == ([], [])


def test_an_id_twice_in_one_cluster_is_duplicated(logger: logging.Logger) -> None:
    accounting = account(logger, READ, _report([["a", "a"]], ["b", "c", "d"]))

    assert accounting.duplicated == ["a"]


def test_an_unknown_id_is_named(logger: logging.Logger) -> None:
    accounting = account(logger, READ, _report([["a", "b"]], ["c", "d", "ghost"]))

    assert not accounting.ok
    assert accounting.unknown == ["ghost"]
    assert (accounting.missing, accounting.duplicated) == ([], [])
