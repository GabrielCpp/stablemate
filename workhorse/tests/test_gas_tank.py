"""Tests for the _GasTank progress-metered loop guard and the engine wall-clock
budget (WORKHORSE_MAX_RUNTIME_S → RunBudgetExceeded).

The tank burns one unit per node step and refuels to FULL when a refuel node's
tracked value changes (forward progress); a cycle that reprocesses the same
unit forever burns exactly one tank and halts loudly. The wall-clock budget is
the complementary backstop: it bounds a run that *does* progress, counted from
the run's original start so it survives --resume.

Run: ./.venv/bin/python tests/test_gas_tank.py   (or via pytest)
"""
from __future__ import annotations

import importlib
import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

m = importlib.import_module("workhorse.main")


# --------------------------------------------------------------------------- #
# _GasTank
# --------------------------------------------------------------------------- #
def test_burn_raises_after_capacity_without_progress():
    tank = m._GasTank(capacity=3)
    for _ in range(3):
        tank.burn("loop_node")
    with pytest.raises(m.OutOfGasError):
        tank.burn("loop_node")


def test_refuel_on_changed_value_refills_to_full():
    tank = m._GasTank(capacity=3)
    tank.burn("work")
    tank.burn("work")
    assert tank.gas == 1
    tank.refuel("select_story", "story-A")  # first visit counts as progress
    assert tank.gas == 3
    tank.burn("work")
    tank.refuel("select_story", "story-B")  # value changed -> progress -> refill
    assert tank.gas == 3


def test_refuel_same_value_does_not_refill():
    """Reprocessing the SAME story leaves the tracked value unchanged, so the
    tank keeps draining and the loop eventually halts."""
    tank = m._GasTank(capacity=2)
    tank.refuel("select_story", "story-A")
    tank.burn("work")
    tank.refuel("select_story", "story-A")  # unchanged -> no refill
    assert tank.gas == 1
    tank.burn("work")
    with pytest.raises(m.OutOfGasError):
        tank.burn("work")


def test_first_visit_with_none_value_counts_as_progress():
    """The _UNSEEN sentinel is distinct from any real value, including None, so
    a refuel node whose tracked path is missing still refuels on first visit."""
    tank = m._GasTank(capacity=2)
    tank.burn("work")
    tank.refuel("select_story", None)
    assert tank.gas == 2
    # ...but a SECOND None is "no change" and must not refill.
    tank.burn("work")
    tank.refuel("select_story", None)
    assert tank.gas == 1


def test_zero_capacity_disables_the_guard():
    tank = m._GasTank(capacity=0)
    for _ in range(50):
        tank.burn("loop_node")  # never raises


def test_out_of_gas_message_names_hottest_nodes():
    tank = m._GasTank(capacity=4)
    for node in ("hot", "hot", "hot", "cold"):
        tank.burn(node)
    with pytest.raises(m.OutOfGasError) as excinfo:
        tank.burn("hot")
    assert "hot×4" in str(excinfo.value)
    assert "WORKHORSE_GAS" in str(excinfo.value)


def test_configured_gas_env_override_and_bad_value():
    with patch.dict("os.environ", {"WORKHORSE_GAS": "42"}):
        assert m._configured_gas() == 42
    with patch.dict("os.environ", {"WORKHORSE_GAS": "not-a-number"}):
        assert m._configured_gas() == m._DEFAULT_GAS


# --------------------------------------------------------------------------- #
# Engine wall-clock budget (WORKHORSE_MAX_RUNTIME_S)
# --------------------------------------------------------------------------- #
def _iso_now(offset_s: float = 0.0) -> str:
    return datetime.fromtimestamp(
        time.time() + offset_s, tz=timezone.utc
    ).isoformat()


def test_runtime_deadline_unset_means_unbounded():
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("WORKHORSE_MAX_RUNTIME_S", None)
        assert m._runtime_deadline(_iso_now()) is None


def test_runtime_deadline_counts_from_original_start():
    """A resumed run keeps the ORIGINAL start time, so the deadline is start +
    budget — not resume-time + budget."""
    with patch.dict("os.environ", {"WORKHORSE_MAX_RUNTIME_S": "100"}):
        started = _iso_now(-40)  # run began 40s ago
        deadline = m._runtime_deadline(started)
        assert deadline is not None
        assert abs(deadline - (time.time() + 60)) < 5


def test_step_loop_raises_run_budget_exceeded_past_deadline():
    """A deadline already in the past trips at the loop-top, BEFORE any node
    work (gas burn / checkpoint) happens."""
    graph = m.Graph.model_construct(
        name="wf", start="a", nodes={"a": object()}, flows={}, vars={}, env=None
    )

    class _NoWriter:
        def write_checkpoint(self, *a, **k):
            raise AssertionError("must trip before checkpointing")

    with pytest.raises(m.RunBudgetExceeded):
        m._step_loop(
            graph,
            _NoWriter(),
            None,
            "a",
            False,
            manifest={},
            workflow_dir=None,
            session_id_path=None,
            tank=m._GasTank(capacity=0),
            deadline=time.time() - 10,
        )


def test_step_loop_no_deadline_reaches_terminal():
    terminal = m.TerminalNode.model_construct(id="done", type="terminal")
    graph = m.Graph.model_construct(
        name="wf", start="done", nodes={"done": terminal}, flows={}, vars={}, env=None
    )
    got = m._step_loop(
        graph,
        None,
        None,
        "done",
        False,
        manifest={},
        workflow_dir=None,
        session_id_path=None,
        tank=m._GasTank(capacity=5),
        deadline=None,
    )
    assert got == "terminal"


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
