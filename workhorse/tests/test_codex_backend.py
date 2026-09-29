"""Tests for how the codex backend runs a confined turn behind its guard hook (``runner/backends/codex.py``)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

from workhorse.config_run import AgentResilience
from workhorse.runner import process
from workhorse.runner.backends import AgentProfile, codex, jsonl, turn
from workhorse.runner.backends.codex import CodexBackend
from workhorse.runner.backends.codex_guard import Policy

RESILIENCE = AgentResilience()


@dataclass(frozen=True)
class _GuardedCall:
    hooks: str
    policy_path: Path
    policy: Policy


@pytest.fixture(autouse=True)
def _no_codex_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEX_PROFILE", raising=False)


def _run_turn(backend: CodexBackend, root: Path, agent: AgentProfile, cwd: str | None = None, add_dirs: list[str] | None = None) -> None:
    _ = backend.run_turn(
        "P", "n", root / ".sid", timeout=RESILIENCE.result_timeout_s, resilience=RESILIENCE, cwd=cwd, add_dirs=add_dirs, agent=agent
    )


def test_codex_runs_a_confined_turn_behind_the_guard_hook_and_removes_its_policy_after(tmp_path: Path) -> None:
    """A confined codex turn runs outside the sandbox, so every tool call passes the guard, which reads the turn's policy."""
    root = tmp_path.resolve()
    (root / ".git").mkdir()
    (root / "docs").mkdir()
    (root / ".claude" / "skills").mkdir(parents=True)
    agent = AgentProfile(name="docs", tools={"*": False}, confined=True, commands=("ostler",))
    calls: list[_GuardedCall] = []

    def _run_codex_recording_the_guard(cmd: list[str], node_id: str, timeout: float, stdin_data: str | None, on_event: object, **kwargs: object) -> turn.TurnState:
        hooks = cmd[cmd.index("--dangerously-bypass-hook-trust") + 2]
        policy_path = Path(hooks.split(" ")[-1].rstrip('"}]'))
        calls.append(_GuardedCall(hooks, policy_path, Policy.from_json(policy_path.read_text(encoding="utf-8"))))
        return turn.TurnState(result_text="OK", session_id="t")

    _run_turn(CodexBackend(_run_codex_recording_the_guard), root, cwd=str(root / "docs"), add_dirs=[str(root / "src")], agent=agent)

    (call,) = calls
    assert "codex_guard" in call.hooks
    assert call.policy == Policy(
        cwd=root / "docs",
        read_roots=(root / "docs", root / "src", root / ".claude" / "skills"),
        commands=("ostler",),
    )
    assert not call.policy_path.exists()


def test_codex_runs_an_unconfined_turn_without_the_guard(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def _run_codex_recording_the_command(cmd: list[str], node_id: str, timeout: float, stdin_data: str | None, on_event: object, **kwargs: object) -> turn.TurnState:
        commands.append(cmd)
        return turn.TurnState(result_text="OK", session_id="t")

    _run_turn(CodexBackend(_run_codex_recording_the_command), tmp_path, agent=AgentProfile(name="free"))

    (cmd,) = commands
    assert "--dangerously-bypass-hook-trust" not in cmd


def test_codex_hook_notices_neither_fail_nor_end_the_turn() -> None:
    """A refused command, a patch that missed and the hook-trust warning are events of a guarded turn, not failures, even when one names a timeout."""
    lines = [
        json.dumps({"type": "item.completed", "item": {"id": "item_0", "type": "error", "message": "`--dangerously-bypass-hook-trust` is enabled. Hooks may run."}}),
        "2026-01-01T00:00:00Z ERROR codex_core::tools::router: error=Command blocked by PreToolUse hook: Refused. Command: timeout 60 cat x",
        "2026-01-01T00:00:00.503861Z ERROR codex_core::tools::router: error=apply_patch verification failed: Failed to find expected lines in a.md:",
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "DONE"}}),
    ]

    def fake_stream(cmd: list[str], node_id: str, timeout: float, on_line, **kwargs: object) -> tuple[bool, int]:
        return any(on_line(raw) for raw in lines), 0

    with patch.object(process, "stream_subprocess", fake_stream):
        state = jsonl.stream_jsonl(["codex"], "n", 3600, None, codex._on_event, resilience=RESILIENCE, non_failure_markers=codex.NON_FAILURE_MARKERS)
    assert state.diagnostics == []
    assert not state.timed_out
    assert state.result_text == "DONE"



def test_the_file_text_a_missed_patch_quotes_is_no_provider_outage() -> None:
    """A page that documents a 500 must not read as the provider answering one when a patch against it misses."""
    lines = [
        "2026-01-01T00:00:00.503861Z ERROR codex_core::tools::router: error=apply_patch verification failed: Failed to find expected lines in a.md:",
        "- emits: `500` [Problem response](../formats/problem-response.md) for any other service failure",
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "DONE"}}),
    ]

    def fake_stream(cmd: list[str], node_id: str, timeout: float, on_line, **kwargs: object) -> tuple[bool, int]:
        return any(on_line(raw) for raw in lines), 0

    with patch.object(process, "stream_subprocess", fake_stream):
        state = jsonl.stream_jsonl(["codex"], "n", 3600, None, codex._on_event, resilience=RESILIENCE, non_failure_markers=codex.NON_FAILURE_MARKERS)
    assert state.diagnostics == []
    assert not state.timed_out
    assert state.result_text == "DONE"


def test_a_log_record_after_a_missed_patch_is_still_a_diagnostic() -> None:
    """Only the missed patch's own quoted lines are excused, not the next failure the CLI logs."""
    lines = [
        "2026-01-01T00:00:00Z ERROR codex_core::tools::router: error=apply_patch verification failed: Failed to find expected lines in a.md:",
        "- a quoted line",
        "2026-01-01T00:00:01Z ERROR codex_api: stream disconnected: 503 Service Unavailable",
    ]

    def fake_stream(cmd: list[str], node_id: str, timeout: float, on_line, **kwargs: object) -> tuple[bool, int]:
        return any(on_line(raw) for raw in lines), 0

    with patch.object(process, "stream_subprocess", fake_stream):
        state = jsonl.stream_jsonl(["codex"], "n", 3600, None, codex._on_event, resilience=RESILIENCE, non_failure_markers=codex.NON_FAILURE_MARKERS)
    assert state.diagnostics == [lines[2]]
    assert state.timed_out


def test_codex_other_tool_router_errors_stay_diagnostics() -> None:
    """A tool failure the router reports that is neither a refusal nor a missed patch is still a failure of the turn."""
    lines = [
        "2026-01-01T00:00:00Z ERROR codex_core::tools::router: error=exec_command failed: sandbox denied",
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "DONE"}}),
    ]

    def fake_stream(cmd: list[str], node_id: str, timeout: float, on_line, **kwargs: object) -> tuple[bool, int]:
        return any(on_line(raw) for raw in lines), 0

    with patch.object(process, "stream_subprocess", fake_stream):
        state = jsonl.stream_jsonl(["codex"], "n", 3600, None, codex._on_event, resilience=RESILIENCE, non_failure_markers=codex.NON_FAILURE_MARKERS)
    assert [d for d in state.diagnostics if "sandbox denied" in d]

if __name__ == "__main__":
    import subprocess
    import sys

    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
