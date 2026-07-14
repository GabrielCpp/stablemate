"""Opt-in OpenTelemetry instrumentation for workhorse — no-op by default.

Enable by setting ``WORKHORSE_OTEL=1`` (plus ``OTEL_EXPORTER_OTLP_ENDPOINT``,
default ``http://127.0.0.1:8787`` — groom's collector) and installing the
``otel`` extra (``pip install 'workhorse-agent[otel]'``). With the env unset, or
the SDK absent, every function here is a near-zero-cost no-op — instrumentation
must never change how an unattended run behaves, let alone crash it, so every
public entry point also swallows its own exceptions.

The instrumentation sites call module-level functions rather than threading a
tracer object through the engine: there is exactly one run per process, so the
telemetry state is a module singleton (mirroring the ``AGENT_*`` /
``_configured_gas()`` env-at-import pattern). What gets emitted:

- a **root span** per run (started/ended by ``main.run``),
- a **node span** per node visit, driven by the ``ArtifactWriter._append_event``
  choke point every ``enter``/``done``/``terminal`` already funnels through —
  ``(node, seq)`` uniquely identifies a visit, and the engine's single-threaded
  recursive walk means visits nest strictly, so a plain span stack reproduces
  the flow nesting,
- an **agent-turn span** per CLI invocation with model/effort/timeout attrs and
  the result event's duration + token usage,
- **span events** for retry/reframe/compact/cap-wait/watchdog-kill (the watchdog
  fires on a daemon thread, hence the lock around all span-stack mutation),
- **metrics**: the gas gauge + refuel counter, and the cap-wait heartbeat that
  proves a multi-hour capped run is alive rather than hung.
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Any

# Read once at import (the AGENT_*/_configured_gas() module-constant pattern).
# WORKHORSE_OTEL gates everything; the endpoint defaults to groom's local port.
_OTEL_ENABLED = (os.environ.get("WORKHORSE_OTEL") or "").strip().lower() not in (
    "", "0", "false", "no",
)
_OTEL_ENDPOINT = (
    os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "http://127.0.0.1:8787"
).rstrip("/")

# The active per-run telemetry, or None (the no-op default). Set by start_run()
# when enabled, cleared by end_run(). Module-level because there is one run per
# process; tests construct _Telemetry directly with fakes instead.
_active: _Telemetry | None = None


def enabled() -> bool:
    return _active is not None


def start_run(workflow: str, run_id: str) -> None:
    """Configure the SDK and open the run's root span. No-op unless
    ``WORKHORSE_OTEL`` is set and the (optional) SDK is importable."""
    global _active
    if not _OTEL_ENABLED or _active is not None:
        return
    try:
        _active = _build(workflow, run_id)
    except Exception as exc:  # instrumentation must never break a run
        print(f"[workhorse] ⚠ OTel setup failed ({exc}); telemetry disabled", file=sys.stderr)
        _active = None


def end_run(status: str, error: str | None = None) -> None:
    """Close every open span (root last), flush, and shut the SDK down.
    Idempotent — the finally-backstop in ``main.run`` may call it again."""
    global _active
    telemetry, _active = _active, None
    if telemetry is None:
        return
    try:
        telemetry.end_run(status, error)
    except Exception:
        pass


def _call(method: str, *args: Any, **kwargs: Any) -> None:
    """Forward to the active telemetry, or do nothing. Exceptions are swallowed:
    a telemetry bug must degrade to 'no spans', never to a crashed run."""
    telemetry = _active
    if telemetry is None:
        return
    try:
        getattr(telemetry, method)(*args, **kwargs)
    except Exception:
        pass


def record_event(record: dict[str, Any]) -> None:
    """Mirror one ArtifactWriter event-log record (enter/done/terminal) into
    node spans. Called from ``ArtifactWriter._append_event``."""
    _call("record_event", record)


def gas_level(gas: int, capacity: int) -> None:
    _call("gas_level", gas, capacity)


def gas_refuel(node_id: str) -> None:
    _call("gas_refuel", node_id)


def turn_start(node_id: str, model: str | None, effort: str | None, timeout: float) -> None:
    _call("turn_start", node_id, model, effort, timeout)


def turn_end(error: str | None = None) -> None:
    _call("turn_end", error)


def turn_result(event: dict[str, Any]) -> None:
    """Attach the CLI result event's duration + token usage to the open turn."""
    _call("turn_result", event)


def turn_event(name: str, *, error: bool = False, **attrs: Any) -> None:
    """Record a recovery-ladder event (retry/reframe/compact/cap_wait/
    watchdog_kill) on the open turn span, falling back to the node span.
    Thread-safe: the watchdog calls this from its daemon timer thread."""
    _call("turn_event", name, error, attrs)


def heartbeat(node_id: str, remaining_s: float) -> None:
    """One cap-wait tick: proof the run is alive inside a legitimate multi-hour
    spending-cap sleep (silence, by contrast, means a hang)."""
    _call("heartbeat", node_id, remaining_s)


def _build(workflow: str, run_id: str) -> _Telemetry | None:
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
        }
    )
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{_OTEL_ENDPOINT}/v1/traces"))
    )
    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{_OTEL_ENDPOINT}/v1/metrics")
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])

    def _shutdown() -> None:
        tracer_provider.shutdown()
        meter_provider.shutdown()

    telemetry = _Telemetry(
        trace_api,
        tracer_provider.get_tracer("workhorse"),
        meter_provider.get_meter("workhorse"),
        _shutdown,
    )
    telemetry.start_root(workflow)
    return telemetry


class _Telemetry:
    """The per-run span/metric state behind the module-level facade.

    All mutation happens under one re-entrant lock: the engine's step loop is
    single-threaded, but the watchdog fires span events from a daemon timer
    thread, and end_run must be able to sweep whatever is open at that moment.
    """

    def __init__(self, trace_api: Any, tracer: Any, meter: Any, shutdown: Any) -> None:
        self._trace = trace_api
        self._tracer = tracer
        self._shutdown = shutdown
        self._lock = threading.RLock()
        self._root: Any = None
        # Open node spans, innermost last: [((node_id, seq), span), ...]. The
        # engine's walk nests strictly (a flow node's children open and close
        # while the flow node span is open), so a stack mirrors the tree.
        self._stack: list[tuple[tuple[str, int], Any]] = []
        self._turn: Any = None
        # Instruments are best-effort: an older SDK without sync gauges just
        # skips the gas metrics rather than disabling spans too.
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
        except Exception:
            self._gas = self._gas_capacity = self._refuels = None
            self._heartbeats = self._cap_remaining = None

    # ---- spans ---------------------------------------------------------- #
    def start_root(self, workflow: str) -> None:
        with self._lock:
            self._root = self._tracer.start_span(f"run:{workflow}")

    def _parent_ctx(self) -> Any:
        parent = self._stack[-1][1] if self._stack else self._root
        if parent is None:
            return None
        return self._trace.set_span_in_context(parent)

    def record_event(self, record: dict[str, Any]) -> None:
        phase = record.get("phase")
        node_id = str(record.get("node", ""))
        seq = int(record.get("seq") or 0)
        with self._lock:
            if phase == "enter":
                span = self._tracer.start_span(
                    node_id,
                    context=self._parent_ctx(),
                    attributes={
                        "workhorse.node": node_id,
                        "workhorse.seq": seq,
                        "workhorse.depth": len(self._stack),
                    },
                )
                self._stack.append(((node_id, seq), span))
            elif phase == "done":
                self._end_node((node_id, seq), next_node=record.get("next"))
            elif phase == "terminal":
                # A flow's finish() also emits a terminal (node "<run>") — the
                # stack scopes it to the enclosing flow-node span; the run's own
                # terminal (stack empty) lands on the root span.
                target = self._stack[-1][1] if self._stack else self._root
                if target is not None:
                    target.add_event(
                        "terminal", {"terminal": str(record.get("terminal") or "")}
                    )

    def _end_node(self, key: tuple[str, int], next_node: Any) -> None:
        """End the span for ``key``, sweeping (as errored) anything left open
        above it — a node that raised never gets a done event of its own."""
        if all(k != key for k, _ in self._stack):
            return
        while self._stack:
            stack_key, span = self._stack.pop()
            if stack_key == key:
                if next_node:
                    span.set_attribute("workhorse.next", str(next_node))
                span.end()
                return
            span.set_status(
                self._trace.Status(self._trace.StatusCode.ERROR, "never completed")
            )
            span.end()

    def end_run(self, status: str, error: str | None) -> None:
        with self._lock:
            self.turn_end(error)
            while self._stack:
                _, span = self._stack.pop()
                if error:
                    span.set_status(self._trace.Status(self._trace.StatusCode.ERROR, error))
                span.end()
            if self._root is not None:
                self._root.set_attribute("workhorse.terminal", status)
                if error:
                    self._root.set_status(
                        self._trace.Status(self._trace.StatusCode.ERROR, error)
                    )
                self._root.end()
                self._root = None
        self._shutdown()  # flushes the batch processor + metric reader

    # ---- agent turns ----------------------------------------------------- #
    def turn_start(
        self, node_id: str, model: str | None, effort: str | None, timeout: float
    ) -> None:
        with self._lock:
            if self._turn is not None:  # defensive: never leak an open turn
                self._turn.end()
            self._turn = self._tracer.start_span(
                "agent_turn",
                context=self._parent_ctx(),
                attributes={
                    "workhorse.node": node_id,
                    "model": model or "",
                    "effort": effort or "",
                    "timeout_s": -1 if timeout == float("inf") else int(timeout),
                },
            )

    def turn_end(self, error: str | None = None) -> None:
        with self._lock:
            turn, self._turn = self._turn, None
            if turn is None:
                return
            if error:
                turn.set_status(self._trace.Status(self._trace.StatusCode.ERROR, error))
            turn.end()

    def turn_result(self, event: dict[str, Any]) -> None:
        with self._lock:
            turn = self._turn
            if turn is None:
                return
            if event.get("duration_ms") is not None:
                turn.set_attribute("duration_ms", int(event["duration_ms"]))
            usage = event.get("usage") or {}
            for field in (
                "input_tokens",
                "output_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
            ):
                if usage.get(field) is not None:
                    turn.set_attribute(f"usage.{field}", int(usage[field]))
            if event.get("total_cost_usd") is not None:
                turn.set_attribute("total_cost_usd", float(event["total_cost_usd"]))

    def turn_event(self, name: str, error: bool, attrs: dict[str, Any]) -> None:
        with self._lock:
            target = self._turn or (self._stack[-1][1] if self._stack else self._root)
            if target is None:
                return
            target.add_event(name, {k: str(v) for k, v in attrs.items()})
            if error:
                target.set_status(self._trace.Status(self._trace.StatusCode.ERROR, name))

    # ---- metrics ---------------------------------------------------------- #
    def gas_level(self, gas: int, capacity: int) -> None:
        if self._gas is not None:
            self._gas.set(gas)
            self._gas_capacity.set(capacity)

    def gas_refuel(self, node_id: str) -> None:
        if self._refuels is not None:
            self._refuels.add(1, {"node": node_id})

    def heartbeat(self, node_id: str, remaining_s: float) -> None:
        if self._heartbeats is not None:
            self._heartbeats.add(1, {"node": node_id})
            self._cap_remaining.set(max(0.0, remaining_s), {"node": node_id})
