"""The QA flow's check set is replaced by a stand-in, so each flow test stays offline."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from workhorse.pyflow.blueprint import NODE_ATTR, node_spec
from workhorse.pyflow.engine import RunEnv

from coder.qa.test_flow import BOOK_CALLS, STORY, _Agent, _Ostler, docs, ostler, spec_dir
from workhorse_workflows.coder.qa import flow
from workhorse_workflows.coder.shared.schemas.dev import CheckSet, DispatchEntry


class CheckSetStandIn:
    """A `resolve_check_set` node that answers the dispatch it was given plus any shared paths."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.shared: list[str] = []

        def resolve_check_set(
            logger: logging.Logger,
            dispatch: tuple[DispatchEntry, ...],
            story_slug: str = "",
            story_id: str = "",
            repo_dir: str = "",
            workspace: str = "",
        ) -> CheckSet:
            self.calls.append({"dispatch": list(dispatch), "story_slug": story_slug, "story_id": story_id})
            return CheckSet(checks=list(dispatch), shared=list(self.shared))

        setattr(
            resolve_check_set,
            NODE_ATTR,
            replace(node_spec(flow.resolve_check_set), fn=resolve_check_set),
        )
        self.node = resolve_check_set


@pytest.fixture(autouse=True)
def check_set(monkeypatch: pytest.MonkeyPatch) -> CheckSetStandIn:
    stand_in = CheckSetStandIn()
    monkeypatch.setattr(flow, "resolve_check_set", stand_in.node)
    return stand_in


class BooksLeft(NamedTuple):
    """What a QA pass after the books shows: the seat's calls, the owed claims, the result and the scripted ostler."""

    agent: _Agent
    owed: list[str]
    result: Any
    okf: _Ostler


@pytest.fixture
def qa_after_books(
    docs: Path,
    ostler: Callable[..., _Ostler],
    write_json: Callable[[Path, Any], Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> Callable[[dict[str, Any]], BooksLeft]:
    """Run QA after the books left `record`."""

    def run(record: dict[str, Any]) -> BooksLeft:
        okf = ostler()
        write_json(docs / spec_dir() / "book-qa.json", {"services": BOOK_CALLS, **record})
        agent = _Agent(docs)
        result = drive_flow(flow.Qa(story=STORY), env(), agent)
        owed = json.loads((docs / spec_dir() / "qa-unreached.json").read_text(encoding="utf-8"))
        return BooksLeft(agent, owed, result, okf)

    return run


__all__ = ["BooksLeft", "docs", "ostler", "qa_after_books"]
