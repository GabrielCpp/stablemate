"""Tests for the pi backend (``runner/backends/pi.py``): its command line, its events, its rpc compaction and its transcript store."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from workhorse.config_run import AgentResilience
from workhorse.runner import transcript
from workhorse.runner.backends import AgentProfile, turn
from workhorse.runner.backends.pi import PiBackend, _on_event

RESILIENCE = AgentResilience()
FIXTURE = Path(__file__).parent / "fixtures" / "pi_turn.jsonl"
SESSION = "0b1f6c1e-2d4a-4a56-9d0e-3a7c5f1e9b21"


def _run(
    tmp_path: Path,
    sid: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    add_dirs: list[str] | None = None,
) -> list[list[str]]:
    commands: list[list[str]] = []

    def _record(
        cmd: list[str],
        node_id: str,
        timeout: float,
        stdin_data: str | None,
        on_event: object,
        **extra: object,
    ) -> turn.TurnState:
        commands.append(cmd)
        return turn.TurnState(result_text="OK", session_id="t")

    sid_path = tmp_path / ".sid"
    if sid:
        sid_path.write_text(sid)
    _ = PiBackend(_record).run_turn(
        "P",
        "n",
        sid_path,
        timeout=RESILIENCE.result_timeout_s,
        resilience=RESILIENCE,
        agent=AgentProfile(name="free"),
        model=model,
        effort=effort,
        add_dirs=add_dirs,
    )
    return commands


def test_a_turn_runs_pi_in_json_mode_with_the_model_the_effort_and_a_session_id(
    tmp_path: Path,
) -> None:
    (cmd,) = _run(tmp_path, model="openrouter/acme/model", effort="high")
    assert cmd[:7] == [
        "pi",
        "--mode",
        "json",
        "--model",
        "openrouter/acme/model",
        "--thinking",
        "high",
    ]
    assert cmd[7] == "--session-id" and cmd[8]
    assert cmd[-1] == "P"


def test_a_resumed_turn_reuses_the_session_id(tmp_path: Path) -> None:
    (cmd,) = _run(tmp_path, sid="sess-1")
    assert cmd[cmd.index("--session-id") + 1] == "sess-1"


def test_each_extra_dir_adds_a_skill_flag_per_skills_folder_it_holds(
    tmp_path: Path,
) -> None:
    extra = tmp_path / "extra"
    (extra / ".agents" / "skills").mkdir(parents=True)
    (extra / ".claude" / "skills").mkdir(parents=True)
    bare = tmp_path / "bare"
    bare.mkdir()
    (cmd,) = _run(tmp_path, add_dirs=[str(extra), str(bare)])
    flags = [cmd[i + 1] for i, part in enumerate(cmd) if part == "--skill"]
    assert flags == [str(extra / ".agents/skills"), str(extra / ".claude/skills")]


def test_the_recorded_turn_gives_its_last_answer_its_session_and_its_summed_usage() -> (
    None
):
    state = turn.TurnState()
    for line in FIXTURE.read_text().splitlines():
        _on_event(json.loads(line), state, "n")
    assert state.session_id == SESSION
    assert state.result_text == "README.md"
    assert state.usage.input_tokens == 320
    assert state.usage.output_tokens == 38
    assert state.usage.cache_read_input_tokens == 50
    assert state.usage.cache_creation_input_tokens == 5
    assert state.usage.total_cost_usd == pytest.approx(0.006)
    assert state.usage.steps == 2


def test_an_assistant_stop_on_an_error_lands_in_the_diagnostics() -> None:
    state = turn.TurnState()
    _on_event(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [],
                "stopReason": "error",
                "errorMessage": "401 no key",
            },
        },
        state,
        "n",
    )
    assert state.diagnostics == ["401 no key"]


def _fake_pi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, response: str) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    seen = tmp_path / "seen.txt"
    script = bin_dir / "pi"
    script.write_text(
        "#!/usr/bin/env python3\nimport sys\n"
        f"open({str(seen)!r}, 'w').write(' '.join(sys.argv[1:]) + '\\n' + sys.stdin.readline())\n"
        f"print({response!r}, flush=True)\n"
        "sys.stdin.read()\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return seen


def _session_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / "pi"))
    session = (
        tmp_path
        / "pi"
        / "sessions"
        / "--work-acme--"
        / "2026-11-25T10-00-00-000Z_sess-9.jsonl"
    )
    session.parent.mkdir(parents=True)
    session.write_text("{}\n")
    return session


def _compact(tmp_path: Path, model: str | None = None) -> bool:
    sid_path = tmp_path / ".sid"
    sid_path.write_text("sess-9")
    return PiBackend().compact(sid_path, "n", model, timeout=20, resilience=RESILIENCE)


def test_compaction_writes_the_compact_command_to_pi_rpc_and_reports_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _fake_pi(
        tmp_path,
        monkeypatch,
        json.dumps({"type": "response", "command": "compact", "success": True}),
    )
    session = _session_file(tmp_path, monkeypatch)
    assert _compact(tmp_path, "acme/model") is True
    argv, sent = seen.read_text().split("\n", 1)
    assert argv == f"--mode rpc --model acme/model --session {session}"
    assert json.loads(sent) == {"type": "compact"}


def test_a_compact_response_with_success_false_is_a_failed_compaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_pi(
        tmp_path,
        monkeypatch,
        json.dumps(
            {
                "type": "response",
                "command": "compact",
                "success": False,
                "error": "nothing to compact",
            }
        ),
    )
    _session_file(tmp_path, monkeypatch)
    assert _compact(tmp_path) is False


def test_compaction_finds_no_session_file_and_fails_without_starting_pi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _fake_pi(
        tmp_path,
        monkeypatch,
        json.dumps({"type": "response", "command": "compact", "success": True}),
    )
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / "pi"))
    assert _compact(tmp_path) is False
    assert not seen.exists()


def test_compaction_without_a_session_or_without_pi_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert PiBackend().compact(None, "n", timeout=5, resilience=RESILIENCE) is False
    monkeypatch.setenv("PATH", str(tmp_path))
    _session_file(tmp_path, monkeypatch)
    assert _compact(tmp_path) is False


def test_the_transcript_store_finds_the_session_file_under_the_pi_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    session = (
        tmp_path
        / "sessions"
        / "--work-acme--"
        / f"2026-11-25T10-00-00-000Z_{SESSION}.jsonl"
    )
    session.parent.mkdir(parents=True)
    session.write_text("{}\n")
    assert transcript._pi_store(SESSION) == [session]
    assert transcript._pi_store("other") == []
