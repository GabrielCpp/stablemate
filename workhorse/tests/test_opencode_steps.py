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
