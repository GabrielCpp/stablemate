"""Copilot's ``result`` event carries no token counts, so a turn reports none."""

from __future__ import annotations

from workhorse.runner.backends import copilot
from workhorse.runner.backends.turn import TurnState

RESULT = {
    "type": "result",
    "sessionId": "d2c237e8-59b4-4018-b469-a740d3bced99",
    "exitCode": 0,
    "usage": {
        "premiumRequests": 1,
        "totalApiDurationMs": 2024,
        "sessionDurationMs": 4743,
        "codeChanges": {"linesAdded": 0, "linesRemoved": 0, "filesModified": []},
    },
}


def test_a_result_event_adds_no_tokens_or_cost_to_the_turn():
    state = TurnState()
    copilot._on_event(RESULT, state, "n")
    assert state.usage.token_counts() == {}
    assert state.usage.total_cost_usd is None
    assert state.session_id == RESULT["sessionId"]


def test_two_results_on_one_session_still_report_nothing():
    state = TurnState()
    copilot._on_event(RESULT, state, "n")
    copilot._on_event(RESULT, state, "n")
    assert state.usage.is_empty
