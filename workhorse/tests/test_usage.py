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


# Captured from a real `cline --json` turn (CLI 3.0.50 via OpenRouter, 2026-08-05).
# The best-instrumented harness of the set — and the one that proved a price table
# can masquerade as a token count. `model.info.pricing` uses `input`/`output`, the
# very keys opencode spells its *counts* with.
CLINE_RUN_RESULT = {
    "type": "run_result",
    "finishReason": "completed",
    "iterations": 1,
    "usage": {
        "inputTokens": 6337,
        "outputTokens": 33,
        "cacheReadTokens": 0,
        "cacheWriteTokens": 0,
        "totalCost": 0.00089642,
    },
    "aggregateUsage": {"inputTokens": 6337, "outputTokens": 33, "totalCost": 0.00089642},
    "durationMs": 4542,
    "text": "OK",
    "model": {
        "id": "xiaomi/mimo-v2.5",
        "provider": "openrouter",
        "info": {
            "contextWindow": 1050000,
            "maxInputTokens": 1050000,
            "maxTokens": 131072,
            # Dollars per million tokens — NOT counts.
            "pricing": {"input": 0.14, "output": 0.28, "cacheRead": 0.0028, "cacheWrite": 0},
        },
    },
}


def test_cline_reports_tokens_cost_and_duration():
    """Verified against a live turn, not inferred."""
    got = usage.normalize(CLINE_RUN_RESULT)
    assert got.token_counts() == {
        "input_tokens": 6337,
        "output_tokens": 33,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }, got
    assert got.total_cost_usd == 0.00089642, got
    assert got.duration_ms == 4542, got


def test_a_price_table_is_not_a_token_count():
    """The regression that made `_as_int` reject fractional floats.

    cline's completion event carries `model.info.pricing` — dollars per million
    tokens — under `input`/`output`, which are exactly opencode's spelling for its
    counts. With cline's own camelCase keys unrecognized, the tolerant search walked
    past the real `usage` dict and landed on the price table, where `int(0.14)`
    truncated to 0. A turn that used 6337 input tokens recorded 0: not a missing
    attribute but a fabricated one, which is the failure this module is built to
    make impossible.

    Two things now stop it, and the test pins both: the real keys are recognized so
    the search never gets that far, and a fractional float is refused outright, so
    the price table cannot be mistaken for counts even if it is reached.
    """
    pricing_only = {"usage": {"input": 0.14, "output": 0.28, "cacheRead": 0.0028}}
    assert usage.normalize(pricing_only).token_counts() == {}

    # A whole-valued float is still a count: JSON has one number type, so 33.0
    # means thirty-three.
    assert usage.normalize({"usage": {"input": 12.0, "output": 33.0}}).token_counts() == {
        "input_tokens": 12,
        "output_tokens": 33,
    }


def test_opencode_prices_a_turn_or_not_depending_on_the_provider_behind_it():
    """Both captured from live `opencode run --format json` turns, 2026-08-05.

    The same harness, the same event shape, the same trivial prompt — and two
    different cost semantics, because cost belongs to the *provider*, not the CLI in
    front of it. Through OpenRouter the turn prices itself; through a subscription
    OAuth provider it reports a literal `0`.

    That zero is the one that hurts. A NULL is excluded from a SUM and shows up as a
    gap; a zero is summed, so a run that spent real wall-clock totals nothing and looks
    complete. Nothing here corrects it — a genuinely free model reports identically —
    but `groom.store.node_costs` counts these separately so a total can say how much of
    itself is real.
    """
    via_openrouter = usage.normalize({
        "type": "step_finish",
        "part": {
            "type": "step-finish",
            "tokens": {"total": 12766, "input": 11715, "output": 4,
                       "reasoning": 23, "cache": {"write": 0, "read": 1024}},
            "cost": 0.0016505272,
        },
    })
    via_subscription = usage.normalize({
        "type": "step_finish",
        "part": {
            "type": "step-finish",
            "tokens": {"total": 8156, "input": 6615, "output": 5,
                       "reasoning": 0, "cache": {"write": 0, "read": 1536}},
            "cost": 0,
        },
    })

    assert via_openrouter.total_cost_usd == 0.0016505272, via_openrouter
    # Zero, not None: the harness said "0", and inventing a None here would be as much
    # a fabrication as inventing a 0.0 where nothing was said.
    assert via_subscription.total_cost_usd == 0.0, via_subscription
    assert via_subscription.total_cost_usd is not None

    # Both price differently and both count tokens identically — and `total`, which
    # sits right beside the mapped keys, is not mistaken for one of them.
    assert via_openrouter.input_tokens == 11715 and via_openrouter.output_tokens == 4
    assert via_subscription.input_tokens == 6615 and via_subscription.output_tokens == 5


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
