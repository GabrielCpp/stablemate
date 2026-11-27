"""The lap's clone check is replaced by a recording stand-in, so each flow test stays offline."""
from __future__ import annotations

import logging
from dataclasses import replace
from collections.abc import Callable
from pathlib import Path
from typing import Any
import subprocess

import pytest
from workhorse.pyflow.blueprint import NODE_ATTR, node_spec

from _epics import epics_root
from coder.dev.story import EPIC, STORY, STORY_MD
from workhorse_workflows.coder.dev import gates
from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.schemas.dev import CheckSet, CopyCheck, DispatchEntry


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

        setattr(check_copies, NODE_ATTR, replace(node_spec(gates.check_copies), fn=check_copies))
        self.node = check_copies

    def finds(self, target: str, cwd: str) -> None:
        self.result = CopyCheck(
            findings=[Finding(target=target, issue="a copy", repair="extract it")], cwd=cwd
        )


@pytest.fixture(autouse=True)
def copies(monkeypatch: pytest.MonkeyPatch) -> CopyStandIn:
    stand_in = CopyStandIn()
    monkeypatch.setattr(gates, "check_copies", stand_in.node)
    return stand_in


class CheckSetStandIn:
    """A `resolve_check_set` node that answers the dispatch it was given and records each call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.added: list[DispatchEntry] = []

        def resolve_check_set(
            logger: logging.Logger,
            dispatch: tuple[DispatchEntry, ...],
            story_slug: str = "",
            story_id: str = "",
            repo_dir: str = "",
            workspace: str = "",
        ) -> CheckSet:
            self.calls.append(
                {"dispatch": list(dispatch), "story_slug": story_slug, "story_id": story_id}
            )
            return CheckSet(checks=[*dispatch, *self.added])

        setattr(
            resolve_check_set,
            NODE_ATTR,
            replace(node_spec(gates.resolve_check_set), fn=resolve_check_set),
        )
        self.node = resolve_check_set

    def adds(self, entry: DispatchEntry) -> None:
        self.added.append(entry)


@pytest.fixture(autouse=True)
def check_set(monkeypatch: pytest.MonkeyPatch) -> CheckSetStandIn:
    stand_in = CheckSetStandIn()
    monkeypatch.setattr(gates, "resolve_check_set", stand_in.node)
    return stand_in


@pytest.fixture
def docs(
    repo: Path,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> Path:
    """The docs repo, carrying one epic with one story, committed so the tree starts clean."""
    write(
        epics_root() / EPIC / "epic.md",
        f"---\ntitle: Epic One\nstatus: active\n---\n\n# Epic One\n\n## Stories\n\n"
        f"### {STORY}\n\n- title: Story {STORY}\n",
    )
    write(epics_root() / EPIC / "stories" / STORY / "story.md", STORY_MD)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "Plan one epic", "--allow-empty")
    return repo


@pytest.fixture
def workspace(
    tmp_path: Path,
    docs: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    name_workspace: Callable[[dict[str, Path]], None],
) -> dict[str, Path]:
    """One real code repo and the named workspace that lists it, outside the docs tree."""
    root = tmp_path / "ws"
    api = root / "api"
    api.mkdir(parents=True)
    git(api, "init", "-q", "-b", "main")
    write(api / "README.md", "# api\n")
    git(api, "add", "-A")
    git(api, "commit", "-qm", "Initial commit")
    name_workspace({"api": api})
    return {"api": api}
