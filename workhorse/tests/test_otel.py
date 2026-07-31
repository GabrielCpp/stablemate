"""Tests for workhorse/otel.py — the opt-in OpenTelemetry facade.

Two halves:
- the ENABLEMENT GATE and the no-op it falls back to: WORKHORSE_OTEL's tri-state
  (force-on / force-off / auto) and the collector probe auto mode turns on, plus
  the inert-with-nothing-configured contract — every public function must be an
  exception-free call and ArtifactWriter._append_event must behave exactly as
  before (instrumentation may never change a run);
- the _Telemetry span logic, exercised with fake tracer/meter objects so the
  tests need no OTel SDK: (node, seq)-keyed enter/done pairing, flow nesting
  via the span stack, the end_run sweep of spans a crash left open, turn
  attrs/events, and the gas/heartbeat metrics.

Run: ./.venv/bin/python tests/test_otel.py   (or via pytest)
"""
from __future__ import annotations

import contextlib
import dataclasses
import importlib
import json
import socket
import tempfile
from pathlib import Path

otel = importlib.import_module("workhorse.otel")
records = importlib.import_module("workhorse.records")
usage = importlib.import_module("workhorse.runner.usage")
artifacts = importlib.import_module("workhorse.artifacts")


def _event(node: str, seq: int, phase: str, **extra):
    """One event exactly as ArtifactWriter writes it — the model record_event takes.

    Building the real `NodeEvent` rather than a dict is the point: the writer and
    the exporter now share one type, so a field renamed on it breaks here instead
    of silently dropping a span attribute."""
    return records.NodeEvent(ts="2026-01-01T00:00:00+00:00", seq=seq, node=node,
                             phase=phase, **extra)


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
        FakeTraceApi,
        tracer,
        meter,
        lambda: shutdown.__setitem__("called", True),
        otel.OtelSettings().heartbeat_every_s,
    )
    t.start_root("wf")
    return t, tracer, meter, shutdown


# --------------------------------------------------------------------------- #
# The no-op default
# --------------------------------------------------------------------------- #
def test_noop_by_default_all_calls_inert():
    assert otel.enabled() is False
    # Every public function must be safely callable with nothing configured.
    otel.record_event(_event("a", 1, "enter"))
    otel.gas_level(10, 100)
    otel.gas_refuel("select_story")
    otel.set_labels({"work_id": "w1"})
    otel.turn_start("a", "sonnet", "high", 600.0)
    otel.turn_session("ses_1")
    otel.turn_result(usage.TurnUsage(duration_ms=5, input_tokens=1))
    otel.turn_event("retry", attempt=1)
    otel.heartbeat("a", 120.0)
    otel.turn_heartbeat("a", 3.0, 90.0)
    otel.turn_end()
    otel.end_run("terminal")
    assert otel.current_node() == ""  # the null adapter answers, it does not raise
    assert otel.enabled() is False


class FakeTelemetry:
    """A stand-in for what _build returns: an object satisfying the Telemetry port.

    It answers `enabled()` truthfully, which is what the gate now reads — there is
    no `active is None` sentinel to assert on any more, because absence is the
    null adapter rather than a missing reference."""

    def __init__(self) -> None:
        self.ended: list[tuple[str, str | None]] = []

    def enabled(self) -> bool:
        return True

    def end_run(self, status: str, error: str | None = None) -> None:
        self.ended.append((status, error))


@contextlib.contextmanager
def installed(telemetry):
    """Install ``telemetry`` as the process's active adapter for the block.

    The module functions delegate to the installed host, so this is what makes
    ``otel.set_labels(...)`` land somewhere a test can read. Restoring the host
    ``install`` handed back is the whole teardown — there is no module state to
    put back by hand."""
    previous = otel.install(otel.TelemetryHost(active=telemetry))
    try:
        yield telemetry
    finally:
        otel.install(previous)


@contextlib.contextmanager
def _gate(forced, reachable, under_test=False):
    """Pin all three inputs start_run's gate reads: the WORKHORSE_OTEL tri-state, the
    collector probe, and the test-process guard. The probe must never be left live in
    a test — the dev machine may well have `groom serve` up, which would make these
    pass or fail by environment. The guard is pinned for the opposite reason: these
    tests *are* a test process, so left real it would answer True for every case and
    the gate's other two inputs would never be exercised. The build effect is faked
    too, so no test needs the optional SDK.

    All four are fields of the host this installs — nothing here assigns into the
    module. The previous host comes back from ``install`` and is put back at the end."""
    probes: list[str] = []
    built: list[tuple] = []
    host = otel.TelemetryHost(
        settings=dataclasses.replace(otel.OtelSettings(), forced=forced),
        probe=lambda endpoint, timeout_s: (probes.append(endpoint), reachable)[1],
        build=lambda *a: (built.append(a[:3]), FakeTelemetry())[1],
        under_test=lambda: under_test,
    )
    previous = otel.install(host)
    try:
        yield probes, built
    finally:
        otel.end_run("test")  # close what the test opened, through the real teardown
        otel.install(previous)


def test_tristate_parses_force_on_force_off_and_auto():
    assert otel._tristate(None) is None  # unset → auto
    assert otel._tristate("  ") is None  # blank → auto, not "on"
    for off in ("0", "false", "no", "FALSE"):
        assert otel._tristate(off) is False
    for on in ("1", "true", "yes", "anything"):
        assert otel._tristate(on) is True


def test_auto_activates_when_the_collector_answers():
    # The default path: nobody exported WORKHORSE_OTEL, groom is up, spans flow.
    with _gate(forced=None, reachable=True) as (probes, built):
        otel.start_run("wf", "run-1")
        assert otel.enabled() is True
        assert probes == [otel.OtelSettings().endpoint]
        assert built == [("wf", "run-1", None)]


def test_auto_stays_noop_when_no_collector_is_listening():
    with _gate(forced=None, reachable=False) as (_, built):
        otel.start_run("wf", "run-1")
        assert otel.enabled() is False
        assert built == []  # the SDK is never even built


def test_force_off_wins_over_a_reachable_collector():
    # WORKHORSE_OTEL=0 is the opt-out, and auto-on must not have weakened it.
    with _gate(forced=False, reachable=True) as (probes, built):
        otel.start_run("wf", "run-1")
        assert otel.enabled() is False
        assert probes == []  # not even probed — the answer can't change the outcome
        assert built == []


def test_force_on_skips_the_probe():
    # An explicit WORKHORSE_OTEL=1 targets a collector that may come up later (or
    # sit behind something a TCP connect can't see), so it must not be gated on it.
    with _gate(forced=True, reachable=False) as (probes, built):
        otel.start_run("wf", "run-1")
        assert otel.enabled() is True
        assert probes == []
        assert built == [("wf", "run-1", None)]


def test_auto_declines_in_a_test_process():
    # A suite run on a machine with `groom serve` up used to export like a real run,
    # hundreds of times per invocation, into the same store the dashboard reads.
    with _gate(forced=None, reachable=True, under_test=True) as (probes, built):
        otel.start_run("wf", "run-1")
        assert otel.enabled() is False
        assert probes == []  # not even probed — the answer can't change the outcome
        assert built == []


def test_force_on_still_wins_in_a_test_process():
    # The escape hatch the telemetry tests themselves need: WORKHORSE_OTEL=1 means
    # the operator has said so, and the guard is a default, not a prohibition.
    with _gate(forced=True, reachable=False, under_test=True) as (_, built):
        otel.start_run("wf", "run-1")
        assert otel.enabled() is True
        assert built == [("wf", "run-1", None)]


def test_under_test_detects_this_very_process():
    # Self-evidencing: whatever runs this file (pytest, or `python tests/test_otel.py`)
    # is a test process, so the real predicate — not the pinned one — must say so.
    assert otel._under_test() is True


def test_probe_detects_a_listening_socket_and_a_dead_port():
    # The real probe against a real socket: bound-and-listening is reachable,
    # and the same port is not once it's closed.
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert otel._collector_reachable(f"http://127.0.0.1:{port}", 0.25) is True
    assert otel._collector_reachable(f"http://127.0.0.1:{port}", 0.25) is False


def test_probe_treats_a_malformed_endpoint_as_no_collector():
    # Never raises out of start_run's gate, whatever the endpoint says.
    assert otel._collector_reachable("not-a-url", 0.25) is False
    assert otel._collector_reachable("", 0.25) is False


def test_metric_export_defaults_to_the_heartbeat_interval():
    # The export interval, not the heartbeat, is what bounds a collector's freshness:
    # beats recorded every 10s but shipped on the SDK's 60s default leave a dead run
    # looking alive for the better part of a minute. Default them to the same clock.
    settings = otel.OtelSettings.from_env({})
    assert settings.metric_export_every_s == settings.heartbeat_every_s


def test_metric_export_honors_both_knobs_ours_first():
    sdk_only = otel.OtelSettings.from_env({"OTEL_METRIC_EXPORT_INTERVAL": "15000"})
    assert sdk_only.metric_export_every_s == 15.0  # the SDK's own knob still wins
    both = otel.OtelSettings.from_env(
        {"OTEL_METRIC_EXPORT_INTERVAL": "15000", "WORKHORSE_OTEL_METRIC_EXPORT_S": "3"}
    )
    assert both.metric_export_every_s == 3.0  # ...but ours is more specific


def test_metric_export_falls_through_garbage_rather_than_raising():
    # This runs on the start-up path of every telemetry-enabled run, so a typo in the
    # environment must cost a default, never the run.
    garbage = otel.OtelSettings.from_env(
        {"WORKHORSE_OTEL_METRIC_EXPORT_S": "soon", "OTEL_METRIC_EXPORT_INTERVAL": "15000"}
    )
    assert garbage.metric_export_every_s == 15.0
    zero = otel.OtelSettings.from_env(
        {"WORKHORSE_OTEL_METRIC_EXPORT_S": "0", "OTEL_METRIC_EXPORT_INTERVAL": ""}
    )
    assert zero.metric_export_every_s == zero.heartbeat_every_s


def test_settings_are_read_from_the_mapping_it_is_handed():
    # The four reads used to happen at import, so this — the whole point of the
    # settings object — was previously untestable without reloading the module.
    settings = otel.OtelSettings.from_env(
        {
            "WORKHORSE_OTEL": "0",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector.example.com:4318/",
            "WORKHORSE_OTEL_PROBE_S": "1.5",
            "WORKHORSE_OTEL_HEARTBEAT_S": "30",
        }
    )
    assert settings.forced is False
    assert settings.endpoint == "http://collector.example.com:4318"  # trailing / trimmed
    assert settings.probe_timeout_s == 1.5
    assert settings.heartbeat_every_s == 30.0
    assert settings.metric_export_every_s == 30.0  # follows the heartbeat by default


def test_settings_defaults_match_the_documented_ones():
    # GUARDRAILS.md is the operator contract for these four names; the defaults are
    # stated once, as field defaults, and from_env({}) must reproduce them exactly.
    assert otel.OtelSettings.from_env({}) == otel.OtelSettings()


def test_append_event_unchanged_with_noop_telemetry():
    with tempfile.TemporaryDirectory() as tmp:
        writer = artifacts.ArtifactWriter("wf", Path(tmp), run_id="r1")
        writer.record_node("node_a", "enter")
        writer.write_step("node_a", "prompt", {"out": 1}, {"k": "v"}, next_node="node_b")
        events = writer.read_events()
        assert [(e.node, e.phase) for e in events] == [
            ("node_a", "enter"),
            ("node_a", "done"),
        ]
        assert events[1].model_extra == {"next": "node_b"}


# --------------------------------------------------------------------------- #
# _Telemetry span pairing (with fakes; no SDK required)
# --------------------------------------------------------------------------- #
def test_enter_done_pairs_a_node_span_and_records_next():
    t, tracer, _, _ = _telemetry()
    t.record_event(_event("plan", 1, "enter"))
    span = tracer.by_name("plan")
    assert span.parent is tracer.by_name("run:wf")
    assert span.attrs["workhorse.seq"] == 1 and not span.ended
    t.record_event(_event("plan", 1, "done", next="build"))
    assert span.ended and span.attrs["workhorse.next"] == "build"


def test_flow_children_nest_under_the_open_flow_node_span():
    t, tracer, _, _ = _telemetry()
    t.record_event(_event("qa_flow", 3, "enter"))
    t.record_event(_event("child", 1, "enter"))
    child = tracer.by_name("child")
    assert child.parent is tracer.by_name("qa_flow")
    assert child.attrs["workhorse.depth"] == 1
    # The child's terminal lands on the enclosing flow-node span, not the root.
    t.record_event(_event("child", 1, "done", next=None))
    t.record_event(_event("<run>", 1, "terminal", terminal="terminal"))
    assert ("terminal", {"terminal": "terminal"}) in tracer.by_name("qa_flow").events
    t.record_event(_event("qa_flow", 3, "done", next="wrap"))
    assert tracer.by_name("qa_flow").ended


def test_loop_revisits_pair_by_seq():
    """The same node visited twice (a loop) gets two distinct spans, each done
    event closing its own visit's span via the (node, seq) key."""
    t, tracer, _, _ = _telemetry()
    t.record_event(_event("work", 1, "enter"))
    t.record_event(_event("work", 1, "done", next="work"))
    t.record_event(_event("work", 2, "enter"))
    spans = [s for s in tracer.spans if s.name == "work"]
    assert len(spans) == 2
    assert spans[0].ended and not spans[1].ended


def test_end_run_sweeps_open_spans_and_flags_error():
    t, tracer, _, shutdown = _telemetry()
    t.record_event(_event("stuck", 1, "enter"))
    t.end_run("fail", "out of gas")
    stuck, root = tracer.by_name("stuck"), tracer.by_name("run:wf")
    assert stuck.ended and stuck.status.code == "ERROR"
    assert root.ended and root.attrs["workhorse.terminal"] == "fail"
    assert root.status.code == "ERROR"
    assert shutdown["called"] is True


def test_done_without_matching_enter_is_ignored():
    t, tracer, _, _ = _telemetry()
    t.record_event(_event("ghost", 9, "done", next="x"))
    assert [s.name for s in tracer.spans] == ["run:wf"]


def test_turn_span_attrs_result_usage_and_fallback_events():
    t, tracer, _, _ = _telemetry()
    t.record_event(_event("impl", 1, "enter"))
    t.turn_start("impl", "opus", "high", 3600.0)
    turn = tracer.by_name("agent_turn")
    assert turn.parent is tracer.by_name("impl")
    assert turn.attrs["model"] == "opus" and turn.attrs["timeout_s"] == 3600
    t.turn_result(usage.TurnUsage(duration_ms=1234, input_tokens=10, output_tokens=20))
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
    t.record_event(_event("impl", 1, "enter"))
    t.turn_start("impl", "opus", "high", 3600.0)
    t.turn_session("ses_abc123")
    assert tracer.by_name("agent_turn").attrs["session.id"] == "ses_abc123"


def test_turn_session_is_inert_with_no_open_turn():
    t, tracer, _, _ = _telemetry()
    t.record_event(_event("impl", 1, "enter"))
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
    with installed(t), tempfile.TemporaryDirectory() as tmp:
        writer = artifacts.ArtifactWriter("wf", Path(tmp), run_id="r1")
        writer.record_node("node_a", "enter")
        writer.write_step("node_a", "p", {}, {}, next_node="node_b")
        assert tracer.by_name("node_a").ended
        lines = (writer.run_dir / "events.jsonl").read_text().splitlines()
        assert json.loads(lines[0])["phase"] == "enter"


# --------------------------------------------------------------------------- #
# Live-run visibility: the signals that must escape while a node is OPEN
# --------------------------------------------------------------------------- #
def test_node_active_gauge_marks_the_open_node_and_clears_on_done():
    """The node-active gauge is the only thing that can answer 'where is the run
    right now': the node's span will not export until it ends, which is exactly
    what a hung node never does."""
    t, _, meter, _ = _telemetry()
    t.record_event(_event("select_item", 1, "enter"))
    gauge = meter.instruments["workhorse.node.active"]
    assert gauge.records == [("set", 1, {"node": "select_item"})]
    t.record_event(_event("select_item", 1, "done", next="guard"))
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
    t.record_event(_event("compute_coverage", 1, "enter"))
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
