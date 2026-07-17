"""Tests for workhorse/otel.py — the opt-in OpenTelemetry facade.

Two halves:
- the NO-OP default (WORKHORSE_OTEL unset): every public function must be an
  inert, exception-free call and ArtifactWriter._append_event must behave
  exactly as before (instrumentation may never change a run);
- the _Telemetry span logic, exercised with fake tracer/meter objects so the
  tests need no OTel SDK: (node, seq)-keyed enter/done pairing, flow nesting
  via the span stack, the end_run sweep of spans a crash left open, turn
  attrs/events, and the gas/heartbeat metrics.

Run: ./.venv/bin/python tests/test_otel.py   (or via pytest)
"""
from __future__ import annotations

import importlib
import json
import tempfile
from pathlib import Path

otel = importlib.import_module("workhorse.otel")
artifacts = importlib.import_module("workhorse.artifacts")


# --------------------------------------------------------------------------- #
# Fakes standing in for the OTel API/SDK
# --------------------------------------------------------------------------- #
class FakeSpan:
    def __init__(self, name: str, context, attributes) -> None:
        self.name = name
        self.parent = context  # whatever set_span_in_context wrapped, or None
        self.attrs = dict(attributes or {})
        self.events: list[tuple[str, dict]] = []
        self.status = None
        self.ended = False

    def set_attribute(self, key, value):
        self.attrs[key] = value

    def add_event(self, name, attributes=None):
        self.events.append((name, dict(attributes or {})))

    def set_status(self, status):
        self.status = status

    def end(self):
        self.ended = True


class FakeTracer:
    def __init__(self) -> None:
        self.spans: list[FakeSpan] = []

    def start_span(self, name, context=None, attributes=None):
        span = FakeSpan(name, context, attributes)
        self.spans.append(span)
        return span

    def by_name(self, name: str) -> FakeSpan:
        return next(s for s in self.spans if s.name == name)


class FakeStatus:
    def __init__(self, code, description=None) -> None:
        self.code = code
        self.description = description


class FakeStatusCode:
    ERROR = "ERROR"


class FakeTraceApi:
    Status = FakeStatus
    StatusCode = FakeStatusCode

    @staticmethod
    def set_span_in_context(span):
        return span  # the "context" IS the parent span, easy to assert on


class FakeInstrument:
    def __init__(self) -> None:
        self.records: list[tuple] = []

    def set(self, value, attributes=None):
        self.records.append(("set", value, attributes))

    def add(self, value, attributes=None):
        self.records.append(("add", value, attributes))


class FakeMeter:
    def __init__(self) -> None:
        self.instruments: dict[str, FakeInstrument] = {}

    def create_gauge(self, name, **_):
        return self.instruments.setdefault(name, FakeInstrument())

    def create_counter(self, name, **_):
        return self.instruments.setdefault(name, FakeInstrument())


def _telemetry() -> tuple:
    tracer, meter = FakeTracer(), FakeMeter()
    shutdown = {"called": False}
    t = otel._Telemetry(
        FakeTraceApi, tracer, meter, lambda: shutdown.__setitem__("called", True)
    )
    t.start_root("wf")
    return t, tracer, meter, shutdown


# --------------------------------------------------------------------------- #
# The no-op default
# --------------------------------------------------------------------------- #
def test_noop_by_default_all_calls_inert():
    assert otel._active is None
    assert otel.enabled() is False
    # Every public function must be safely callable with nothing configured.
    otel.record_event({"node": "a", "seq": 1, "phase": "enter"})
    otel.gas_level(10, 100)
    otel.gas_refuel("select_story")
    otel.turn_start("a", "sonnet", "high", 600.0)
    otel.turn_result({"duration_ms": 5, "usage": {"input_tokens": 1}})
    otel.turn_event("retry", attempt=1)
    otel.heartbeat("a", 120.0)
    otel.turn_heartbeat("a", 3.0, 90.0)
    otel.turn_end()
    otel.end_run("terminal")
    assert otel._active is None


def test_start_run_stays_noop_without_env():
    # _OTEL_ENABLED was read at import with WORKHORSE_OTEL unset in the test
    # environment, so start_run must not activate anything.
    assert otel._OTEL_ENABLED is False
    otel.start_run("wf", "run-1")
    assert otel._active is None


def test_append_event_unchanged_with_noop_telemetry():
    with tempfile.TemporaryDirectory() as tmp:
        writer = artifacts.ArtifactWriter("wf", Path(tmp), run_id="r1")
        writer.write_checkpoint("node_a", {"k": "v"})
        writer.write_step("node_a", "prompt", {"out": 1}, {"k": "v"}, next_node="node_b")
        events = writer.read_events()
        assert [(e["node"], e["phase"]) for e in events] == [
            ("node_a", "enter"),
            ("node_a", "done"),
        ]
        assert events[1]["next"] == "node_b"


# --------------------------------------------------------------------------- #
# _Telemetry span pairing (with fakes; no SDK required)
# --------------------------------------------------------------------------- #
def test_enter_done_pairs_a_node_span_and_records_next():
    t, tracer, _, _ = _telemetry()
    t.record_event({"node": "plan", "seq": 1, "phase": "enter"})
    span = tracer.by_name("plan")
    assert span.parent is tracer.by_name("run:wf")
    assert span.attrs["workhorse.seq"] == 1 and not span.ended
    t.record_event({"node": "plan", "seq": 1, "phase": "done", "next": "build"})
    assert span.ended and span.attrs["workhorse.next"] == "build"


def test_flow_children_nest_under_the_open_flow_node_span():
    t, tracer, _, _ = _telemetry()
    t.record_event({"node": "qa_flow", "seq": 3, "phase": "enter"})
    t.record_event({"node": "child", "seq": 1, "phase": "enter"})
    child = tracer.by_name("child")
    assert child.parent is tracer.by_name("qa_flow")
    assert child.attrs["workhorse.depth"] == 1
    # The child's terminal lands on the enclosing flow-node span, not the root.
    t.record_event({"node": "child", "seq": 1, "phase": "done", "next": None})
    t.record_event({"node": "<run>", "seq": 1, "phase": "terminal", "terminal": "terminal"})
    assert ("terminal", {"terminal": "terminal"}) in tracer.by_name("qa_flow").events
    t.record_event({"node": "qa_flow", "seq": 3, "phase": "done", "next": "wrap"})
    assert tracer.by_name("qa_flow").ended


def test_loop_revisits_pair_by_seq():
    """The same node visited twice (a loop) gets two distinct spans, each done
    event closing its own visit's span via the (node, seq) key."""
    t, tracer, _, _ = _telemetry()
    t.record_event({"node": "work", "seq": 1, "phase": "enter"})
    t.record_event({"node": "work", "seq": 1, "phase": "done", "next": "work"})
    t.record_event({"node": "work", "seq": 2, "phase": "enter"})
    spans = [s for s in tracer.spans if s.name == "work"]
    assert len(spans) == 2
    assert spans[0].ended and not spans[1].ended


def test_end_run_sweeps_open_spans_and_flags_error():
    t, tracer, _, shutdown = _telemetry()
    t.record_event({"node": "stuck", "seq": 1, "phase": "enter"})
    t.end_run("fail", "out of gas")
    stuck, root = tracer.by_name("stuck"), tracer.by_name("run:wf")
    assert stuck.ended and stuck.status.code == "ERROR"
    assert root.ended and root.attrs["workhorse.terminal"] == "fail"
    assert root.status.code == "ERROR"
    assert shutdown["called"] is True


def test_done_without_matching_enter_is_ignored():
    t, tracer, _, _ = _telemetry()
    t.record_event({"node": "ghost", "seq": 9, "phase": "done", "next": "x"})
    assert [s.name for s in tracer.spans] == ["run:wf"]


def test_turn_span_attrs_result_usage_and_fallback_events():
    t, tracer, _, _ = _telemetry()
    t.record_event({"node": "impl", "seq": 1, "phase": "enter"})
    t.turn_start("impl", "opus", "high", 3600.0)
    turn = tracer.by_name("agent_turn")
    assert turn.parent is tracer.by_name("impl")
    assert turn.attrs["model"] == "opus" and turn.attrs["timeout_s"] == 3600
    t.turn_result(
        {"duration_ms": 1234, "usage": {"input_tokens": 10, "output_tokens": 20}}
    )
    assert turn.attrs["duration_ms"] == 1234
    assert turn.attrs["usage.input_tokens"] == 10
    t.turn_event("watchdog_kill", True, {"node": "impl"})
    assert turn.events[0][0] == "watchdog_kill" and turn.status.code == "ERROR"
    t.turn_end("killed")
    assert turn.ended
    # With no turn open, ladder events fall back to the open node span.
    t.turn_event("cap_wait", False, {"delay_s": 60})
    assert ("cap_wait", {"delay_s": "60"}) in tracer.by_name("impl").events


def test_turn_session_tags_open_turn_span():
    t, tracer, _, _ = _telemetry()
    t.record_event({"node": "impl", "seq": 1, "phase": "enter"})
    t.turn_start("impl", "opus", "high", 3600.0)
    t.turn_session("ses_abc123")
    assert tracer.by_name("agent_turn").attrs["session.id"] == "ses_abc123"


def test_turn_session_is_inert_with_no_open_turn():
    t, tracer, _, _ = _telemetry()
    t.record_event({"node": "impl", "seq": 1, "phase": "enter"})
    # No turn_start: nothing to tag, and it must not touch the node span or raise.
    t.turn_session("ses_abc123")
    assert "session.id" not in tracer.by_name("impl").attrs


def test_unbounded_timeout_encodes_as_minus_one():
    t, tracer, _, _ = _telemetry()
    t.turn_start("impl", None, None, float("inf"))
    assert tracer.by_name("agent_turn").attrs["timeout_s"] == -1


def test_gas_and_heartbeat_metrics_record():
    t, _, meter, _ = _telemetry()
    t.gas_level(4999, 5000)
    t.gas_refuel("select_story")
    t.heartbeat("impl", 540.0)
    assert ("set", 4999, None) in meter.instruments["workhorse.gas"].records
    assert meter.instruments["workhorse.gas.refuels"].records == [
        ("add", 1, {"node": "select_story"})
    ]
    assert meter.instruments["workhorse.cap_wait.heartbeat"].records == [
        ("add", 1, {"node": "impl"})
    ]
    assert meter.instruments["workhorse.cap_wait.remaining_s"].records == [
        ("set", 540.0, {"node": "impl"})
    ]


def test_record_event_via_writer_reaches_active_telemetry(tmp_path=None):
    """End-to-end through the module facade: with a fake _Telemetry activated,
    ArtifactWriter events turn into spans (and the event log still writes)."""
    t, tracer, _, _ = _telemetry()
    otel._active = t
    try:
        with tempfile.TemporaryDirectory() as tmp:
            writer = artifacts.ArtifactWriter("wf", Path(tmp), run_id="r1")
            writer.write_checkpoint("node_a", {})
            writer.write_step("node_a", "p", {}, {}, next_node="node_b")
            assert tracer.by_name("node_a").ended
            lines = (writer.run_dir / "events.jsonl").read_text().splitlines()
            assert json.loads(lines[0])["phase"] == "enter"
    finally:
        otel._active = None


# --------------------------------------------------------------------------- #
# Live-run visibility: the signals that must escape while a node is OPEN
# --------------------------------------------------------------------------- #
def test_node_active_gauge_marks_the_open_node_and_clears_on_done():
    """The node-active gauge is the only thing that can answer 'where is the run
    right now': the node's span will not export until it ends, which is exactly
    what a hung node never does."""
    t, _, meter, _ = _telemetry()
    t.record_event({"node": "select_item", "seq": 1, "phase": "enter"})
    gauge = meter.instruments["workhorse.node.active"]
    assert gauge.records == [("set", 1, {"node": "select_item"})]
    t.record_event({"node": "select_item", "seq": 1, "phase": "done", "next": "guard"})
    assert gauge.records[-1] == ("set", 0, {"node": "select_item"})


def test_turn_heartbeat_reports_idleness_not_just_liveness():
    """idle_s is what separates a healthy long turn (streaming, so idle stays
    small) from a wedged one (silent, so idle climbs) — both of which look
    identical to a span that has not ended."""
    t, _, meter, _ = _telemetry()
    t.turn_heartbeat("investigate", 42.0, 300.0)
    assert meter.instruments["workhorse.turn.heartbeat"].records == [
        ("add", 1, {"node": "investigate"})
    ]
    assert meter.instruments["workhorse.turn.idle_s"].records == [
        ("set", 42.0, {"node": "investigate"})
    ]
    assert meter.instruments["workhorse.turn.elapsed_s"].records == [
        ("set", 300.0, {"node": "investigate"})
    ]


def test_run_heartbeat_tick_reports_the_open_node_and_its_age():
    """One tick of the background loop. This is the ONLY liveness signal a script
    node produces: it runs as a buffered subprocess, so there is no stream to hook
    a per-line heartbeat onto."""
    t, _, meter, _ = _telemetry()
    t.record_event({"node": "compute_coverage", "seq": 1, "phase": "enter"})
    t._beat_once()
    assert meter.instruments["workhorse.run.heartbeat"].records == [
        ("add", 1, {"node": "compute_coverage"})
    ]
    kind, value, attrs = meter.instruments["workhorse.node.elapsed_s"].records[-1]
    assert (kind, attrs) == ("set", {"node": "compute_coverage"})
    assert value >= 0.0


def test_run_heartbeat_beats_between_nodes_with_an_empty_stack():
    """Liveness is a property of the process, not of any node — a run must stay
    provably alive in the gap between two node visits."""
    t, _, meter, _ = _telemetry()
    t._beat_once()
    assert meter.instruments["workhorse.run.heartbeat"].records == [("add", 1, {"node": ""})]
    # No node is open, so there is no node age to report.
    assert meter.instruments["workhorse.node.elapsed_s"].records == []


def test_beat_survives_an_instrument_that_raises():
    """A telemetry bug must degrade to 'no heartbeat', never kill the thread and
    with it every later liveness signal."""
    t, _, _, _ = _telemetry()

    class Boom:
        def add(self, *_a, **_k):
            raise RuntimeError("instrument exploded")

    t._run_beats = Boom()
    t._beat_once()  # must return, not raise


def test_beat_loop_exits_promptly_when_stopped():
    t, _, _, _ = _telemetry()
    t._stop.set()
    t._beat_loop()  # returns immediately rather than sleeping the interval


def test_end_run_stops_the_heartbeat_before_flushing():
    """The last export must not race a tick claiming the run is still alive."""
    t, _, _, shutdown = _telemetry()
    t.end_run("terminal", None)
    assert t._stop.is_set()
    assert shutdown["called"] is True


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
