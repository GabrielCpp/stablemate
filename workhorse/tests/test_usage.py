"""Tests for workhorse/runner/usage.py — cross-harness token/cost normalization.

The event payloads below are the real shapes, captured from the installed CLIs on
2026-07-27 (claude 2.1.220, codex 0.128.0, opencode 1.18.3). They are pasted verbatim
rather than minimized so that a future CLI upgrade that changes a key is caught by a
test that still looks like the thing it models.

Run: ./.venv/bin/python tests/test_usage.py   (or via pytest)
"""
from __future__ import annotations

import importlib

from _fakes import present

usage = importlib.import_module("workhorse.runner.usage")


# --------------------------------------------------------------------------- #
# Captured events
# --------------------------------------------------------------------------- #

CLAUDE_RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "duration_ms": 8423,
    "num_turns": 3,
    "result": "done",
    "session_id": "abc-123",
    "total_cost_usd": 0.0412,
    "usage": {
        "input_tokens": 4,
        "cache_creation_input_tokens": 12034,
        "cache_read_input_tokens": 31288,
        "output_tokens": 517,
    },
}

# Captured from a real `copilot -p … --output-format json` turn (CLI 1.0.65,
# 2026-08-05) — the shape this module could previously only guess at. Copilot's
# `usage` names none of the token fields: `premiumRequests` is a *request* count,
# which is what Copilot actually bills, and the two durations are wall clock.
COPILOT_RESULT = {
    "type": "result",
    "timestamp": "2026-08-05T18:41:09.264Z",
    "sessionId": "d2c237e8-59b4-4018-b469-a740d3bced99",
    "exitCode": 0,
    "usage": {
        "premiumRequests": 1,
        "totalApiDurationMs": 2024,
        "sessionDurationMs": 4743,
        "codeChanges": {"linesAdded": 0, "linesRemoved": 0, "filesModified": []},
    },
}

CODEX_TURN_COMPLETED = {
    "type": "turn.completed",
    "usage": {
        "input_tokens": 20876,
        "cached_input_tokens": 2432,
        "output_tokens": 5,
        "reasoning_output_tokens": 0,
    },
}

# opencode emits one of these per STEP; a turn that calls two tools emits two.
def _opencode_step(inp: int, out: int, read: int, write: int, cost: float) -> dict:
    return {
        "type": "step_finish",
        "part": {
            "id": "prt_1",
            "type": "step-finish",
            "tokens": {
                "input": inp,
                "output": out,
                "reasoning": 0,
                "cache": {"read": read, "write": write},
            },
            "cost": cost,
        },
    }


# --------------------------------------------------------------------------- #
# normalize()
# --------------------------------------------------------------------------- #


def test_claude_result_keeps_its_own_key_names():
    """Claude's spelling IS the canonical spelling — the store already holds spans
    using it, so normalize must be the identity on these fields."""
    got = usage.normalize(CLAUDE_RESULT)
    assert got.token_counts() == {
        "input_tokens": 4,
        "output_tokens": 517,
        "cache_read_input_tokens": 31288,
        "cache_creation_input_tokens": 12034,
    }, got
    assert got.total_cost_usd == 0.0412
    assert got.duration_ms == 8423


def test_copilot_reports_no_tokens_and_no_money():
    """Verified against a live CLI turn, not inferred.

    Copilot bills in *premium requests*, not tokens, and its result event carries no
    token counts and no currency at all. Everything is therefore absent — which is the
    correct answer, and the one the tolerant search has to arrive at without being
    told: `codeChanges` is a nested dict of integers sitting right beside `usage`, and
    latching onto it would invent counts out of a lines-changed tally.
    """
    got = usage.normalize(COPILOT_RESULT)
    assert got.token_counts() == {}, got
    assert got.total_cost_usd is None, got
    assert got.duration_ms is None, got
    # And so the whole turn reports nothing, which is what routes it past
    # `finalize_turn`'s `is_empty` guard: no usage attributes reach the span, and
    # duration falls back to the engine's own wall clock in `turn_end`.
    assert got.is_empty, got


def test_codex_cached_input_maps_onto_cache_read():
    got = usage.normalize(CODEX_TURN_COMPLETED)
    assert got.token_counts() == {
        "input_tokens": 20876,
        "output_tokens": 5,
        "cache_read_input_tokens": 2432,
        "reasoning_output_tokens": 0,
    }, got
    # Codex reports no money under subscription auth. Absent, not zero — a
    # fabricated 0.0 would average into "this turn was free".
    assert got.total_cost_usd is None, got
    assert got.duration_ms is None, got


def test_opencode_nested_cache_dict_is_flattened():
    got = usage.normalize(_opencode_step(1200, 340, 8000, 500, 0.0))
    assert got.token_counts() == {
        "input_tokens": 1200,
        "output_tokens": 340,
        "reasoning_output_tokens": 0,
        "cache_read_input_tokens": 8000,
        "cache_creation_input_tokens": 500,
    }, got
    # A real 0.0 IS reported — distinct from codex's silence above.
    assert got.total_cost_usd == 0.0, got


def test_unknown_shape_yields_nothing_rather_than_raising():
    """The copilot shape could not be verified, so the extractor must degrade to a
    missing attribute — never an exception on the hot path of every event."""
    for junk in ({}, {"type": "text", "text": "hello"}, {"usage": "n/a"}, {"a": {"b": {}}}):
        got = usage.normalize(junk)
        assert got.token_counts() == {}, (junk, got)
        assert got.total_cost_usd is None, (junk, got)
        assert got.is_empty, (junk, got)


def test_booleans_are_not_token_counts():
    """isinstance(True, int) is True in Python; a stray flag must not land in the
    store as a count of 1."""
    got = usage.normalize({"usage": {"input_tokens": True, "output_tokens": 5}})
    assert got.token_counts() == {"output_tokens": 5}, got


def test_unnamed_container_is_found_by_recursive_search():
    """No `usage`/`tokens` key at all — the fallback has to find the token-shaped
    dict itself. This is the path an unverified backend (copilot) would take."""
    got = usage.normalize({"type": "done", "meta": {"stats": {
        "prompt_tokens": 90, "completion_tokens": 12}}})
    assert got.token_counts() == {"input_tokens": 90, "output_tokens": 12}, got


def test_search_ignores_dicts_that_are_not_token_shaped():
    """A payload with an `input` that means something else (a tool's argument) must
    not be mistaken for usage."""
    got = usage.normalize({"type": "tool_use", "tool": {"input": "path/to/file.py"}})
    assert got.token_counts() == {}, got


# --------------------------------------------------------------------------- #
# TurnUsage.merge()
# --------------------------------------------------------------------------- #


def test_opencode_steps_sum_into_one_turn():
    """The reason merge exists: opencode reports per step, and only the sum is
    the turn's consumption."""
    total = usage.TurnUsage()
    for step in (
        _opencode_step(1000, 100, 0, 400, 0.01),
        _opencode_step(1500, 200, 900, 0, 0.02),
        _opencode_step(1700, 50, 2400, 0, 0.005),
    ):
        total = total.merge(usage.normalize(step))
    assert total.input_tokens == 4200, total
    assert total.output_tokens == 350, total
    assert total.cache_read_input_tokens == 3300, total
    assert total.cache_creation_input_tokens == 400, total
    assert abs(present(total.total_cost_usd) - 0.035) < 1e-9, total


def test_single_report_backend_merges_unchanged():
    total = usage.TurnUsage().merge(usage.normalize(CODEX_TURN_COMPLETED))
    assert total.input_tokens == 20876, total


def test_duration_is_replaced_not_summed():
    """Duration is a span of time, not a quantity — summing two reports of the same
    turn's elapsed time would double it."""
    total = usage.TurnUsage()
    total = total.merge(usage.normalize({"duration_ms": 500, "usage": {"output_tokens": 1}}))
    total = total.merge(usage.normalize({"duration_ms": 900, "usage": {"output_tokens": 1}}))
    assert total.duration_ms == 900, total
    assert total.output_tokens == 2, total


def test_empty_event_leaves_the_total_alone():
    """Most events in a stream are text/tool deltas. Folding one must not disturb the
    total, nor turn an absent count into a zero that looks like a real report."""
    total = usage.TurnUsage().merge(usage.normalize({"type": "text", "text": "..."}))
    assert total == usage.TurnUsage(), total
    assert total.is_empty, total


# --------------------------------------------------------------------------- #
# from_text()  (aider — no structured events at all)
# --------------------------------------------------------------------------- #


def test_aider_transcript_last_line_wins():
    transcript = (
        "Applied edit to app.py\n"
        "Tokens: 2.1k sent, 180 received. Cost: $0.0031 message, $0.0031 session.\n"
        "Applied edit to test_app.py\n"
        "Tokens: 3.4k sent, 213 received. Cost: $0.0052 message, $0.0083 session.\n"
    )
    got = usage.from_text(transcript)
    assert got.token_counts() == {"input_tokens": 3400, "output_tokens": 213}, got
    assert got.total_cost_usd == 0.0052, got


def test_aider_transcript_without_a_usage_line():
    got = usage.from_text("I could not find that file.\n")
    assert got.token_counts() == {}, got
    assert got.total_cost_usd is None, got
    assert got.is_empty, got


def test_from_text_tolerates_empty_and_none():
    assert usage.from_text("").is_empty
    assert usage.from_text(None).is_empty


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
