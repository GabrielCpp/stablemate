"""Tests for the per-node ``activity:`` field.

Three seams:
- the node models parse an ``activity`` off ``agent``/``script``/``flow``/``call``
  nodes (and the loader passes it through — a field on the model but dropped by the
  loader would be silently lost);
- the graph walk renders it per node and folds it into the labels dict as
  ``wf.activity`` (reusing ``main._render_labels``);
- unlike most labels, ``wf.activity`` and ``wf.work_id`` also ride the LIVE liveness
  metrics (``workhorse.node.active`` and the run heartbeat), so a monitor can show
  what the run is doing while the node span is still open — and only those two keys
  do, to keep metric attribute cardinality bounded.

Run: ./.venv/bin/python tests/test_activity.py   (or via pytest)
"""
from __future__ import annotations

import importlib
import json
import tempfile
from pathlib import Path

from workhorse.graph.loader import load_workflow

main = importlib.import_module("workhorse.main")
test_otel = importlib.import_module("tests.test_otel")


def _load(raw: dict):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "workflow.yaml"
        p.write_text(json.dumps(raw))  # JSON is valid YAML
        return load_workflow(p)


# --------------------------------------------------------------------------- #
# The node field parses (and survives the loader) on every work-doing node type
# --------------------------------------------------------------------------- #
def test_activity_parses_on_agent_script_flow_and_call():
    raw = {
        "name": "acts",
        "start": "ag",
        "flows": {
            "sub": {
                "start": "s2",
                "nodes": [{"id": "s2", "type": "terminal"}],
            }
        },
        "nodes": [
            {"id": "ag", "type": "agent", "prompt": "p.md",
             "activity": "reviewing {{ story_slug }}", "next": "sc"},
            {"id": "sc", "type": "script", "script": "s.py",
             "activity": "selecting next item", "next": "cl"},
            {"id": "cl", "type": "call", "fn": "seed",
             "activity": "seeding", "next": "fl"},
            {"id": "fl", "type": "flow", "name": "sub",
             "activity": "running sub", "next": "done"},
            {"id": "done", "type": "terminal"},
        ],
    }
    g = _load(raw)
    nodes = g.nodes  # keyed by node id (the walk does graph.nodes[current_id])
    assert nodes["ag"].activity == "reviewing {{ story_slug }}"
    assert nodes["sc"].activity == "selecting next item"
    assert nodes["cl"].activity == "seeding"
    assert nodes["fl"].activity == "running sub"


def test_activity_is_optional():
    raw = {
        "name": "acts",
        "start": "sc",
        "nodes": [
            {"id": "sc", "type": "script", "script": "s.py", "next": "done"},
            {"id": "done", "type": "terminal"},
        ],
    }
    assert _load(raw).nodes["sc"].activity is None


# --------------------------------------------------------------------------- #
# Rendering — a per-node activity string lands as wf.activity via the shared helper
# --------------------------------------------------------------------------- #
def test_activity_renders_under_wf_namespace():
    got = main._render_labels(
        {"activity": "reviewing {{ story_slug }}"}, {"story_slug": "PRED-A2JX"}
    )
    assert got == {"wf.activity": "reviewing PRED-A2JX"}, got


def test_unresolved_activity_is_dropped():
    # A pure-expression activity that resolves to nothing is dropped, not stamped
    # blank (early in a run, before a story is selected).
    got = main._render_labels({"activity": "{{ story_slug }}"}, {})
    assert got == {}, got


# --------------------------------------------------------------------------- #
# The live path — wf.activity/wf.work_id ride node.active + the run heartbeat
# --------------------------------------------------------------------------- #
def test_activity_rides_the_node_active_gauge():
    t, _tracer, meter, _sd = test_otel._telemetry()
    t.set_labels({"wf.activity": "reviewing X", "wf.work_id": "ACME-1",
                  "wf.phase": "qa"})
    t.record_event({"node": "impl", "seq": 1, "phase": "enter"})

    gauge = meter.instruments["workhorse.node.active"]
    _kind, value, attrs = gauge.records[-1]
    assert value == 1, gauge.records
    assert attrs["node"] == "impl", attrs
    assert attrs["wf.activity"] == "reviewing X", attrs
    assert attrs["wf.work_id"] == "ACME-1", attrs
    # Only the two dashboard keys ride the gauge; other labels stay off it so
    # metric attribute cardinality stays bounded.
    assert "wf.phase" not in attrs, attrs


def test_activity_rides_the_run_heartbeat():
    t, _tracer, meter, _sd = test_otel._telemetry()
    t.set_labels({"wf.activity": "seeding", "wf.work_id": "ACME-2"})
    t.record_event({"node": "seed", "seq": 1, "phase": "enter"})
    t._beat_once()

    beats = meter.instruments["workhorse.run.heartbeat"]
    _kind, _value, attrs = beats.records[-1]
    assert attrs["node"] == "seed", attrs
    assert attrs["wf.activity"] == "seeding", attrs
    assert attrs["wf.work_id"] == "ACME-2", attrs


def test_live_attrs_omit_absent_labels():
    t, _tracer, meter, _sd = test_otel._telemetry()
    # No labels set at all — the gauge carries just the node, never a blank attr.
    t.record_event({"node": "plan", "seq": 1, "phase": "enter"})
    gauge = meter.instruments["workhorse.node.active"]
    _kind, _value, attrs = gauge.records[-1]
    assert attrs == {"node": "plan"}, attrs


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
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
