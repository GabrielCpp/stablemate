"""Tests for groom.gates: STATUS-line parsing/writing and answer_gate's
orchestration. The regex/constants here must stay byte-compatible with the
await_operator.py scripts in vigilant-octo/agents, so the parsing tests pin
down the exact on-disk shape those scripts themselves produce and expect.

Run: uv run python tests/test_gates.py   (or via pytest)
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

from groom import gates, state
from groom.models import WorkflowContainer

_GATE_FILE = """STATUS: AWAITING_OPERATOR

## Questions from the agent

Should the fallback default to "unknown" or raise?

## Context

Some other section that must not be swallowed.
"""


def test_status_of_reads_the_status_line():
    assert gates.status_of(_GATE_FILE) == "AWAITING_OPERATOR"
    assert gates.status_of("STATUS: consumed\nrest") == "CONSUMED"
    assert gates.status_of("no status line here") == ""


def test_is_awaiting():
    assert gates.is_awaiting(_GATE_FILE) is True
    assert gates.is_awaiting("STATUS: ANSWERED\n") is False


def test_extract_question_pulls_the_named_section():
    question = gates.extract_question(_GATE_FILE)
    assert question == 'Should the fallback default to "unknown" or raise?'
    assert "Some other section" not in question


def test_extract_question_falls_back_to_whole_text_when_no_header():
    text = "STATUS: AWAITING_OPERATOR\n\njust a blob, no section header"
    assert gates.extract_question(text) == text.strip()


def test_apply_answer_flips_status_and_appends_text():
    new_text = gates.apply_answer(_GATE_FILE, "Default to unknown, never raise.")
    assert new_text.startswith("STATUS: ANSWERED")
    assert new_text.count("STATUS:") == 1
    assert new_text.rstrip().endswith("Default to unknown, never raise.")


def test_apply_answer_with_blank_answer_still_flips_status():
    new_text = gates.apply_answer(_GATE_FILE, "   ")
    assert gates.status_of(new_text) == gates.ANSWERED
    # No trailing answer paragraph is appended for a blank answer.
    assert new_text.rstrip().endswith("Some other section that must not be swallowed.")


def _reset_state():
    state.WORKFLOWS.clear()
    state._gate_locks.clear()


def test_answer_gate_rejects_when_already_answered():
    _reset_state()

    async def scenario():
        with patch.object(gates.docker_io, "read_file", return_value="STATUS: ANSWERED\n"):
            return await gates.answer_gate("abc123", "docs/gate.md", "an answer", workspace_volume="vol-1")

    result = asyncio.run(scenario())
    assert result.ok is False
    assert "already answered" in result.message


def test_answer_gate_writes_answer_no_restart_when_still_running():
    _reset_state()
    from groom.models import GateInfo

    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="demo")
    state.WORKFLOWS["abc123"].gates["docs/gate.md"] = GateInfo(
        workflow_id="abc123", file_path="docs/gate.md", question="q?"
    )

    written = {}

    def _fake_write(volume, rel_path, content):
        written["volume"] = volume
        written["rel_path"] = rel_path
        written["content"] = content
        return True

    async def scenario():
        with patch.object(gates.docker_io, "read_file", return_value=_GATE_FILE), \
             patch.object(gates.docker_io, "write_file", _fake_write), \
             patch.object(gates.docker_io, "is_running", return_value=True), \
             patch.object(gates.docker_io, "docker_start") as fake_start:
            result = await gates.answer_gate("abc123", "docs/gate.md", "Use unknown.", workspace_volume="vol-1")
            fake_start.assert_not_called()
            return result

    result = asyncio.run(scenario())
    assert result.ok is True
    # await_operator.py blocks in place — the normal path never needs a restart.
    assert result.message == "answered"
    assert written["volume"] == "vol-1"
    assert written["rel_path"] == "docs/gate.md"
    assert gates.status_of(written["content"]) == gates.ANSWERED
    # The answered gate is cleared from in-memory state so the UI stops
    # showing a form for it even before the container's own push arrives.
    assert "docs/gate.md" not in state.WORKFLOWS["abc123"].gates


def test_answer_gate_restarts_when_container_stopped():
    """Fallback path: inotify was unavailable and await_operator.py exited,
    or the container predates this redesign — the container is genuinely
    stopped, so answer_gate must still restart it.
    """
    _reset_state()
    from groom.models import GateInfo

    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="demo")
    state.WORKFLOWS["abc123"].gates["docs/gate.md"] = GateInfo(
        workflow_id="abc123", file_path="docs/gate.md", question="q?"
    )

    async def scenario():
        with patch.object(gates.docker_io, "read_file", return_value=_GATE_FILE), \
             patch.object(gates.docker_io, "write_file", return_value=True), \
             patch.object(gates.docker_io, "is_running", return_value=False), \
             patch.object(gates.docker_io, "docker_start", return_value=True) as fake_start:
            result = await gates.answer_gate("abc123", "docs/gate.md", "Use unknown.", workspace_volume="vol-1")
            fake_start.assert_called_once_with("abc123")
            return result

    result = asyncio.run(scenario())
    assert result.ok is True
    assert "restarted" in result.message


def test_answer_gate_reports_missing_workspace_volume():
    _reset_state()

    async def scenario():
        return await gates.answer_gate("abc123", "docs/gate.md", "x", workspace_volume="")

    result = asyncio.run(scenario())
    assert result.ok is False
    assert "workspace volume" in result.message


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
