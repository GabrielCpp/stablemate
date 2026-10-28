"""The lap's clone check is replaced by a recording stand-in, so each flow test stays offline."""
from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

import pytest
from workhorse.pyflow.blueprint import NODE_ATTR, node_spec

from workhorse_workflows.coder.dev import flow
from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.schemas.dev import CopyCheck


class CopyStandIn:
    """A `check_copies` node that answers one canned result and records each lap's call."""

    def __init__(self) -> None:
        self.result = CopyCheck()
        self.calls: list[dict[str, Any]] = []
        self.then = CopyCheck()

        def check_copies(
            logger: logging.Logger,
            roots: list[str],
            story_slug: str = "",
            story_id: str = "",
            library_dirs: tuple[str, ...] = (),
        ) -> CopyCheck:
            self.calls.append({"roots": list(roots), "story_slug": story_slug, "story_id": story_id})
            answer, self.result = self.result, self.then
            return answer

        setattr(check_copies, NODE_ATTR, replace(node_spec(flow.check_copies), fn=check_copies))
        self.node = check_copies

    def finds(self, target: str, cwd: str) -> None:
        self.result = CopyCheck(
            findings=[Finding(target=target, issue="a copy", repair="extract it")], cwd=cwd
        )


@pytest.fixture(autouse=True)
def copies(monkeypatch: pytest.MonkeyPatch) -> CopyStandIn:
    stand_in = CopyStandIn()
    monkeypatch.setattr(flow, "check_copies", stand_in.node)
    return stand_in
