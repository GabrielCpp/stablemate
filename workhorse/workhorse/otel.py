"""OpenTelemetry instrumentation for workhorse — on when a collector is there."""

from __future__ import annotations

import functools
import os
import socket
import sys
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, ParamSpec, Protocol, TypeVar
from urllib.parse import urlparse

if TYPE_CHECKING:
    from workhorse.records import NodeEvent
    from workhorse.runner.usage import TurnUsage


def _tristate(raw: str | None) -> bool | None:
    """Parse a force-on / force-off / auto env var."""
    value = (raw or "").strip().lower()
    if not value:
        return None
    return value not in ("0", "false", "no")


def _seconds(environ: Mapping[str, str], name: str, default: float) -> float:
    """A seconds-valued knob, or ``default`` when unset."""
    return float(environ.get(name, "").strip() or default)


def _metric_export_every_s(environ: Mapping[str, str], heartbeat_every_s: float) -> float:
    """Seconds between metric exports: our knob, then the SDK's, then the heartbeat."""
    for name, scale in (("WORKHORSE_OTEL_METRIC_EXPORT_S", 1.0),
                        ("OTEL_METRIC_EXPORT_INTERVAL", 0.001)):
        raw = environ.get(name, "").strip()
        if not raw:
            continue
        try:
            value = float(raw) * scale
        except ValueError:
            continue
        if value > 0:
            return value
    return heartbeat_every_s


@dataclass(frozen=True, slots=True)
class _LiveWait:
    started: float
    attributes: dict[str, str]


@dataclass(frozen=True, slots=True)
class OtelSettings:
    """Everything telemetry reads from the environment — read once, at the edge."""

    forced: bool | None = None
    endpoint: str = "http://127.0.0.1:8787"
    probe_timeout_s: float = 0.25
    heartbeat_every_s: float = 10.0
    metric_export_every_s: float = 10.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> OtelSettings:
        """The one place any of these names is read."""
        default = cls()
        heartbeat = _seconds(
            environ, "WORKHORSE_OTEL_HEARTBEAT_S", default.heartbeat_every_s
        )
        return cls(
            forced=_tristate(environ.get("WORKHORSE_OTEL")),
            endpoint=(
                environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or default.endpoint
            ).rstrip("/"),
            probe_timeout_s=_seconds(
                environ, "WORKHORSE_OTEL_PROBE_S", default.probe_timeout_s
            ),
            heartbeat_every_s=heartbeat,
            metric_export_every_s=_metric_export_every_s(environ, heartbeat),
        )


_TEST_ARGV0 = ("test_", "conftest.py")


def _under_test() -> bool:
    """Is this process a test run rather than a real one?"""
    if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
        return True
    argv0 = os.path.basename(sys.argv[0] or "")
    return argv0.startswith(_TEST_ARGV0[0]) or argv0 == _TEST_ARGV0[1]


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _failsoft(fallback: _R) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Make a telemetry method degrade to `fallback` instead of raising."""

    def decorate(fn: Callable[_P, _R]) -> Callable[_P, _R]:
        @functools.wraps(fn)
        def guarded(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            try:
                return fn(*args, **kwargs)
            except Exception:
                return fallback

        return guarded

    return decorate


_NO_OPEN_NODE = str()
_NO_WAIT_TOKEN = int()
_NO_OPEN_DEPTH = int()
_NO_REPOSITORY: dict[str, str] = {}

CONTROL_UNWIND_MARKER = "workhorse_control_unwind"


def _is_control_unwind(error: BaseException) -> bool:
    """Is this raise a control signal rather than a failure?"""
    return getattr(error, CONTROL_UNWIND_MARKER, False) is True


RepositoryProbe = Callable[[str | None, tuple[str, ...], bool], Mapping[str, str]]
HeadProbe = Callable[[bool], str]


def _no_repository(
    cwd: str | None, add_dirs: tuple[str, ...], refresh: bool
) -> Mapping[str, str]:  # noqa: ARG001 — the null probe ignores its scope
    return {}


_repository_probe: RepositoryProbe = _no_repository


def set_repository_probe(probe: RepositoryProbe | None) -> None:
    """Point span stamping at a scoped directory observer, or restore the no-op."""
    global _repository_probe
    _repository_probe = probe or _no_repository


def set_head_probe(probe: HeadProbe | None) -> None:
    """Compatibility adapter for callers that only observe one HEAD."""
    if probe is None:
        set_repository_probe(None)
        return

    def repository(
        cwd: str | None, add_dirs: tuple[str, ...], refresh: bool
    ) -> Mapping[str, str]:  # noqa: ARG001 — a head-only probe has no directory scope
        head = probe(refresh)
        return {"git.head": head} if head else {}

    set_repository_probe(repository)


def _repository_attrs(
    cwd: str | None = None,
    add_dirs: tuple[str, ...] = (),
    *,
    refresh: bool = False,
) -> dict[str, str]:
    """One fail-soft immutable observation of an execution's directory scope."""
    try:
        return dict(_repository_probe(cwd, add_dirs, refresh))
    except Exception:
        return {}


def _span_repository_attrs(snapshot: Mapping[str, str], phase: str) -> dict[str, str]:
    """Suffix one snapshot's fields for a span boundary."""
    return {f"{key}.{phase}": value for key, value in snapshot.items()}


class Telemetry(Protocol):
    """What the instrumentation sites may ask of telemetry."""

    def enabled(self) -> bool: ...
    def record_event(self, event: NodeEvent) -> None: ...
    def run_attribute(self, name: str, value: str) -> None: ...
    def state_start(self, state: str, seq: int) -> None: ...
    def state_end(
        self, state: str, seq: int, next_state: str | None = None, cut: str = ""
    ) -> None: ...
    def wait_start(
        self,
        kind: str,
        node_id: str,
        gate_path: str = "",
        gate_question: str = "",
    ) -> int: ...
    def wait_end(self, token: int, outcome: str = "completed") -> None: ...
    def gas_level(self, gas: int, capacity: int) -> None: ...
    def gas_refuel(self, node_id: str) -> None: ...
    def turn_start(
        self,
        node_id: str,
        model: str | None,
        effort: str | None,
        timeout: float,
        backend: str | None = None,
        cwd: str | None = None,
        add_dirs: tuple[str, ...] = (),
    ) -> None: ...
    def turn_end(
        self, error: str | None = None, error_class: str = "", error_kind: str = ""
    ) -> None: ...
    def turn_result(self, usage: TurnUsage) -> None: ...
    def set_labels(self, labels: dict[str, str]) -> None: ...
    def turn_session(self, session_id: str) -> None: ...
    def turn_event(self, name: str, error: bool, attrs: dict[str, Any]) -> None: ...
    def heartbeat(self, node_id: str, remaining_s: float) -> None: ...
    def turn_heartbeat(self, node_id: str, idle_s: float, elapsed_s: float) -> None: ...
    def current_node(self) -> str: ...
    def current_repository(self) -> dict[str, str]: ...
    def open_depth(self) -> int: ...
    def unwind_to(self, depth: int, error: BaseException) -> None: ...
    def end_run(
        self,
        status: str,
        error: str | None = None,
        error_class: str = "",
        error_kind: str = "",
    ) -> None: ...


class _NullTelemetry:
    """Telemetry that is off: every call is a near-zero-cost no-op."""

    def enabled(self) -> bool:
        return False

    def record_event(self, event: NodeEvent) -> None: ...
    def run_attribute(self, name: str, value: str) -> None: ...
    def state_start(self, state: str, seq: int) -> None: ...
    def state_end(
        self, state: str, seq: int, next_state: str | None = None, cut: str = ""
    ) -> None: ...
    def wait_start(
        self,
        kind: str,
        node_id: str,
        gate_path: str = "",
        gate_question: str = "",
    ) -> int:
        return 0
    def wait_end(self, token: int, outcome: str = "completed") -> None: ...
    def gas_level(self, gas: int, capacity: int) -> None: ...
    def gas_refuel(self, node_id: str) -> None: ...
    def turn_start(
        self,
        node_id: str,
        model: str | None,
        effort: str | None,
        timeout: float,
        backend: str | None = None,
        cwd: str | None = None,
        add_dirs: tuple[str, ...] = (),
    ) -> None: ...
    def turn_end(
        self, error: str | None = None, error_class: str = "", error_kind: str = ""
    ) -> None: ...
    def turn_result(self, usage: TurnUsage) -> None: ...
    def set_labels(self, labels: dict[str, str]) -> None: ...
    def turn_session(self, session_id: str) -> None: ...
    def turn_event(self, name: str, error: bool, attrs: dict[str, Any]) -> None: ...
    def heartbeat(self, node_id: str, remaining_s: float) -> None: ...
    def turn_heartbeat(self, node_id: str, idle_s: float, elapsed_s: float) -> None: ...

    def current_node(self) -> str:
        return ""

    def current_repository(self) -> dict[str, str]:
        return {}

    def open_depth(self) -> int:
        return 0

    def unwind_to(self, depth: int, error: BaseException) -> None: ...

    def end_run(
        self,
        status: str,
        error: str | None = None,
        error_class: str = "",
        error_kind: str = "",
    ) -> None: ...


_NULL: Telemetry = _NullTelemetry()


def _collector_reachable(endpoint: str, timeout_s: float) -> bool:
    """True when something accepts a TCP connection at ``endpoint``."""
    try:
        parsed = urlparse(endpoint)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout_s):
            return True
    except Exception:
        return False


class CollectorProbe(Protocol):
    """Is anything listening at ``endpoint``?"""

    def __call__(self, endpoint: str, timeout_s: float) -> bool: ...


class TelemetryFactory(Protocol):
    """Build the run's telemetry, or return None when the optional SDK is absent."""

    def __call__(
        self,
        workflow: str,
        run_id: str,
        run_dir: str | None,
        settings: OtelSettings,
    ) -> Telemetry | None: ...


_GENERATION_FILE = "resume_generation"


def _resume_generation(run_dir: str | None) -> int:
    """Read-increment-write this run directory's start counter, and return the new value."""
    if not run_dir:
        return 0
    path = Path(run_dir) / _GENERATION_FILE
    try:
        previous = int(path.read_text().strip())
    except (OSError, ValueError):
        previous = 0
    generation = previous + 1
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{generation}\n")
    except OSError:
        return previous
    return generation


def _build_logs(resource: Any, endpoint: str) -> Any:
    """The OTLP log pipeline, or None if this SDK build can't provide one."""
    try:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    except ImportError:
        print(
            "[workhorse] ⚠ OTel logs API unavailable in this SDK build; "
            "spans and metrics still export, logs stay console-only",
            file=sys.stderr,
        )
        return None
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{endpoint}/v1/logs"))
    )
    return provider


def _build(
    workflow: str, run_id: str, run_dir: str | None, settings: OtelSettings
) -> _Telemetry | None:
    try:
        from opentelemetry import trace as trace_api
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        if settings.forced is not None:
            print(
                "[workhorse] ⚠ WORKHORSE_OTEL is set but the OTel SDK is not installed; "
                "telemetry disabled. Install it with: pip install 'workhorse-agent[otel]'",
                file=sys.stderr,
            )
        return None

    resource = Resource.create(
        {
            "service.name": "workhorse",
            "run_id": run_id,
            "workflow": workflow,
            "repo": os.environ.get("REPO_NAME", ""),
            "branch": os.environ.get("REPO_BRANCH", ""),
            "run_dir": run_dir or "",
            "process.pid": os.getpid(),
            "workspace": os.environ.get("AGENT_REPO_DIR") or os.getcwd(),
            "workhorse.resume_generation": _resume_generation(run_dir),
        }
    )
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{settings.endpoint}/v1/traces"))
    )
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{settings.endpoint}/v1/metrics"),
        export_interval_millis=settings.metric_export_every_s * 1000.0,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    logger_provider = _build_logs(resource, settings.endpoint)

    def _shutdown() -> None:
        tracer_provider.shutdown()
        meter_provider.shutdown()
        if logger_provider is not None:
            logger_provider.shutdown()

    telemetry = _Telemetry(
        trace_api,
        tracer_provider.get_tracer("workhorse"),
        meter_provider.get_meter("workhorse"),
        _shutdown,
        settings.heartbeat_every_s,
    )
    telemetry.start_root(workflow)
    telemetry.start_heartbeat()
    from workhorse import logsetup

    logsetup.attach_otel(logger_provider)
    return telemetry


@dataclass(slots=True)
class TelemetryHost:
    """The run's telemetry, and the three decisions that select it."""

    settings: OtelSettings = field(default_factory=OtelSettings)
    probe: CollectorProbe = _collector_reachable
    build: TelemetryFactory = _build
    under_test: Callable[[], bool] = _under_test
    active: Telemetry = _NULL

    def start_run(self, workflow: str, run_id: str, run_dir: str | None = None) -> None:
        """Configure the SDK and open the run's root span."""
        if self.active.enabled() or self.settings.forced is False:
            return
        if self.settings.forced is None and (
            self.under_test()
            or not self.probe(self.settings.endpoint, self.settings.probe_timeout_s)
        ):
            return
        try:
            self.active = (
                self.build(workflow, run_id, run_dir, self.settings) or _NULL
            )
        except Exception as exc:
            print(
                f"[workhorse] ⚠ OTel setup failed ({exc}); telemetry disabled",
                file=sys.stderr,
            )
            self.active = _NULL

    def end_run(
        self,
        status: str,
        error: str | None = None,
        error_class: str = "",
        error_kind: str = "",
    ) -> None:
        """Close every open span (root last), flush, and shut the SDK down."""
        telemetry, self.active = self.active, _NULL
        if not telemetry.enabled():
            return
        try:
            from workhorse import logsetup

            logsetup.detach_otel()
        except Exception:
            pass
        telemetry.end_run(status, error, error_class, error_kind)


_host = TelemetryHost()


def install(host: TelemetryHost) -> TelemetryHost:
    """Make ``host`` the one the module-level functions below delegate to, and return the previous one so a caller can put it back."""
    global _host
    previous, _host = _host, host
    return previous


def enabled() -> bool:
    """Whether the active telemetry actually exports anything."""
    return _host.active.enabled()


def start_run(workflow: str, run_id: str, run_dir: str | None = None) -> None:
    """Open the installed host's run."""
    _host.start_run(workflow, run_id, run_dir)


def end_run(
    status: str, error: str | None = None, error_class: str = "", error_kind: str = ""
) -> None:
    """Close the installed host's run."""
    _host.end_run(status, error, error_class, error_kind)


def record_event(event: NodeEvent) -> None:
    """Mirror one ArtifactWriter event-log record (enter/done/terminal) into node spans."""
    _host.active.record_event(event)


def run_attribute(name: str, value: str) -> None:
    """Stamp a run-level fact on the root span."""
    _host.active.run_attribute(name, value)


def state_start(state: str, seq: int) -> None:
    """Open the span for one state-body execution."""
    _host.active.state_start(state, seq)


def state_end(state: str, seq: int, next_state: str | None = None, cut: str = "") -> None:
    """Close a state-body execution — successfully returned, or ``cut`` short."""
    _host.active.state_end(state, seq, next_state, cut)


@contextmanager
def scope() -> Iterator[None]:
    """Close, in this body's own `finally`, every span the body leaves open."""
    depth = _host.active.open_depth()
    try:
        yield
    except BaseException as exc:
        _host.active.unwind_to(depth, exc)
        raise


@contextmanager
def wait(
    kind: str,
    node_id: str,
    gate_path: str = "",
    gate_question: str = "",
) -> Iterator[None]:
    """Bracket an actual engine-controlled wait with a completed duration span."""
    token = _host.active.wait_start(kind, node_id, gate_path, gate_question)
    try:
        yield
    except BaseException:
        _host.active.wait_end(token, "interrupted")
        raise
    else:
        _host.active.wait_end(token)


def gas_level(gas: int, capacity: int) -> None:
    _host.active.gas_level(gas, capacity)


def gas_refuel(node_id: str) -> None:
    _host.active.gas_refuel(node_id)


def turn_start(
    node_id: str,
    model: str | None,
    effort: str | None,
    timeout: float,
    backend: str | None = None,
    cwd: str | None = None,
    add_dirs: tuple[str, ...] = (),
) -> None:
    _host.active.turn_start(node_id, model, effort, timeout, backend, cwd, add_dirs)


def turn_end(error: str | None = None, error_class: str = "", error_kind: str = "") -> None:
    _host.active.turn_end(error, error_class, error_kind)


def turn_result(usage: TurnUsage) -> None:
    """Attach a turn's duration + token usage to the open agent-turn span."""
    _host.active.turn_result(usage)


def set_labels(labels: dict[str, str]) -> None:
    """Set the workflow-declared dimensions (`labels:`) stamped on later spans."""
    _host.active.set_labels(labels)


def turn_session(session_id: str) -> None:
    """Tag the open agent-turn span with the backend CLI's session id, so a node's span leads back to that session's transcript (``opencode export <id>`` and equivalents) — the agent's reasoning/tool trace, which the node's ``prompt.md`` / ``output.json`` do not carry."""
    _host.active.turn_session(session_id)


def turn_event(name: str, *, error: bool = False, **attrs: Any) -> None:
    """Record a recovery-ladder event (retry/reframe/compact/cap_wait/ watchdog_kill) on the open turn span, falling back to the node span."""
    _host.active.turn_event(name, error, attrs)


def heartbeat(node_id: str, remaining_s: float) -> None:
    """One cap-wait tick: proof the run is alive inside a legitimate multi-hour spending-cap sleep (silence, by contrast, means a hang)."""
    _host.active.heartbeat(node_id, remaining_s)


def turn_heartbeat(node_id: str, idle_s: float, elapsed_s: float) -> None:
    """One liveness tick for the agent turn currently streaming."""
    _host.active.turn_heartbeat(node_id, idle_s, elapsed_s)


def current_node() -> str:
    """The node the run is currently inside, or "" — for tagging log records."""
    return _host.active.current_node()


def current_repository() -> dict[str, str]:
    """The immutable repository snapshot captured by the innermost active span."""
    return _host.active.current_repository()


class _Telemetry:
    """The per-run span/metric state behind the module-level facade."""

    def __init__(
        self,
        trace_api: Any,
        tracer: Any,
        meter: Any,
        shutdown: Any,
        heartbeat_every_s: float,
    ) -> None:
        self._trace = trace_api
        self._tracer = tracer
        self._shutdown = shutdown
        self._heartbeat_every_s = heartbeat_every_s
        self._lock = threading.RLock()
        self._root: Any = None
        self._root_repository: tuple[
            str | None, tuple[str, ...], dict[str, str]
        ] | None = None
        self._ended = False
        self._error_reported = False
        self._stack: list[tuple[tuple[str, str, int], Any, float]] = []
        self._span_repositories: dict[
            int, tuple[str | None, tuple[str, ...], dict[str, str]]
        ] = {}
        self._wait_seq = 0
        self._wait_keys: dict[int, tuple[str, str, int]] = {}
        self._wait_live: dict[int, _LiveWait] = {}
        self._turn: Any = None
        self._turn_repository: tuple[
            str | None, tuple[str, ...], dict[str, str]
        ] | None = None
        self._turn_started: float | None = None
        self._turn_node = ""
        self._turn_has_duration = False
        self._labels: dict[str, str] = {}
        self._stop = threading.Event()
        self._beat_thread: threading.Thread | None = None
        try:
            self._gas = meter.create_gauge(
                "workhorse.gas", description="Gas remaining in the progress-metered tank"
            )
            self._gas_capacity = meter.create_gauge(
                "workhorse.gas.capacity", description="Configured gas tank capacity"
            )
            self._refuels = meter.create_counter(
                "workhorse.gas.refuels", description="Tank refills on forward progress"
            )
            self._heartbeats = meter.create_counter(
                "workhorse.cap_wait.heartbeat",
                description="Cap-wait liveness ticks (a heartbeating run is not hung)",
            )
            self._cap_remaining = meter.create_gauge(
                "workhorse.cap_wait.remaining_s",
                description="Seconds left in the current cap-wait sleep",
            )
            self._node_active = meter.create_gauge(
                "workhorse.node.active",
                description="1 while a node visit is open, 0 once it completes",
            )
            self._wait_active = meter.create_gauge(
                "workhorse.wait.active",
                description="1 while an explicit runtime wait is open, 0 once it closes",
            )
            self._wait_elapsed = meter.create_gauge(
                "workhorse.wait.elapsed_s",
                description="Seconds the current explicit runtime wait has been open",
            )
            self._turn_beats = meter.create_counter(
                "workhorse.turn.heartbeat",
                description="Agent-turn liveness ticks (a streaming turn is not hung)",
            )
            self._turn_active = meter.create_gauge(
                "workhorse.turn.active",
                description="1 while an agent turn is open, 0 once it closes",
            )
            self._turn_idle = meter.create_gauge(
                "workhorse.turn.idle_s",
                description="Seconds since the streaming agent last emitted a line",
            )
            self._turn_elapsed = meter.create_gauge(
                "workhorse.turn.elapsed_s",
                description="Seconds the current agent turn has been running",
            )
            self._run_beats = meter.create_counter(
                "workhorse.run.heartbeat",
                description="Run-process liveness ticks, emitted for any node type",
            )
            self._node_elapsed = meter.create_gauge(
                "workhorse.node.elapsed_s",
                description="Seconds the currently open node visit has been running",
            )
        except Exception:
            self._gas = self._gas_capacity = self._refuels = None
            self._heartbeats = self._cap_remaining = None
            self._node_active = None
            self._wait_active = self._wait_elapsed = None
            self._turn_beats = self._turn_active = None
            self._turn_idle = self._turn_elapsed = None
            self._run_beats = self._node_elapsed = None

    def enabled(self) -> bool:
        """True: an SDK was built, so these calls really export something."""
        return True

    def start_root(self, workflow: str) -> None:
        with self._lock:
            snapshot = _repository_attrs(refresh=True)
            self._root = self._tracer.start_span(
                f"run:{workflow}",
                attributes=_span_repository_attrs(snapshot, "start"),
            )
            self._root_repository = (None, (), snapshot)

    @_failsoft(None)
    def run_attribute(self, name: str, value: str) -> None:
        """Stamp one run-level fact on the root span."""
        with self._lock:
            if self._root is not None:
                self._root.set_attribute(name, value)

    def start_heartbeat(self) -> None:
        """Begin proving the run's process is alive, independent of node type."""
        if self._run_beats is None:
            return
        self._beat_thread = threading.Thread(
            target=self._beat_loop, name="workhorse-otel-heartbeat", daemon=True
        )
        self._beat_thread.start()

    def _beat_loop(self) -> None:
        while not self._stop.wait(self._heartbeat_every_s):
            self._beat_once()

    def _live_attrs(self, node_id: str) -> dict[str, str]:
        """Metric attributes for the live "where is it now" signals: the node plus the run's current *activity* and *work_id*."""
        attrs: dict[str, str] = {"node": node_id}
        labels = self._labels
        for key in ("wf.activity", "wf.work_id", "activity", "work_id"):
            value = labels.get(key)
            if value:
                attrs[key] = value
        return attrs

    @_failsoft(None)
    def _beat_once(self) -> None:
        """Repeat active state so a collector can join after the opening edge."""
        with self._lock:
            top = self._stack[-1] if self._stack else None
            wait = next(reversed(self._wait_live.values()), None)
            node = top[0][1] if top else ""
            attrs = self._live_attrs(node)
            if self._run_beats is not None:
                self._run_beats.add(1, attrs)
            if top is not None and self._node_active is not None:
                self._node_active.set(1, attrs)
            if top is not None and self._node_elapsed is not None:
                self._node_elapsed.set(time.monotonic() - top[2], attrs)
            if wait is not None and self._wait_active is not None:
                self._wait_active.set(1, wait.attributes)
            if wait is not None and self._wait_elapsed is not None:
                self._wait_elapsed.set(
                    time.monotonic() - wait.started,
                    wait.attributes,
                )

    def _parent_ctx(self) -> Any:
        parent = self._stack[-1][1] if self._stack else self._root
        if parent is None:
            return None
        return self._trace.set_span_in_context(parent)

    @_failsoft(None)
    def record_event(self, event: NodeEvent) -> None:
        phase = event.phase
        node_id = event.node
        seq = event.seq
        extra = event.model_extra or {}
        if phase == "enter" and "waiting_on" in extra:
            return
        with self._lock:
            if phase == "enter":
                cwd = str(extra.get("repository_cwd") or "") or None
                raw_add_dirs = extra.get("repository_add_dirs") or []
                add_dirs = (
                    tuple(str(path) for path in raw_add_dirs)
                    if isinstance(raw_add_dirs, list)
                    else ()
                )
                self._start_execution(
                    ("node", node_id, seq),
                    node_id,
                    node_id,
                    {
                        **(
                            {"workhorse.span_kind": str(extra["span_kind"])}
                            if extra.get("span_kind")
                            else {}
                        )
                    },
                    cwd=cwd,
                    add_dirs=add_dirs,
                )
            elif phase == "done":
                self._end_execution(("node", node_id, seq), next_name=extra.get("next"))
                self._set_node_active(node_id, 0)
            elif phase == "error":
                target = self._stack[-1][1] if self._stack else self._root
                if target is not None:
                    target.add_event("error", {"error": str(extra.get("error") or "")})
            elif phase == "terminal":
                target = self._stack[-1][1] if self._stack else self._root
                if target is not None:
                    target.add_event(
                        "terminal", {"terminal": str(extra.get("terminal") or "")}
                    )

    @_failsoft(None)
    def state_start(self, state: str, seq: int) -> None:
        with self._lock:
            self._start_execution(
                ("state", state, seq),
                f"state:{state}",
                state,
                {"workhorse.span_kind": "state"},
            )

    @_failsoft(None)
    def state_end(
        self, state: str, seq: int, next_state: str | None = None, cut: str = ""
    ) -> None:
        with self._lock:
            self._end_execution(("state", state, seq), next_name=next_state, cut=cut)
            self._set_node_active(state, 0)

    @_failsoft(_NO_WAIT_TOKEN)
    def wait_start(
        self,
        kind: str,
        node_id: str,
        gate_path: str = "",
        gate_question: str = "",
    ) -> int:
        with self._lock:
            self._wait_seq += 1
            token = self._wait_seq
            key = ("wait", node_id, token)
            self._wait_keys[token] = key
            started = time.monotonic()
            attrs = self._wait_attrs(node_id, kind, gate_path, gate_question)
            self._wait_live[token] = _LiveWait(started, attrs)
            self._start_execution(
                key,
                f"wait:{kind}",
                node_id,
                {
                    "workhorse.span_kind": "wait",
                    "workhorse.wait_kind": kind,
                    "workhorse.gate_path": gate_path,
                    "workhorse.gate_question": gate_question,
                },
                mark_active=False,
            )
            if self._wait_active is not None:
                self._wait_active.set(1, attrs)
            if self._wait_elapsed is not None:
                self._wait_elapsed.set(0.0, attrs)
            return token

    @_failsoft(None)
    def wait_end(self, token: int, outcome: str = "completed") -> None:
        with self._lock:
            key = self._wait_keys.pop(token, None)
            live = self._wait_live.pop(token, None)
            if key is None:
                return
            self._end_execution(
                key,
                next_name=None,
                end_attributes={"workhorse.wait_outcome": outcome},
            )
            if live is not None:
                if self._wait_elapsed is not None:
                    self._wait_elapsed.set(time.monotonic() - live.started, live.attributes)
                if self._wait_active is not None:
                    self._wait_active.set(0, live.attributes)

    def _wait_attrs(
        self,
        node_id: str,
        kind: str,
        gate_path: str = "",
        gate_question: str = "",
    ) -> dict[str, str]:
        attrs = {**self._live_attrs(node_id), "wait_kind": kind}
        if gate_path:
            attrs["gate_path"] = gate_path
        if gate_question:
            attrs["gate_question"] = gate_question
        return attrs

    def _start_execution(
        self,
        key: tuple[str, str, int],
        span_name: str,
        node_id: str,
        attributes: dict[str, Any],
        *,
        mark_active: bool = True,
        cwd: str | None = None,
        add_dirs: tuple[str, ...] = (),
    ) -> None:
        snapshot = _repository_attrs(cwd, add_dirs)
        span = self._tracer.start_span(
            span_name,
            context=self._parent_ctx(),
            attributes={
                "workhorse.node": node_id,
                "workhorse.seq": key[2],
                "workhorse.depth": len(self._stack),
                **_span_repository_attrs(snapshot, "start"),
                **attributes,
                **self._labels,
            },
        )
        self._stack.append((key, span, time.monotonic()))
        self._span_repositories[id(span)] = (cwd, add_dirs, snapshot)
        if mark_active:
            self._set_node_active(node_id, 1)

    def _end_execution(
        self,
        key: tuple[str, str, int],
        next_name: Any,
        end_attributes: dict[str, Any] | None = None,
        cut: str = "",
    ) -> None:
        """End the span for ``key``, sweeping anything left open above it."""
        if all(k != key for k, _, _ in self._stack):
            return
        while self._stack:
            stack_key, span, _ = self._stack.pop()
            cwd, add_dirs, _ = self._span_repositories.pop(id(span), (None, (), {}))
            end_snapshot = _repository_attrs(cwd, add_dirs, refresh=True)
            for name, value in _span_repository_attrs(end_snapshot, "end").items():
                span.set_attribute(name, value)
            if cut:
                span.set_attribute("workhorse.cut", cut)
            if stack_key == key:
                if next_name:
                    span.set_attribute("workhorse.next", str(next_name))
                for name, value in (end_attributes or {}).items():
                    span.set_attribute(name, value)
                span.end()
                return
            span.end()

    @_failsoft(_NO_OPEN_NODE)
    def current_node(self) -> str:
        """The innermost open node visit, or "" — what stamps a log record."""
        with self._lock:
            return self._stack[-1][0][1] if self._stack else ""

    @_failsoft(_NO_REPOSITORY)
    def current_repository(self) -> dict[str, str]:
        """The innermost span's immutable start snapshot for log attribution."""
        with self._lock:
            if self._turn_repository is not None:
                return dict(self._turn_repository[2])
            if self._stack:
                snapshot = self._span_repositories.get(id(self._stack[-1][1]))
                if snapshot is not None:
                    return dict(snapshot[2])
            if self._root_repository is not None:
                return dict(self._root_repository[2])
            return {}

    @_failsoft(_NO_OPEN_DEPTH)
    def open_depth(self) -> int:
        """How many execution spans are open — the mark a `scope()` unwinds back to."""
        with self._lock:
            return len(self._stack)

    @_failsoft(None)
    def unwind_to(self, depth: int, error: BaseException) -> None:
        """Close every span opened above ``depth`` because the body raised."""
        control = _is_control_unwind(error)
        with self._lock:
            innermost = True
            while len(self._stack) > depth:
                _, span, _ = self._stack.pop()
                cwd, add_dirs, _ = self._span_repositories.pop(id(span), (None, (), {}))
                end_snapshot = _repository_attrs(cwd, add_dirs, refresh=True)
                for name, value in _span_repository_attrs(end_snapshot, "end").items():
                    span.set_attribute(name, value)
                span.set_attribute(
                    "workhorse.outcome", "control" if control else "error"
                )
                if control:
                    span.set_attribute("workhorse.control", type(error).__name__)
                elif innermost and not self._error_reported:
                    self._error_reported = True
                    span.set_attribute("error.class", type(error).__name__)
                    span.set_status(
                        self._trace.Status(self._trace.StatusCode.ERROR, str(error))
                    )
                innermost = False
                span.end()

    @_failsoft(None)
    def end_run(
        self,
        status: str,
        error: str | None = None,
        error_class: str = "",
        error_kind: str = "",
    ) -> None:
        with self._lock:
            if self._ended:
                return
            self._ended = True
        self._stop.set()
        if self._beat_thread is not None:
            self._beat_thread.join(timeout=2)
            self._beat_thread = None
        failed = status in {"fail", "aborted"} and error is not None
        with self._lock:
            for token in list(self._wait_live):
                self.wait_end(token, "interrupted")
            self.turn_end(error if failed else None)
            while self._stack:
                _, span, _ = self._stack.pop()
                span.set_attribute("workhorse.outcome", "abandoned")
                cwd, add_dirs, _ = self._span_repositories.pop(id(span), (None, (), {}))
                end_snapshot = _repository_attrs(cwd, add_dirs, refresh=True)
                for name, value in _span_repository_attrs(end_snapshot, "end").items():
                    span.set_attribute(name, value)
                span.end()
            if self._root is not None:
                self._root.set_attribute("workhorse.terminal", status)
                cwd, add_dirs, _ = self._root_repository or (None, (), {})
                end_snapshot = _repository_attrs(cwd, add_dirs, refresh=True)
                for name, value in _span_repository_attrs(end_snapshot, "end").items():
                    self._root.set_attribute(name, value)
                if error_class:
                    self._root.set_attribute("error.class", error_class)
                if error_kind:
                    self._root.set_attribute("error.kind", error_kind)
                if failed and not self._error_reported:
                    self._error_reported = True
                    self._root.set_status(
                        self._trace.Status(self._trace.StatusCode.ERROR, error)
                    )
                self._root.end()
                self._root = None
                self._root_repository = None
        self._shutdown()

    @_failsoft(None)
    def turn_start(
        self,
        node_id: str,
        model: str | None,
        effort: str | None,
        timeout: float,
        backend: str | None = None,
        cwd: str | None = None,
        add_dirs: tuple[str, ...] = (),
    ) -> None:
        with self._lock:
            if self._turn is not None:
                self.turn_end()
            self._turn_started = time.monotonic()
            self._turn_node = node_id
            self._turn_has_duration = False
            snapshot = _repository_attrs(cwd, add_dirs)
            self._turn = self._tracer.start_span(
                "agent_turn",
                context=self._parent_ctx(),
                attributes={
                    "workhorse.node": node_id,
                    "backend": backend or "",
                    "model": model or "",
                    "effort": effort or "",
                    "timeout_s": -1 if timeout == float("inf") else int(timeout),
                    **_span_repository_attrs(snapshot, "start"),
                    **self._labels,
                },
            )
            self._turn_repository = (cwd, add_dirs, snapshot)
            attrs = self._live_attrs(node_id)
            if self._turn_active is not None:
                self._turn_active.set(1, attrs)
            if self._turn_idle is not None:
                self._turn_idle.set(0.0, attrs)
            if self._turn_elapsed is not None:
                self._turn_elapsed.set(0.0, attrs)

    @_failsoft(None)
    def turn_end(
        self, error: str | None = None, error_class: str = "", error_kind: str = ""
    ) -> None:
        with self._lock:
            turn, self._turn = self._turn, None
            node_id, self._turn_node = self._turn_node, ""
            repository, self._turn_repository = self._turn_repository, None
            if turn is None:
                return
            if not self._turn_has_duration and self._turn_started is not None:
                turn.set_attribute(
                    "duration_ms", int((time.monotonic() - self._turn_started) * 1000)
                )
            self._turn_started = None
            cwd, add_dirs, _ = repository or (None, (), {})
            end_snapshot = _repository_attrs(cwd, add_dirs, refresh=True)
            for name, value in _span_repository_attrs(end_snapshot, "end").items():
                turn.set_attribute(name, value)
            if error:
                if error_class:
                    turn.set_attribute("error.class", error_class)
                if error_kind:
                    turn.set_attribute("error.kind", error_kind)
                turn.set_status(self._trace.Status(self._trace.StatusCode.ERROR, error))
            turn.end()
            attrs = self._live_attrs(node_id)
            if self._turn_active is not None:
                self._turn_active.set(0, attrs)
            if self._turn_idle is not None:
                self._turn_idle.set(0.0, attrs)
            if self._turn_elapsed is not None:
                self._turn_elapsed.set(0.0, attrs)

    @_failsoft(None)
    def turn_result(self, usage: TurnUsage) -> None:
        with self._lock:
            turn = self._turn
            if turn is None:
                return
            if usage.duration_ms is not None:
                turn.set_attribute("duration_ms", int(usage.duration_ms))
                self._turn_has_duration = True
            for field, count in usage.token_counts().items():
                turn.set_attribute(f"usage.{field}", int(count))
            if usage.total_cost_usd is not None:
                turn.set_attribute("total_cost_usd", float(usage.total_cost_usd))

    @_failsoft(None)
    def set_labels(self, labels: dict[str, str]) -> None:
        """Replace the workflow-declared dimensions stamped on subsequent spans."""
        with self._lock:
            self._labels = dict(labels)

    @_failsoft(None)
    def turn_session(self, session_id: str) -> None:
        with self._lock:
            if self._turn is not None and session_id:
                self._turn.set_attribute("session.id", session_id)

    @_failsoft(None)
    def turn_event(self, name: str, error: bool, attrs: dict[str, Any]) -> None:
        with self._lock:
            target = self._turn or (self._stack[-1][1] if self._stack else self._root)
            if target is None:
                return
            target.add_event(name, {k: str(v) for k, v in attrs.items()})
            if error:
                target.set_status(self._trace.Status(self._trace.StatusCode.ERROR, name))

    @_failsoft(None)
    def gas_level(self, gas: int, capacity: int) -> None:
        if self._gas is not None and self._gas_capacity is not None:
            self._gas.set(gas)
            self._gas_capacity.set(capacity)

    @_failsoft(None)
    def gas_refuel(self, node_id: str) -> None:
        if self._refuels is not None:
            self._refuels.add(1, {"node": node_id})

    @_failsoft(None)
    def heartbeat(self, node_id: str, remaining_s: float) -> None:
        if self._heartbeats is not None and self._cap_remaining is not None:
            self._heartbeats.add(1, {"node": node_id})
            self._cap_remaining.set(max(0.0, remaining_s), {"node": node_id})

    def _set_node_active(self, node_id: str, value: int) -> None:
        if self._node_active is not None:
            self._node_active.set(value, self._live_attrs(node_id))

    @_failsoft(None)
    def turn_heartbeat(self, node_id: str, idle_s: float, elapsed_s: float) -> None:
        if (
            self._turn_beats is not None
            and self._turn_idle is not None
            and self._turn_elapsed is not None
        ):
            attrs = self._live_attrs(node_id)
            self._turn_beats.add(1, attrs)
            if self._turn_active is not None:
                self._turn_active.set(1, attrs)
            self._turn_idle.set(max(0.0, idle_s), attrs)
            self._turn_elapsed.set(max(0.0, elapsed_s), attrs)
