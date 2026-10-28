"""The QA flow's check set is replaced by a stand-in, so each flow test stays offline."""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

import pytest
from workhorse.pyflow.blueprint import NODE_ATTR, node_spec

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
