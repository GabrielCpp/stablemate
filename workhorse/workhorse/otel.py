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
- **metrics**: the gas gauge + refuel counter, the cap-wait heartbeat that
  proves a multi-hour capped run is alive rather than hung, and — the pair that
  makes a *live* run legible — the node-active gauge and the agent-turn
  heartbeat.
- **logs**: a ``LoggerProvider`` wired into the stdlib ``logging`` root by
  ``workhorse.logsetup``, so workhorse's own log records *and* those of the
  script nodes it now runs in-process (``runner/script.py``) reach the collector
  tagged with the same ``run_id``/``run_dir`` resource as the spans.

Why that last pair is metrics and not spans: a span only leaves the process when
it **ends** (``BatchSpanProcessor`` exports on ``on_end``), so the node you most
want to watch — the one that hangs and never ends — is precisely the one no
trace can show. Metrics ride a periodic reader instead, so they escape while the
node's span is still open. Hence the division of labour:

- ``workhorse.node.active`` answers **where** the run is (which node is open),
- ``workhorse.turn.heartbeat`` / ``.idle_s`` answer **whether it is alive** —
  a working turn keeps streaming (idle_s small), a wedged one goes quiet
  (idle_s climbs), a dead one stops heartbeating altogether.

The gauge alone cannot prove liveness: a synchronous gauge re-exports its last
value every cycle, so a stale ``active=1`` looks identical whether the run is
working or dead. Only something that *increments* separates the two.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any

# Read once at import (the AGENT_*/_configured_gas() module-constant pattern).
# WORKHORSE_OTEL gates everything; the endpoint defaults to groom's local port.
_OTEL_ENABLED = (os.environ.get("WORKHORSE_OTEL") or "").strip().lower() not in (
    "", "0", "false", "no",
)
_OTEL_ENDPOINT = (
    os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or "http://127.0.0.1:8787"
).rstrip("/")
# How often the background thread proves the run's process is alive. Script nodes are
# why this exists: they run as a buffered child (``SubprocessScriptRunner``), so they
# stream nothing a per-line heartbeat could hook, and a wedged one would otherwise be
# indistinguishable from a fast one until it returned.
_HEARTBEAT_EVERY_S = float(os.environ.get("WORKHORSE_OTEL_HEARTBEAT_S", "10"))

# The active per-run telemetry, or None (the no-op default). Set by start_run()
# when enabled, cleared by end_run(). Module-level because there is one run per
# process; tests construct _Telemetry directly with fakes instead.
_active: _Telemetry | None = None


def enabled() -> bool:
    return _active is not None


def start_run(workflow: str, run_id: str, run_dir: str | None = None) -> None:
    """Configure the SDK and open the run's root span. No-op unless
    ``WORKHORSE_OTEL`` is set and the (optional) SDK is importable."""
    global _active
    if not _OTEL_ENABLED or _active is not None:
        return
    try:
        _active = _build(workflow, run_id, run_dir)
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
        # Unhook logging before the provider below is shut down, so no late
        # record is handed to a dead exporter.
        from workhorse import logsetup

        logsetup.detach_otel()
    except Exception:
        pass
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


def turn_session(session_id: str) -> None:
    """Tag the open agent-turn span with the backend CLI's session id, so a
    node's span leads back to that session's transcript (``opencode export <id>``
    and equivalents) — the agent's reasoning/tool trace, which the node's
    ``prompt.md`` / ``output.json`` do not carry."""
    _call("turn_session", session_id)


def turn_event(name: str, *, error: bool = False, **attrs: Any) -> None:
    """Record a recovery-ladder event (retry/reframe/compact/cap_wait/
    watchdog_kill) on the open turn span, falling back to the node span.
    Thread-safe: the watchdog calls this from its daemon timer thread."""
    _call("turn_event", name, error, attrs)


def heartbeat(node_id: str, remaining_s: float) -> None:
    """One cap-wait tick: proof the run is alive inside a legitimate multi-hour
    spending-cap sleep (silence, by contrast, means a hang)."""
    _call("heartbeat", node_id, remaining_s)


def turn_heartbeat(node_id: str, idle_s: float, elapsed_s: float) -> None:
    """One liveness tick for the agent turn currently streaming.

    The cap-wait heartbeat above proves a *sleeping* run is alive; this proves a
    *working* one is, which spans structurally cannot: a span only leaves the
    process when it ends, so the one node you most want to see — the one that
    hangs — never exports. Metrics ride the periodic reader instead, so these
    escape while the turn's span is still open.

    ``idle_s`` (seconds since the agent last wrote a stream line) is the signal
    that separates the two ways a long turn looks identical from outside: a
    healthy turn streams, so idle_s stays small however long it runs; a wedged
    one goes quiet, so idle_s climbs. No heartbeat at all means the process is
    gone.
    """
    _call("turn_heartbeat", node_id, idle_s, elapsed_s)


def current_node() -> str:
    """The node the run is currently inside, or "" — for tagging log records.

    Workhorse opens node spans with ``start_span``, never ``start_as_current_span``,
    so nothing is in the OTel *context* and a log record would otherwise carry
    ``trace_id=0``: the SDK's LoggingHandler correlates via the ambient context,
    which this engine deliberately does not populate. Tagging the node explicitly
    is what makes ``groom logs --node`` work at all.
    """
    telemetry = _active
    if telemetry is None:
        return ""
    try:
        with telemetry._lock:
            stack = telemetry._stack
            return stack[-1][0][0] if stack else ""
    except Exception:
        return ""


def _build_logs(resource: Any) -> Any:
    """The OTLP log pipeline, or None if this SDK build can't provide one.

    Separate from ``_build`` and independently failure-tolerant because the logs
    SDK is the one leg of the three that still lives under private module paths
    (``sdk._logs``, ``..._log_exporter``) — there is no public ``sdk.logs``. An
    SDK upgrade that renames them must cost us logs only, not the traces and
    metrics that answer "where is the run" (see docs/workhorse-otel.md).
    """
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
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{_OTEL_ENDPOINT}/v1/logs"))
    )
    return provider


def _build(workflow: str, run_id: str, run_dir: str | None = None) -> _Telemetry | None:
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
            # The run's artifact directory: what turns a span into a filesystem
            # lookup (prompt.md / output.json / events.jsonl) in one hop, instead
            # of a manual join through the runs/ tree.
            "run_dir": run_dir or "",
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
    logger_provider = _build_logs(resource)

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
    )
    telemetry.start_root(workflow)
    telemetry.start_heartbeat()
    # Imported here, not at module scope: logsetup imports this module for
    # current_node(), so a top-level import would be circular.
    from workhorse import logsetup

    logsetup.attach_otel(logger_provider)
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
        # Open node spans, innermost last: [((node_id, seq), span, started_at), ...].
        # The engine's walk nests strictly (a flow node's children open and close
        # while the flow node span is open), so a stack mirrors the tree. The
        # monotonic start stamp feeds the node.elapsed_s gauge, which — unlike the
        # span's own duration — is readable *while* the node is still running.
        self._stack: list[tuple[tuple[str, int], Any, float]] = []
        self._turn: Any = None
        self._stop = threading.Event()
        self._beat_thread: threading.Thread | None = None
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
            self._node_active = meter.create_gauge(
                "workhorse.node.active",
                description="1 while a node visit is open, 0 once it completes",
            )
            self._turn_beats = meter.create_counter(
                "workhorse.turn.heartbeat",
                description="Agent-turn liveness ticks (a streaming turn is not hung)",
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
            self._turn_beats = self._turn_idle = self._turn_elapsed = None
            self._run_beats = self._node_elapsed = None

    # ---- spans ---------------------------------------------------------- #
    def start_root(self, workflow: str) -> None:
        with self._lock:
            self._root = self._tracer.start_span(f"run:{workflow}")

    def start_heartbeat(self) -> None:
        """Begin proving the run's process is alive, independent of node type.

        A daemon thread so it can never hold the interpreter open past a run, and
        so a node that blocks the main thread for an hour (a buffered script child,
        a cap sleep) keeps beating anyway — which is the entire point: the main
        thread being busy is exactly when the outside world most needs telling that
        busy is not the same as hung.
        """
        if self._run_beats is None:
            return
        self._beat_thread = threading.Thread(
            target=self._beat_loop, name="workhorse-otel-heartbeat", daemon=True
        )
        self._beat_thread.start()

    def _beat_loop(self) -> None:
        while not self._stop.wait(_HEARTBEAT_EVERY_S):
            self._beat_once()

    def _beat_once(self) -> None:
        """Emit one liveness tick for whatever node is open (or none)."""
        try:
            with self._lock:
                top = self._stack[-1] if self._stack else None
            node = top[0][0] if top else ""
            self._run_beats.add(1, {"node": node})
            if top is not None and self._node_elapsed is not None:
                self._node_elapsed.set(time.monotonic() - top[2], {"node": node})
        except Exception:
            # A telemetry bug must degrade to "no heartbeat", never take down the
            # thread (and with it every later liveness signal) mid-run.
            pass

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
                self._stack.append(((node_id, seq), span, time.monotonic()))
                # Metrics export on the periodic reader, independent of any span's
                # lifecycle — so unlike the span just opened above, this escapes the
                # process while the node is still running. It is what answers "where
                # is the run right now" without inferring it from the last completed
                # span's workhorse.next.
                self._set_node_active(node_id, 1)
            elif phase == "done":
                self._end_node((node_id, seq), next_node=record.get("next"))
                self._set_node_active(node_id, 0)
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
        if all(k != key for k, _, _ in self._stack):
            return
        while self._stack:
            stack_key, span, _ = self._stack.pop()
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
        # Stop beating before the flush below, so the last export cannot race a
        # tick that would claim the run is still alive after it ended.
        self._stop.set()
        if self._beat_thread is not None:
            self._beat_thread.join(timeout=2)
            self._beat_thread = None
        with self._lock:
            self.turn_end(error)
            while self._stack:
                _, span, _ = self._stack.pop()
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

    def turn_session(self, session_id: str) -> None:
        with self._lock:
            if self._turn is not None and session_id:
                self._turn.set_attribute("session.id", session_id)

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

    def _set_node_active(self, node_id: str, value: int) -> None:
        if self._node_active is not None:
            self._node_active.set(value, {"node": node_id})

    def turn_heartbeat(self, node_id: str, idle_s: float, elapsed_s: float) -> None:
        if self._turn_beats is not None:
            self._turn_beats.add(1, {"node": node_id})
            self._turn_idle.set(max(0.0, idle_s), {"node": node_id})
            self._turn_elapsed.set(max(0.0, elapsed_s), {"node": node_id})
