"""Tests for workhorse/otel.py — the opt-in OpenTelemetry facade."""
from __future__ import annotations

import contextlib
import dataclasses
import json
import socket
import tempfile
from pathlib import Path

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.common.metrics_encoder import encode_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider

from _fakes import FakeBackend, FakeClock, RecordingTelemetry
from workhorse import artifacts, otel, records, reload
from workhorse.config_run import AgentResilience
from workhorse.runner import ladder, usage


def _event(node: str, seq: int, phase: records.NodePhase, **extra):
    """One event exactly as ArtifactWriter writes it — the model record_event takes."""
    return records.NodeEvent(ts="2026-01-01T00:00:00+00:00", seq=seq, node=node,
                             phase=phase, **extra)


class FakeSpan:
    def __init__(self, name: str, context, attributes) -> None:
        self.name = name
        self.parent = context
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
        return span


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


def test_noop_by_default_all_calls_inert():
    assert otel.enabled() is False
    otel.record_event(_event("a", 1, "enter"))
    otel.state_start("start", 1)
    otel.state_end("start", 1, "finish")
    with otel.wait("operator", "start"):
        pass
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
    assert otel.current_node() == ""
    assert otel.enabled() is False


class FakeTelemetry(otel._NullTelemetry):
    """A stand-in for what _build returns: an object satisfying the Telemetry port."""

    def __init__(self) -> None:
        self.ended: list[tuple[str, str | None]] = []

    def enabled(self) -> bool:
        return True

    def end_run(
        self,
        status: str,
        error: str | None = None,
        error_class: str = "",
        error_kind: str = "",
    ) -> None:
        self.ended.append((status, error))


@contextlib.contextmanager
def installed(telemetry):
    """Install ``telemetry`` as the process's active adapter for the block."""
    previous = otel.install(otel.TelemetryHost(active=telemetry))
    try:
        yield telemetry
    finally:
        otel.install(previous)


@contextlib.contextmanager
def _gate(forced, reachable, under_test=False):
    """Pin all three inputs start_run's gate reads: the WORKHORSE_OTEL tri-state, the collector probe, and the test-process guard."""
    probes: list[str] = []
    built: list[tuple] = []
    host = otel.TelemetryHost(
        settings=dataclasses.replace(otel.OtelSettings(), forced=forced),
        probe=lambda endpoint, timeout_s: (probes.append(endpoint), reachable)[1],
        build=lambda workflow, run_id, run_dir, settings: (
            built.append((workflow, run_id, run_dir)),
            FakeTelemetry(),
        )[1],
        under_test=lambda: under_test,
    )
    previous = otel.install(host)
    try:
        yield probes, built
    finally:
        otel.end_run("test")
        otel.install(previous)


def test_tristate_parses_force_on_force_off_and_auto():
    assert otel._tristate(None) is None
    assert otel._tristate("  ") is None
    for off in ("0", "false", "no", "FALSE"):
        assert otel._tristate(off) is False
    for on in ("1", "true", "yes", "anything"):
        assert otel._tristate(on) is True


def test_auto_activates_when_the_collector_answers():
    with _gate(forced=None, reachable=True) as (probes, built):
        otel.start_run("wf", "run-1")
        assert otel.enabled() is True
        assert probes == [otel.OtelSettings().endpoint]
        assert built == [("wf", "run-1", None)]


def test_auto_stays_noop_when_no_collector_is_listening():
    with _gate(forced=None, reachable=False) as (_, built):
        otel.start_run("wf", "run-1")
        assert otel.enabled() is False
        assert built == []


def test_force_off_wins_over_a_reachable_collector():
    with _gate(forced=False, reachable=True) as (probes, built):
        otel.start_run("wf", "run-1")
        assert otel.enabled() is False
        assert probes == []
        assert built == []


def test_force_on_skips_the_probe():
    with _gate(forced=True, reachable=False) as (probes, built):
        otel.start_run("wf", "run-1")
        assert otel.enabled() is True
        assert probes == []
        assert built == [("wf", "run-1", None)]


def test_auto_declines_in_a_test_process():
    with _gate(forced=None, reachable=True, under_test=True) as (probes, built):
        otel.start_run("wf", "run-1")
        assert otel.enabled() is False
        assert probes == []
        assert built == []


def test_force_on_still_wins_in_a_test_process():
    with _gate(forced=True, reachable=False, under_test=True) as (_, built):
        otel.start_run("wf", "run-1")
        assert otel.enabled() is True
        assert built == [("wf", "run-1", None)]


def test_under_test_detects_this_very_process():
    assert otel._under_test() is True


def test_probe_detects_a_listening_socket_and_a_dead_port():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert otel._collector_reachable(f"http://127.0.0.1:{port}", 0.25) is True
    assert otel._collector_reachable(f"http://127.0.0.1:{port}", 0.25) is False


def test_probe_treats_a_malformed_endpoint_as_no_collector():
    assert otel._collector_reachable("not-a-url", 0.25) is False
    assert otel._collector_reachable("", 0.25) is False


def test_metric_export_defaults_to_the_heartbeat_interval():
    settings = otel.OtelSettings.from_env({})
    assert settings.metric_export_every_s == settings.heartbeat_every_s


def test_metric_export_honors_both_knobs_ours_first():
    sdk_only = otel.OtelSettings.from_env({"OTEL_METRIC_EXPORT_INTERVAL": "15000"})
    assert sdk_only.metric_export_every_s == 15.0
    both = otel.OtelSettings.from_env(
        {"OTEL_METRIC_EXPORT_INTERVAL": "15000", "WORKHORSE_OTEL_METRIC_EXPORT_S": "3"}
    )
    assert both.metric_export_every_s == 3.0


def test_metric_export_falls_through_garbage_rather_than_raising():
    garbage = otel.OtelSettings.from_env(
        {"WORKHORSE_OTEL_METRIC_EXPORT_S": "soon", "OTEL_METRIC_EXPORT_INTERVAL": "15000"}
    )
    assert garbage.metric_export_every_s == 15.0
    zero = otel.OtelSettings.from_env(
        {"WORKHORSE_OTEL_METRIC_EXPORT_S": "0", "OTEL_METRIC_EXPORT_INTERVAL": ""}
    )
    assert zero.metric_export_every_s == zero.heartbeat_every_s


def test_settings_are_read_from_the_mapping_it_is_handed():
    settings = otel.OtelSettings.from_env(
        {
            "WORKHORSE_OTEL": "0",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector.example.com:4318/",
            "WORKHORSE_OTEL_PROBE_S": "1.5",
            "WORKHORSE_OTEL_HEARTBEAT_S": "30",
        }
    )
    assert settings.forced is False
    assert settings.endpoint == "http://collector.example.com:4318"
    assert settings.probe_timeout_s == 1.5
    assert settings.heartbeat_every_s == 30.0
    assert settings.metric_export_every_s == 30.0


def test_settings_defaults_match_the_documented_ones():
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


def test_enter_done_pairs_a_node_span_and_records_next():
    t, tracer, _, _ = _telemetry()
    t.record_event(_event("plan", 1, "enter"))
    span = tracer.by_name("plan")
    assert span.parent is tracer.by_name("run:wf")
    assert span.attrs["workhorse.seq"] == 1 and not span.ended
    t.record_event(_event("plan", 1, "done", next="build"))
    assert span.ended and span.attrs["workhorse.next"] == "build"


def test_checkpoint_enters_do_not_open_execution_spans():
    """A checkpoint records durable position, not work being executed."""
    t, tracer, _, _ = _telemetry()
    t.record_event(_event("start", 1, "enter", waiting_on=None))
    t.record_event(_event("finish", 2, "enter", waiting_on="operator.md"))
    assert [span.name for span in tracer.spans] == ["run:wf"]


def test_state_spans_are_siblings_and_contain_their_nodes():
    """Sequential states must not become nested suffixes that last until run shutdown."""
    t, tracer, _, _ = _telemetry()
    t.state_start("start", 1)
    t.record_event(_event("measure", 1, "enter"))
    t.record_event(_event("measure", 1, "done"))
    t.state_end("start", 1, "finish")
    t.state_start("finish", 2)
    t.state_end("finish", 2)

    root = tracer.by_name("run:wf")
    start = tracer.by_name("state:start")
    finish = tracer.by_name("state:finish")
    assert tracer.by_name("measure").parent is start
    assert start.parent is root and finish.parent is root
    assert start.attrs["workhorse.span_kind"] == "state"
    assert start.attrs["workhorse.next"] == "finish"
    assert start.ended and finish.ended


def test_wait_span_records_kind_node_and_outcome_without_replacing_the_node():
    t, tracer, meter, _ = _telemetry()
    t.state_start("review", 1)
    token = t.wait_start("cap", "review-qa-plan")
    wait_span = tracer.by_name("wait:cap")
    assert wait_span.parent is tracer.by_name("state:review")
    assert wait_span.attrs["workhorse.span_kind"] == "wait"
    assert wait_span.attrs["workhorse.wait_kind"] == "cap"
    assert wait_span.attrs["workhorse.node"] == "review-qa-plan"
    assert meter.instruments["workhorse.node.active"].records == [
        ("set", 1, {"node": "review"})
    ]
    wait_attrs = {"node": "review-qa-plan", "wait_kind": "cap"}
    assert meter.instruments["workhorse.wait.active"].records == [
        ("set", 1, wait_attrs)
    ]
    assert meter.instruments["workhorse.wait.elapsed_s"].records == [
        ("set", 0.0, wait_attrs)
    ]
    t._beat_once()
    assert meter.instruments["workhorse.wait.elapsed_s"].records[-1][0] == "set"
    assert meter.instruments["workhorse.wait.elapsed_s"].records[-1][2] == wait_attrs
    t.wait_end(token)
    assert wait_span.ended
    assert wait_span.attrs["workhorse.wait_outcome"] == "completed"
    assert meter.instruments["workhorse.wait.active"].records[-1] == (
        "set",
        0,
        wait_attrs,
    )


def test_an_interrupted_node_records_why_on_its_span():
    """`record_interrupt` has always written `phase="error"` to events.jsonl, and record_event had no branch for it — so a run killed mid-node left its cause sitting on disk, unexported."""
    t, tracer, _, _ = _telemetry()
    t.record_event(_event("plan", 1, "enter"))
    t.record_event(_event("plan", 1, "error", error="KeyboardInterrupt"))
    span = tracer.by_name("plan")
    assert span.events[-1] == ("error", {"error": "KeyboardInterrupt"})


def test_operator_wait_keeps_gate_attributes_until_its_metric_series_closes():
    t, tracer, meter, _ = _telemetry()
    t.set_labels({"activity": "review"})
    token = t.wait_start("operator", "review", "/run/question.md", "Which branch?")
    attrs = meter.instruments["workhorse.wait.active"].records[-1][2]
    assert attrs["gate_path"] == "/run/question.md"
    assert attrs["gate_question"] == "Which branch?"
    t.set_labels({"activity": "answer"})
    t._beat_once()
    assert meter.instruments["workhorse.wait.elapsed_s"].records[-1][2] == attrs
    t.wait_end(token)
    assert meter.instruments["workhorse.wait.active"].records[-1] == ("set", 0, attrs)
    assert meter.instruments["workhorse.wait.elapsed_s"].records[-1][2] == attrs
    span = tracer.by_name("wait:operator")
    assert span.attrs["workhorse.gate_question"] == "Which branch?"


def test_heartbeat_republishes_active_state_for_a_reconnected_collector():
    reader = InMemoryMetricReader()
    meters = MeterProvider(metric_readers=[reader])
    traces = TracerProvider()
    telemetry = otel._Telemetry(trace, traces.get_tracer("test"), meters.get_meter("test"),
                                lambda: None, 30)
    try:
        telemetry.state_start("review", 1)
        token = telemetry.wait_start("operator", "review", "/run/gate.md", "Proceed?")
        assert reader.get_metrics_data() is not None
        telemetry._beat_once()
        data = reader.get_metrics_data()
        assert data is not None
        exported = encode_metrics(data)
        gauges = {metric.name: list(metric.gauge.data_points)
                  for resource in exported.resource_metrics
                  for scope in resource.scope_metrics for metric in scope.metrics
                  if metric.HasField("gauge")}
        assert gauges["workhorse.node.active"][0].as_int == 1
        point = gauges["workhorse.wait.active"][0]
        assert point.as_int == 1
        attrs = {attr.key: attr.value.string_value for attr in point.attributes}
        assert attrs["gate_path"] == "/run/gate.md"
        assert attrs["gate_question"] == "Proceed?"
        telemetry.wait_end(token)
    finally:
        telemetry.end_run("terminal")
        meters.shutdown()
        traces.shutdown()


def test_exported_operator_wait_has_no_active_series_after_answer():
    reader = InMemoryMetricReader()
    meters = MeterProvider(metric_readers=[reader])
    traces = TracerProvider()
    telemetry = otel._Telemetry(trace, traces.get_tracer("test"), meters.get_meter("test"),
                                lambda: None, 30)
    try:
        token = telemetry.wait_start("operator", "review", "/run/gate.md", "Proceed?")
        assert reader.get_metrics_data() is not None
        telemetry._beat_once()
        telemetry.wait_end(token)
        data = reader.get_metrics_data()
        assert data is not None
        exported = encode_metrics(data)
        points = [point for resource in exported.resource_metrics
                  for scope in resource.scope_metrics for metric in scope.metrics
                  if metric.name == "workhorse.wait.active" for point in metric.gauge.data_points]
        assert len(points) == 1
        assert points[0].as_int == 0
        attrs = {attr.key: attr.value.string_value for attr in points[0].attributes}
        assert attrs["gate_path"] == "/run/gate.md"
        assert attrs["gate_question"] == "Proceed?"
    finally:
        telemetry.end_run("terminal")
        meters.shutdown()
        traces.shutdown()


def test_a_failed_turn_carries_its_class_and_recovery_bucket():
    """A store can count failed turns from the status alone."""
    t, tracer, _, _ = _telemetry()
    t.turn_start("plan", "sonnet", "high", 60.0, backend="claude")
    t.turn_end(
        error="usage limit reached",
        error_class="BackendInvocationError",
        error_kind="cap",
    )
    turn = tracer.by_name("agent_turn")
    assert turn.attrs["error.class"] == "BackendInvocationError"
    assert turn.attrs["error.kind"] == "cap"


def test_a_node_the_workflow_calls_infra_is_marked_as_such():
    """Bringing a stack up is wall-clock the model spends idle."""
    t, tracer, _, _ = _telemetry()
    t.record_event(_event("ensure_stack", 1, "enter", span_kind="infra"))
    assert tracer.by_name("ensure_stack").attrs["workhorse.span_kind"] == "infra"


def test_a_node_the_workflow_says_nothing_about_carries_no_span_kind():
    """Absent, not "compute": workhorse must not classify a node the workflow did not."""
    t, tracer, _, _ = _telemetry()
    t.record_event(_event("plan", 1, "enter"))
    assert "workhorse.span_kind" not in tracer.by_name("plan").attrs


def test_a_run_level_fact_lands_on_the_root_span_and_the_last_write_wins():
    """`workhorse.profile` is the caller this exists for, and a `control switch-profile` means it can be written twice."""
    t, tracer, _, _ = _telemetry()

    t.run_attribute("workhorse.profile", "cheap")
    assert tracer.by_name("run:wf").attrs["workhorse.profile"] == "cheap"

    t.run_attribute("workhorse.profile", "local")
    assert tracer.by_name("run:wf").attrs["workhorse.profile"] == "local"

    t.end_run("terminal")
    t.run_attribute("workhorse.profile", "too-late")


def test_a_run_level_fact_is_inert_with_telemetry_off():
    """The facade path: nothing installs a host in a test process, so this is what every call site really executes on a machine with no collector."""
    otel.run_attribute("workhorse.profile", "cheap")


def test_resume_generation_counts_starts_of_one_run_directory():
    """A resume reuses the run_id and opens a fresh root span, so without this a gap between two spans cannot be told apart from a process that sat waiting."""
    with tempfile.TemporaryDirectory() as tmp:
        assert otel._resume_generation(tmp) == 1
        assert otel._resume_generation(tmp) == 2
        assert otel._resume_generation(tmp) == 3
        with tempfile.TemporaryDirectory() as other:
            assert otel._resume_generation(other) == 1


def test_resume_generation_never_fails_a_run_over_its_own_bookkeeping():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / otel._GENERATION_FILE).write_text("not a number")
        assert otel._resume_generation(tmp) == 1
    assert otel._resume_generation(None) == 0
    assert otel._resume_generation("") == 0


def test_a_failed_run_carries_its_class_through_the_module_facade():
    """Through `otel.end_run`, not the adapter directly."""
    t, tracer, _, _ = _telemetry()
    with installed(t):
        otel.end_run(
            "fail",
            error="transition budget exhausted",
            error_class="RunBudgetExceeded",
            error_kind="fatal",
        )
    root = tracer.by_name("run:wf")
    assert root.attrs["workhorse.terminal"] == "fail"
    assert root.attrs["error.class"] == "RunBudgetExceeded"
    assert root.attrs["error.kind"] == "fatal"


def test_a_clean_turn_carries_no_error_attributes():
    t, tracer, _, _ = _telemetry()
    t.turn_start("plan", "sonnet", "high", 60.0, backend="claude")
    t.turn_end()
    turn = tracer.by_name("agent_turn")
    assert "error.class" not in turn.attrs and "error.kind" not in turn.attrs


def test_flow_children_nest_under_the_open_flow_node_span():
    t, tracer, _, _ = _telemetry()
    t.record_event(_event("qa_flow", 3, "enter"))
    t.record_event(_event("child", 1, "enter"))
    child = tracer.by_name("child")
    assert child.parent is tracer.by_name("qa_flow")
    assert child.attrs["workhorse.depth"] == 1
    t.record_event(_event("child", 1, "done", next=None))
    t.record_event(_event("<run>", 1, "terminal", terminal="terminal"))
    assert ("terminal", {"terminal": "terminal"}) in tracer.by_name("qa_flow").events
    t.record_event(_event("qa_flow", 3, "done", next="wrap"))
    assert tracer.by_name("qa_flow").ended


def test_unfinished_nested_spans_close_without_error_status():
    """A recovered non-terminal interruption leaves an unfinished child span, but that span did not cause the flow to enter its failure terminal."""
    t, tracer, _, _ = _telemetry()
    t.record_event(_event("parent", 1, "enter"))
    t.record_event(_event("child", 2, "enter"))

    t.record_event(_event("parent", 1, "done", next="recover"))

    child = tracer.by_name("child")
    assert child.ended
    assert child.status is None or child.status.code != "ERROR"


def test_loop_revisits_pair_by_seq():
    """The same node visited twice (a loop) gets two distinct spans, each done event closing its own visit's span via the (node, seq) key."""
    t, tracer, _, _ = _telemetry()
    t.record_event(_event("work", 1, "enter"))
    t.record_event(_event("work", 1, "done", next="work"))
    t.record_event(_event("work", 2, "enter"))
    spans = [s for s in tracer.spans if s.name == "work"]
    assert len(spans) == 2
    assert spans[0].ended and not spans[1].ended


def test_failed_end_run_sweeps_open_spans_and_flags_error():
    t, tracer, _, shutdown = _telemetry()
    t.record_event(_event("stuck", 1, "enter"))
    t.end_run("fail", "out of gas")
    stuck, root = tracer.by_name("stuck"), tracer.by_name("run:wf")
    assert stuck.ended and stuck.attrs["workhorse.outcome"] == "abandoned"
    assert stuck.status is None or stuck.status.code != "ERROR"
    assert root.ended and root.attrs["workhorse.terminal"] == "fail"
    assert root.status.code == "ERROR"
    assert shutdown["called"] is True


def test_interrupted_end_run_sweeps_open_spans_without_error_status():
    t, tracer, _, shutdown = _telemetry()
    t.record_event(_event("stuck", 1, "enter"))

    t.end_run(
        "interrupted",
        "KeyboardInterrupt",
        error_class="KeyboardInterrupt",
        error_kind="interrupt",
    )

    stuck, root = tracer.by_name("stuck"), tracer.by_name("run:wf")
    assert stuck.ended
    assert stuck.status is None or stuck.status.code != "ERROR"
    assert root.ended and root.attrs["workhorse.terminal"] == "interrupted"
    assert root.status is None or root.status.code != "ERROR"
    assert root.attrs["error.class"] == "KeyboardInterrupt"
    assert root.attrs["error.kind"] == "interrupt"
    assert shutdown["called"] is True


def test_aborted_end_run_remains_an_error() -> None:
    t, tracer, _, _ = _telemetry()
    t.record_event(_event("stuck", 1, "enter"))

    t.end_run(
        "aborted",
        "run aborted before finalize",
        error_class="RuntimeError",
        error_kind="fatal",
    )

    stuck, root = tracer.by_name("stuck"), tracer.by_name("run:wf")
    assert stuck.ended and stuck.attrs["workhorse.outcome"] == "abandoned"
    assert stuck.status is None or stuck.status.code != "ERROR"
    assert root.ended and root.attrs["workhorse.terminal"] == "aborted"
    assert root.status.code == "ERROR"
    assert root.attrs["error.class"] == "RuntimeError"
    assert root.attrs["error.kind"] == "fatal"


def test_scope_closes_the_frames_it_opened_and_blames_only_the_innermost():
    """One defect is one ERROR span, however deep the frame that raised."""
    t, tracer, _, _ = _telemetry()
    previous = otel.install(otel.TelemetryHost(active=t))
    try:
        boom = AttributeError("no such attribute")
        try:
            with otel.scope():
                t.state_start("verify", 1)
                with otel.scope():
                    t.record_event(_event("build_context", 1, "enter"))
                    raise boom
        except AttributeError:
            pass
    finally:
        otel.install(previous)

    state, node = tracer.by_name("state:verify"), tracer.by_name("build_context")
    assert state.ended and node.ended
    assert t.open_depth() == 0
    assert node.status.code == "ERROR"
    assert node.attrs["error.class"] == "AttributeError"
    assert state.attrs["workhorse.outcome"] == "error"
    assert state.status is None or state.status.code != "ERROR"

    t.end_run("fail", str(boom))
    root = tracer.by_name("run:wf")
    assert root.attrs["workhorse.terminal"] == "fail"
    assert root.status is None or root.status.code != "ERROR"
    assert sum(1 for s in tracer.spans if s.status and s.status.code == "ERROR") == 1


def test_a_reload_unwind_closes_its_frames_without_counting_as_a_failure():
    """A deliberate reload is not the run's error, and groom's badge counts ERROR spans."""
    t, tracer, _, _ = _telemetry()
    previous = otel.install(otel.TelemetryHost(active=t))
    try:
        try:
            with otel.scope():
                t.state_start("dev", 1)
                with otel.scope():
                    t.record_event(_event("validate_paths", 1, "enter"))
                    raise reload.ReloadRequested("reload requested at the boundary")
        except reload.ReloadRequested:
            pass
    finally:
        otel.install(previous)

    state, node = tracer.by_name("state:dev"), tracer.by_name("validate_paths")
    assert state.ended and node.ended
    assert t.open_depth() == 0
    for span in (state, node):
        assert span.status is None or span.status.code != "ERROR", span
        assert "error.class" not in span.attrs, span
        assert span.attrs["workhorse.outcome"] == "control"
        assert span.attrs["workhorse.control"] == "ReloadRequested"
    assert not any(s.status and s.status.code == "ERROR" for s in tracer.spans)

    previous = otel.install(otel.TelemetryHost(active=t))
    try:
        try:
            with otel.scope():
                t.record_event(_event("later_node", 2, "enter"))
                raise AttributeError("no such attribute")
        except AttributeError:
            pass
    finally:
        otel.install(previous)
    later = tracer.by_name("later_node")
    assert later.status.code == "ERROR"
    assert later.attrs["error.class"] == "AttributeError"


def test_end_run_is_idempotent_and_the_first_status_wins():
    """The driver calls this more than once by design — a finalizing branch stamps its own status and a `finally` stamps `aborted` behind it as the crash backstop."""
    t, tracer, _, shutdown = _telemetry()
    t.end_run("terminal")
    shutdown["called"] = False
    t.end_run("aborted", "run aborted before finalize")

    root = tracer.by_name("run:wf")
    assert root.attrs["workhorse.terminal"] == "terminal", root.attrs
    assert root.status is None or root.status.code != "ERROR", root.status
    assert shutdown["called"] is False, "the second end_run flushed again"


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
    """End-to-end through the module facade: with a fake _Telemetry activated, ArtifactWriter events turn into spans (and the event log still writes)."""
    t, tracer, _, _ = _telemetry()
    with installed(t), tempfile.TemporaryDirectory() as tmp:
        writer = artifacts.ArtifactWriter("wf", Path(tmp), run_id="r1")
        writer.record_node("node_a", "enter")
        writer.write_step("node_a", "p", {}, {}, next_node="node_b")
        assert tracer.by_name("node_a").ended
        lines = (writer.run_dir / "events.jsonl").read_text().splitlines()
        assert json.loads(lines[0])["phase"] == "enter"


def test_node_active_gauge_marks_the_open_node_and_clears_on_done():
    """The node-active gauge is the only thing that can answer 'where is the run right now': the node's span will not export until it ends, which is exactly what a hung node never does."""
    t, _, meter, _ = _telemetry()
    t.record_event(_event("select_item", 1, "enter"))
    gauge = meter.instruments["workhorse.node.active"]
    assert gauge.records == [("set", 1, {"node": "select_item"})]
    t.record_event(_event("select_item", 1, "done", next="guard"))
    assert gauge.records[-1] == ("set", 0, {"node": "select_item"})


def test_turn_heartbeat_reports_idleness_not_just_liveness():
    """idle_s is what separates a healthy long turn (streaming, so idle stays small) from a wedged one (silent, so idle climbs) — both of which look identical to a span that has not ended."""
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


def test_turn_lifecycle_clears_stale_idle_when_the_turn_ends():
    t, _, meter, _ = _telemetry()

    t.turn_start("investigate", "sonnet", "high", 300.0)
    t.turn_heartbeat("investigate", 42.0, 120.0)
    t.turn_end()

    assert meter.instruments["workhorse.turn.active"].records == [
        ("set", 1, {"node": "investigate"}),
        ("set", 1, {"node": "investigate"}),
        ("set", 0, {"node": "investigate"}),
    ]
    assert meter.instruments["workhorse.turn.idle_s"].records[-1] == (
        "set",
        0.0,
        {"node": "investigate"},
    )
    assert meter.instruments["workhorse.turn.elapsed_s"].records[-1] == (
        "set",
        0.0,
        {"node": "investigate"},
    )


def test_run_heartbeat_tick_reports_the_open_node_and_its_age():
    """One tick of the background loop."""
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
    """Liveness is a property of the process, not of any node — a run must stay provably alive in the gap between two node visits."""
    t, _, meter, _ = _telemetry()
    t._beat_once()
    assert meter.instruments["workhorse.run.heartbeat"].records == [("add", 1, {"node": ""})]
    assert meter.instruments["workhorse.node.elapsed_s"].records == []


def test_beat_survives_an_instrument_that_raises():
    """A telemetry bug must degrade to 'no heartbeat', never kill the thread and with it every later liveness signal."""
    t, _, _, _ = _telemetry()

    class Boom:
        def add(self, *_a, **_k):
            raise RuntimeError("instrument exploded")

    t._run_beats = Boom()
    t._beat_once()


def test_beat_loop_exits_promptly_when_stopped():
    t, _, _, _ = _telemetry()
    t._stop.set()
    t._beat_loop()


def test_end_run_stops_the_heartbeat_before_flushing():
    """The last export must not race a tick claiming the run is still alive."""
    t, _, _, shutdown = _telemetry()
    t.end_run("terminal", None)
    assert t._stop.is_set()
    assert shutdown["called"] is True





def _turn_recording(**kwargs):
    """Run one turn through the real ladder against a recording adapter."""
    fake = RecordingTelemetry()
    runner = ladder.AgentRunner(
        backend=FakeBackend(turn=lambda *a, **k: "{}"),
        resilience=AgentResilience(),
        clock=FakeClock(),
    )
    with installed(fake):
        runner.turn("p", "plan_qa", None, timeout=750, **kwargs)
    return fake


def test_a_scaled_budget_records_the_scale_and_the_number_it_scaled():
    """`timeout_s` alone cannot say *why* a node had the budget it had."""
    fake = _turn_recording(budget_scale=2.5, base_timeout_s=300)

    scaled = [attrs for name, _, attrs in fake.events if name == "budget_scaled"]

    assert len(scaled) == 1
    assert scaled[0]["scale"] == 2.5
    assert scaled[0]["base_timeout_s"] == 300


def test_an_unscaled_turn_publishes_no_budget_event():
    """Silent at 1.0, so the event's presence is itself the signal."""
    fake = _turn_recording()

    assert [name for name, _, _ in fake.events if name == "budget_scaled"] == []


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
