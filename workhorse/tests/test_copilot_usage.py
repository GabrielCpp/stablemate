"""Copilot's stdout ``result`` event carries no token counts, so a turn reads them from the session log."""

from __future__ import annotations

import json
from pathlib import Path

from workhorse.runner.backends import copilot
from workhorse.runner.backends.turn import TurnState

SESSION = "d2c237e8-59b4-4018-b469-a740d3bced99"
RESULT = {
    "type": "result",
    "sessionId": SESSION,
    "exitCode": 0,
    "usage": {
        "premiumRequests": 15,
        "totalApiDurationMs": 2024,
        "sessionDurationMs": 4743,
        "codeChanges": {"linesAdded": 0, "linesRemoved": 0, "filesModified": []},
    },
}


def usage_record(input_tokens, output, read, write, reasoning, sequence=1):
    return {
        "type": "session.usage_record",
        "data": {
            "usage": {
                "accounting": {"sourceSessionId": SESSION, "sequence": sequence},
                "model": "example-model",
                "inputTokens": input_tokens,
                "outputTokens": output,
                "cacheReadTokens": read,
                "cacheWriteTokens": write,
                "reasoningTokens": reasoning,
                "cost": 15.0,
            }
        },
    }


def write_log(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in events))


def run_turn(home: Path, baseline: int = 0) -> TurnState:
    state = TurnState()
    handle = copilot._with_session_usage(copilot._on_event, str(home), baseline)
    handle(RESULT, state, "n")
    return state


def log_path(home: Path) -> Path:
    return home / "session-state" / SESSION / "events.jsonl"


def test_a_result_event_alone_adds_no_tokens_or_cost_to_the_turn():
    state = TurnState()
    copilot._on_event(RESULT, state, "n")
    assert state.usage.token_counts() == {}
    assert state.usage.total_cost_usd is None
    assert state.session_id == SESSION


def test_two_usage_records_of_one_turn_sum_into_the_canonical_fields(tmp_path):
    write_log(
        log_path(tmp_path),
        [
            {"type": "session.start", "data": {}},
            {"type": "user.message", "data": {}},
            usage_record(32889, 4, 0, 32885, 0, 1),
            usage_record(33540, 300, 32889, 647, 120, 2),
        ],
    )
    usage = run_turn(tmp_path).usage
    assert usage.token_counts() == {
        "input_tokens": 4 + 4,
        "output_tokens": 304,
        "cache_read_input_tokens": 32889,
        "cache_creation_input_tokens": 33532,
        "reasoning_output_tokens": 120,
    }


def test_the_premium_request_cost_is_not_recorded_as_dollars(tmp_path):
    write_log(log_path(tmp_path), [usage_record(100, 5, 0, 90, 0)])
    assert run_turn(tmp_path).usage.total_cost_usd is None


def test_records_before_the_baseline_belong_to_an_earlier_turn(tmp_path):
    earlier = [
        {"type": "session.start", "data": {}},
        usage_record(32889, 4, 0, 32885, 0, 1),
    ]
    this_turn = [
        {"type": "session.resume", "data": {}},
        usage_record(32934, 6, 32889, 41, 2, 2),
    ]
    write_log(log_path(tmp_path), [*earlier, *this_turn])
    usage = run_turn(tmp_path, baseline=len(earlier)).usage
    assert usage.token_counts() == {
        "input_tokens": 4,
        "output_tokens": 6,
        "cache_read_input_tokens": 32889,
        "cache_creation_input_tokens": 41,
        "reasoning_output_tokens": 2,
    }


def test_uncached_input_never_goes_negative(tmp_path):
    write_log(log_path(tmp_path), [usage_record(10, 1, 8, 8, 0)])
    assert run_turn(tmp_path).usage.input_tokens == 0


def test_a_missing_session_log_leaves_the_turn_without_tokens(tmp_path):
    usage = run_turn(tmp_path).usage
    assert usage.token_counts() == {}
    assert usage.total_cost_usd is None


def test_a_torn_last_line_is_skipped(tmp_path):
    write_log(log_path(tmp_path), [usage_record(100, 5, 0, 90, 0)])
    with log_path(tmp_path).open("a") as f:
        f.write('{"type": "session.usage_rec')
    assert run_turn(tmp_path).usage.output_tokens == 5
