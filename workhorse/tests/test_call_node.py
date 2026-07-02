"""Tests for the `type: call` node — inline built-in function invocation.

Run: ./.venv/bin/python tests/test_call_node.py   (or via pytest)
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from workhorse.builtins import REGISTRY, incr, seed
from workhorse.graph.context import WorkflowContext
from workhorse.graph.nodes import CallNode, CallOutputSpec
from workhorse.runner import call as c

m = importlib.import_module("workhorse.main")


# ── builtins unit tests ──────────────────────────────────────────────────────

def test_incr_int():
    assert incr(4) == 5

def test_incr_string():
    assert incr("4") == 5

def test_incr_float_string():
    assert incr("4.0") == 5

def test_incr_missing_defaults_to_zero():
    assert incr() == 1

def test_incr_empty_string_defaults_to_zero():
    assert incr("") == 1

def test_seed_returns_zero():
    assert seed() == 0
    assert seed(value="anything") == 0

def test_registry_contains_expected_keys():
    assert "incr" in REGISTRY
    assert "seed" in REGISTRY


# ── runner unit tests ────────────────────────────────────────────────────────

def _call_node(**kw) -> CallNode:
    return CallNode(type="call", id="n", **kw)


def test_incr_with_wrap():
    node = _call_node(
        fn="incr",
        args={"value": "4"},
        outputs=[CallOutputSpec(key="qa_rework_count", wrap="value")],
        next="done",
    )
    ctx = WorkflowContext({})
    label, outputs = c.run_call(node, ctx, Path("."))
    assert outputs == {"qa_rework_count": {"value": 5}}
    assert "incr" in label


def test_incr_bare_scalar():
    node = _call_node(
        fn="incr",
        args={"value": "3"},
        outputs=[CallOutputSpec(key="triage_scope_count")],
        next="done",
    )
    label, outputs = c.run_call(node, WorkflowContext({}), Path("."))
    assert outputs == {"triage_scope_count": 4}


def test_incr_missing_arg_defaults_to_zero():
    node = _call_node(
        fn="incr",
        outputs=[CallOutputSpec(key="k")],
        next="done",
    )
    _, outputs = c.run_call(node, WorkflowContext({}), Path("."))
    assert outputs == {"k": 1}


def test_seed_multi_output_wrap():
    node = _call_node(
        fn="seed",
        outputs=[
            CallOutputSpec(key="ci_rework_count", wrap="value"),
            CallOutputSpec(key="merge_rework_count", wrap="value"),
        ],
        next="done",
    )
    _, outputs = c.run_call(node, WorkflowContext({}), Path("."))
    assert outputs == {
        "ci_rework_count": {"value": 0},
        "merge_rework_count": {"value": 0},
    }


def test_seed_bare_scalar():
    node = _call_node(
        fn="seed",
        outputs=[CallOutputSpec(key="triage_scope_count")],
        next="done",
    )
    _, outputs = c.run_call(node, WorkflowContext({}), Path("."))
    assert outputs == {"triage_scope_count": 0}


def test_unknown_fn_raises():
    node = _call_node(fn="nonexistent", outputs=[CallOutputSpec(key="k")], next="done")
    with pytest.raises(RuntimeError, match="unknown built-in"):
        c.run_call(node, WorkflowContext({}), Path("."))


def test_jinja_args_rendered():
    node = _call_node(
        fn="incr",
        args={"value": "{{ counter.value }}"},
        outputs=[CallOutputSpec(key="counter", wrap="value")],
        next="done",
    )
    ctx = WorkflowContext({"counter": {"value": 7}})
    _, outputs = c.run_call(node, ctx, Path("."))
    assert outputs == {"counter": {"value": 8}}


# ── end-to-end test ──────────────────────────────────────────────────────────

_WORKFLOW = """\
name: test-call
start: incr_counter
vars:
  count: 0
nodes:
  - id: incr_counter
    type: call
    fn: incr
    args:
      value: "{{ count }}"
    outputs:
      - key: count
        wrap: value
    next: done
  - id: done
    type: terminal
"""


def _ctx_after(runs_dir: Path, run_name: str, node_id: str) -> dict:
    return json.loads((runs_dir / run_name / node_id / "context_after.json").read_text())


def test_call_node_end_to_end(tmp_path):
    wf_dir = tmp_path / "wf"
    wf_dir.mkdir()
    (wf_dir / "workflow.yaml").write_text(_WORKFLOW)
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    rc = m.run(wf_dir / "workflow.yaml", runs_dir, run_id="run1")
    assert rc == 0

    # Run dir is named "<graph-name>-<run-id>" by the artifact writer.
    run_dir = next(runs_dir.iterdir())
    ctx = json.loads((run_dir / "incr_counter" / "context_after.json").read_text())
    assert ctx["count"] == {"value": 1}


# ── DOT renderer test ────────────────────────────────────────────────────────

def test_dot_includes_call_node():
    from workhorse.graph.dot import to_dot
    from workhorse.graph.nodes import Graph

    nodes = {
        "reset": {"id": "reset", "type": "call", "fn": "seed", "outputs": [{"key": "c", "wrap": "value"}], "next": "done"},
        "done": {"id": "done", "type": "terminal"},
    }
    g = Graph.model_validate({"name": "t", "start": "reset", "vars": {}, "nodes": nodes})
    out = to_dot(g)
    assert "reset" in out
    assert "done" in out


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
