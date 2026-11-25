"""Counting a turn's LLM steps, because the turn's bill is quadratic in them."""

from __future__ import annotations

from workhorse.runner.backends import opencode
from workhorse.runner.backends.turn import TurnState


def _replay(*events) -> TurnState:
    """Feed ``events`` to one turn's event reader and return what it accumulated."""
    state = TurnState()
    on_event = opencode._OpenCodeEvents().on_event
    for event in events:
        on_event(event, state, "n")
    return state


def test_every_step_is_counted():
    """opencode resends the whole conversation on each step, so the step count is what the cost model is fitted against."""
    state = _replay(
        {"type": "step_finish", "tokens": {"input": 20000, "output": 300}},
        {"type": "step_finish", "tokens": {"input": 22000, "output": 300}},
        {"type": "step_finish", "tokens": {"input": 24000, "output": 300}},
    )
    assert state.usage.steps == 3


def test_the_first_step_still_carries_its_tokens():
    """A step event that reports usage must not lose it to the step counter."""
    state = _replay({"type": "step_finish", "tokens": {"input": 20000, "output": 300}})
    assert state.usage.steps == 1
    assert state.usage.input_tokens == 20000


def test_a_turn_that_reported_no_step_leaves_the_count_unset():
    """An unset count says the harness never reported one; a zero would claim the turn took none."""
    state = _replay({"type": "text", "part": {"id": "p1", "text": "done"}})
    assert state.usage.steps is None


def test_a_step_alone_is_not_an_empty_turn():
    """A step that carried no token counts still has to survive the merge that drops empty parts."""
    state = _replay({"type": "step_finish"})
    assert state.usage.steps == 1
    assert not state.usage.is_empty


def _step(tokens: dict, cost: float = 0) -> dict:
    return {
        "type": "step_finish",
        "sessionID": "ses_x",
        "part": {"type": "step-finish", "tokens": tokens, "cost": cost},
    }


def test_a_step_reports_uncached_input_beside_its_cache_reads():
    """opencode's input excludes cache reads, since its total is input + output + reasoning + cache."""
    tokens = {
        "total": 21996,
        "input": 5955,
        "output": 135,
        "reasoning": 34,
        "cache": {"write": 0, "read": 15872},
    }
    assert 5955 + 135 + 34 + 15872 == 21996
    state = _replay(_step(tokens))
    assert state.usage.input_tokens == 5955
    assert state.usage.cache_read_input_tokens == 15872
    assert state.usage.output_tokens == 135
    assert state.usage.reasoning_output_tokens == 34


def test_steps_of_one_turn_are_summed_because_each_reports_its_own_counts():
    """Consecutive steps of a session do not grow steadily, so each is that step's usage and the turn is their sum."""
    state = _replay(
        _step(
            {
                "total": 22156,
                "input": 1141,
                "output": 23,
                "reasoning": 0,
                "cache": {"write": 0, "read": 20992},
            },
            0.01,
        ),
        _step(
            {
                "total": 27059,
                "input": 4863,
                "output": 180,
                "reasoning": 0,
                "cache": {"write": 0, "read": 22016},
            },
            0.02,
        ),
    )
    assert state.usage.input_tokens == 1141 + 4863
    assert state.usage.cache_read_input_tokens == 20992 + 22016
    assert state.usage.output_tokens == 23 + 180
    assert state.usage.total_cost_usd == 0.03
    assert state.usage.steps == 2


if __name__ == "__main__":
    fns = [
        v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
    ]
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
