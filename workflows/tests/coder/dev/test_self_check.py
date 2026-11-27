"""The dev check's self-check: a scoped rerun of the scenarios QA failed, on a stack the dev run leases."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import pytest
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows.coder.shared.schemas.qa import StackStatus
from workhorse_workflows.kit.qa import runner as qa_runner
from workhorse_workflows.kit.qa.runner import copy_lease
from workhorse_workflows.kit.qa.schemas import QaPlanRun
from coder.dev.fake_agent import FakeAgent
from coder.dev.story import STORY, make_dev


class _Stack:
    """The stack nodes, scripted: what the scoped rerun returns, and every call the flow made."""

    def __init__(
        self,
        status: Literal["passed", "failed", "invalid"] = "passed",
        ready: Literal["yes", "no", "unneeded"] = "yes",
        failed: tuple[str, ...] = (),
        red: int = 0,
    ) -> None:
        self.status: Literal["passed", "failed", "invalid"] = status
        self.red = red
        self.ready: Literal["yes", "no", "unneeded"] = ready
        self.failed = failed
        self.calls: list[str] = []
        self.leases: list[str] = []
        self.only: list[str] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(qa_runner, "story_near", lambda _root, _services=(), _package="": "book")
        monkeypatch.setattr(qa_runner, "stack_env", self.env)
        monkeypatch.setattr(qa_runner, "ensure_stack", self.ensure)
        monkeypatch.setattr(qa_runner, "run_qa_plan", self.run)
        monkeypatch.setattr(qa_runner, "release_copy", self.release)

    def env(self, _root: Any, near: str = "", lease: str = "", repo_dir: str = "") -> dict[str, str]:
        self.calls.append("stack_target")
        self.leases.append(lease)
        return {}

    def ensure(self, _log: Any, **_k: Any) -> StackStatus:
        self.calls.append("ensure_stack")
        return StackStatus(ready=self.ready)

    def run(self, _log: Any, only: list[str] | None = None, **_k: Any) -> QaPlanRun:
        self.calls.append("run_qa_plan")
        self.only = list(only or [])
        reruns = self.calls.count("run_qa_plan")
        status: Literal["passed", "failed", "invalid"] = "failed" if reruns <= self.red else self.status
        scenarios = {sid: {"status": "failed"} for sid in self.failed} if status == "failed" else {}
        return QaPlanRun(status=status, ostler={"scenarios": scenarios})

    def release(self, _log: Any, **_k: Any) -> None:
        self.calls.append("release_copy")
        return None


def test_no_failed_record_touches_no_stack(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A story QA never failed finishes without a stack node running."""
    stack = _Stack()
    stack.install(monkeypatch)

    result = drive_flow(make_dev(docs), env(), FakeAgent(workspace))

    assert result.status == "ready", result
    assert stack.calls == [], stack.calls


def test_failed_scenarios_that_now_pass_finish(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scoped rerun runs only the failed ids, and a pass lets the item leave dev."""
    stack = _Stack()
    stack.install(monkeypatch)
    agent = FakeAgent(workspace, failed=("scenario-b", "scenario-a"))

    result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 1}, agent.counts()
    assert stack.only == ["scenario-a", "scenario-b"], stack.only
    assert stack.calls == ["stack_target", "ensure_stack", "run_qa_plan", "release_copy"], stack.calls


def test_a_scenario_that_still_fails_goes_back_to_review(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A red rerun is the next turn's report, names the ids, and spends one repair lap."""
    stack = _Stack(failed=("scenario-a",), red=1)
    stack.install(monkeypatch)
    agent = FakeAgent(workspace, failed=("scenario-a",))

    result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 2}, agent.counts()
    first, second = agent.args_for("dev-review")
    assert first["report"] == "", first
    assert "scenario-a" in str(second["report"]), second
    assert stack.calls.count("release_copy") == stack.calls.count("run_qa_plan") == 2, stack.calls


def test_a_scoped_run_that_does_not_finish_lets_the_item_leave(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unfinished or unreachable rerun is QA's to own, and the copy is still released."""
    stack = _Stack(status="invalid")
    stack.install(monkeypatch)
    agent = FakeAgent(workspace, failed=("scenario-a",))

    result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 1}, agent.counts()
    assert stack.calls[-1] == "release_copy", stack.calls


def test_a_stack_that_will_not_come_up_is_skipped_and_released(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No stack means no rerun and no repair turn, and the lease is still released."""
    stack = _Stack(ready="no")
    stack.install(monkeypatch)
    agent = FakeAgent(workspace, failed=("scenario-a",))

    result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert stack.calls == ["stack_target", "ensure_stack", "release_copy"], stack.calls


def test_the_dev_lease_is_not_the_qa_lease(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dev's copy of the stack carries its own name, so it never collides with QA's."""
    stack = _Stack()
    stack.install(monkeypatch)
    run_env = env()

    drive_flow(make_dev(docs), run_env, FakeAgent(workspace, failed=("scenario-a",)))

    (lease,) = stack.leases
    assert lease != copy_lease(STORY, "t"), lease
    assert lease.endswith("-dev"), lease


def test_a_second_failing_self_check_hands_the_item_to_qa(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The self-check bounces dev once, and a still-red rerun then finishes the item and says QA owns it."""
    stack = _Stack(failed=("scenario-a",), red=5)
    stack.install(monkeypatch)
    agent = FakeAgent(workspace, failed=("scenario-a",))

    with caplog.at_level("INFO"):
        result = drive_flow(make_dev(docs), env(), agent)

    assert result.status == "ready", result
    assert agent.counts() == {"dev-plan": 1, "dev-build": 1, "dev-review": 2}, agent.counts()
    assert stack.calls.count("run_qa_plan") == 2, stack.calls
    assert stack.calls.count("release_copy") == 2, stack.calls
    assert "scenario-a" in str(agent.args_for("dev-review")[1]["report"])
    assert any(
        "self-check: 1 scenario(s) still fail after one bounce, QA owns them now: scenario-a"
        in r.getMessage()
        for r in caplog.records
    ), [r.getMessage() for r in caplog.records]
