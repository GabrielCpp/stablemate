"""Tests for workflow-declared telemetry labels (`labels:` in workflow.yaml).

Three seams:
- the Graph field parses and defaults to empty (no workflow is required to opt in);
- `main._render_labels` renders each value against the live context, drops the
  empties, and namespaces the keys under `wf.`;
- `otel.set_labels` stamps them on the spans opened afterwards — node spans and
  agent-turn spans alike — and a flow inherits its parent's rendered values.

Run: ./.venv/bin/python tests/test_labels.py   (or via pytest)
"""
from __future__ import annotations

import importlib

import json
import tempfile
from pathlib import Path

from workhorse.graph.loader import load_workflow

main = importlib.import_module("workhorse.main")
otel = importlib.import_module("workhorse.otel")
test_otel = importlib.import_module("tests.test_otel")


_WORKFLOW = {
    "name": "labelled",
    "start": "a",
    "labels": {"work_id": "{{ story.id }}", "phase": "{{ phase }}"},
    "nodes": [
        {"id": "a", "type": "script", "script": "s.py", "next": "done"},
        {"id": "done", "type": "terminal"},
    ],
}


def _load(raw: dict):
    """Go through the real YAML→Graph path. `_shape_graph` enumerates the keys it
    passes through, so a field added to the model but not to the loader is silently
    dropped — which is exactly what this asserts against."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "workflow.yaml"
        p.write_text(json.dumps(raw))  # JSON is valid YAML
        return load_workflow(p)


# --------------------------------------------------------------------------- #
# The Graph field
# --------------------------------------------------------------------------- #
def test_labels_parse_off_the_workflow():
    graph = _load(_WORKFLOW)
    assert graph.labels == {"work_id": "{{ story.id }}", "phase": "{{ phase }}"}


def test_labels_are_optional():
    stripped = {k: v for k, v in _WORKFLOW.items() if k != "labels"}
    assert _load(stripped).labels == {}


def test_a_flow_may_declare_its_own_labels():
    raw = {
        **{k: v for k, v in _WORKFLOW.items() if k != "labels"},
        "flows": {"qa": {"start": "q", "labels": {"stage": "qa"},
                         "nodes": [{"id": "q", "type": "terminal"}]}},
    }
    assert _load(raw).flows["qa"].labels == {"stage": "qa"}


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def test_render_namespaces_keys_under_wf():
    """A workflow picks the name but not the namespace, so no label can ever shadow
    `workhorse.*`, `model`, or an OTel semantic-convention attribute."""
    got = main._render_labels({"work_id": "{{ story.id }}"}, {"story": {"id": "ACME-1"}})
    assert got == {"wf.work_id": "ACME-1"}, got


def test_unresolved_expression_is_dropped_not_blanked():
    """Early in a run no story is selected yet. Jinja here renders a missing var as
    empty, and a blank attribute on every span would read as data."""
    got = main._render_labels({"work_id": "{{ story.id }}", "phase": "plan"}, {})
    assert got == {"wf.phase": "plan"}, got


def test_whitespace_only_render_is_dropped():
    got = main._render_labels({"work_id": "  {{ nothing }}  "}, {})
    assert got == {}, got


def test_a_bad_expression_costs_one_label_not_the_run():
    """Instrumentation must never be able to end an unattended run."""
    got = main._render_labels(
        {"broken": "{{ 1/0 }}", "fine": "{{ ok }}"}, {"ok": "yes"}
    )
    assert got == {"wf.fine": "yes"}, got


def test_unresolved_labels_do_not_warn():
    """Labels re-render before EVERY node, and being unresolved is a designed state
    (see above), so the usual missing-variable warning would print thousands of lines
    about correct behavior over a week-long run."""
    import io
    import logging

    logger = logging.getLogger("workhorse.templates")
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    logger.addHandler(handler)
    try:
        main._render_labels({"work_id": "{{ story.id }}"}, {})
    finally:
        logger.removeHandler(handler)
    assert buf.getvalue() == "", buf.getvalue()


def test_non_string_context_values_stringify():
    got = main._render_labels({"n": "{{ count }}"}, {"count": 42})
    assert got == {"wf.n": "42"}, got


# --------------------------------------------------------------------------- #
# Stamping on spans
# --------------------------------------------------------------------------- #
def test_labels_land_on_node_and_turn_spans():
    t, tracer, _meter, _sd = test_otel._telemetry()
    t.set_labels({"wf.work_id": "ACME-1"})
    t.record_event({"node": "impl", "seq": 1, "phase": "enter"})
    t.turn_start("impl", "sonnet", "high", 600.0, backend="claude")

    node_span = tracer.by_name("impl")
    assert node_span.attrs.get("wf.work_id") == "ACME-1", node_span.attrs
    turn_span = tracer.by_name("agent_turn")
    assert turn_span.attrs.get("wf.work_id") == "ACME-1", turn_span.attrs


def test_labels_track_the_run_rather_than_being_fixed_at_start():
    """The whole point: a week-long run moves through stories, and each node span
    must carry the one that was current when it opened."""
    t, tracer, _meter, _sd = test_otel._telemetry()
    t.set_labels({"wf.work_id": "ACME-1"})
    t.record_event({"node": "impl", "seq": 1, "phase": "enter"})
    t.set_labels({"wf.work_id": "ACME-2"})
    t.record_event({"node": "impl", "seq": 2, "phase": "enter"})

    first, second = [s for s in tracer.spans if s.name == "impl"]
    assert first.attrs["wf.work_id"] == "ACME-1", first.attrs
    assert second.attrs["wf.work_id"] == "ACME-2", second.attrs


def test_setting_labels_never_raises_when_telemetry_is_off():
    assert otel._active is None
    otel.set_labels({"wf.work_id": "ACME-1"})


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
