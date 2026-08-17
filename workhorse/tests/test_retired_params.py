"""A field deleted from a workflow must not brick the runs already holding it.

`Workflow` is `extra="forbid"`, and the same `_instantiate` builds the class from
`--params` on a fresh run and from the checkpoint's `inputs` on a resume or a live
reload. That symmetry is what made a *deletion* unrecoverable: the run died the moment
it reloaded, and then died identically on every `--resume-run` after it, because the
stored key nothing reads was still being validated. The fix splits the two sources —
a checkpoint may carry keys the class has since dropped, `--params` may not.

What is asserted here is that split, and its limit: only *unknown* keys are forgiven.
A field that was renamed or retyped still stops the run, because there the stored value
is meaningful and only a human can map it onto the new contract.

Run: uv run python tests/test_retired_params.py   (or via pytest)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workhorse.pyflow.run import _drop_retired_inputs, _instantiate  # noqa: E402
from workhorse.pyflow.workflow import Workflow  # noqa: E402
from workhorse.pyflow.transitions import Done, Transition  # noqa: E402
from workhorse.pyflow.errors import WorkflowFailed  # noqa: E402


class Coder(Workflow):
    """A workflow that used to declare `qa_sandbox` and no longer does."""

    epic: str = ""
    qa_lane_budget_s: int = 3300

    def start(self) -> Transition:
        return Done()


def test_retired_key_is_dropped_and_named():
    stored = {"epic": "acme-hardening", "qa_sandbox": False, "qa_lane_budget_s": 60}
    inputs, retired = _drop_retired_inputs(Coder, stored)
    assert retired == ("qa_sandbox",), retired
    assert inputs == {"epic": "acme-hardening", "qa_lane_budget_s": 60}, inputs
    # The surviving inputs must still build the workflow — the point of dropping.
    built = _instantiate(Coder, inputs).model_dump()
    assert built["epic"] == "acme-hardening"
    assert built["qa_lane_budget_s"] == 60


def test_several_retired_keys_are_reported_sorted():
    stored = {"epic": "x", "qa_sandbox": False, "fidelity_source": "docs", "id_prefix": "ACME"}
    inputs, retired = _drop_retired_inputs(Coder, stored)
    assert retired == ("fidelity_source", "id_prefix", "qa_sandbox"), retired
    assert inputs == {"epic": "x"}, inputs


def test_a_clean_checkpoint_is_left_alone():
    stored = {"epic": "x", "qa_lane_budget_s": 10}
    inputs, retired = _drop_retired_inputs(Coder, stored)
    assert retired == ()
    assert inputs is stored, "no copy when there is nothing to drop"


def test_the_workflows_own_fields_are_never_dropped():
    """`repo_dir` is declared on the base class, not on `Coder` — still a real field."""
    stored = {"repo_dir": "/w/acme", "epic": "x"}
    inputs, retired = _drop_retired_inputs(Coder, stored)
    assert retired == (), retired
    assert _instantiate(Coder, inputs).model_dump()["repo_dir"] == "/w/acme"


def test_a_retyped_field_still_stops_the_run():
    """Forgiveness covers unknown keys only: a stored value the class still wants, in a
    shape it no longer accepts, is a judgement call that belongs to an operator."""
    inputs, retired = _drop_retired_inputs(Coder, {"epic": "x", "qa_lane_budget_s": "soon"})
    assert retired == (), "a declared field is not retired, whatever its stored value"
    try:
        _instantiate(Coder, inputs)
    except WorkflowFailed as exc:
        assert "qa_lane_budget_s" in str(exc), exc
    else:
        raise AssertionError("a retyped field must not be forgiven")


def test_fresh_params_stay_strict():
    """The typo an operator just made is still caught by name — that is the contract
    `extra="forbid"` is there for, and the resume path is the only one relaxed."""
    try:
        _instantiate(Coder, {"epic": "x", "qa_sandbx": True})
    except WorkflowFailed as exc:
        assert "qa_sandbx" in str(exc), exc
    else:
        raise AssertionError("an unknown --param must not be silently dropped")


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
