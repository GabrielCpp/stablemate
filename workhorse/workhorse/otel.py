"""OpenTelemetry instrumentation for workhorse — on when a collector is there.

``WORKHORSE_OTEL`` is tri-state. Set truthy it forces telemetry on; set falsy
(``0``/``false``/``no``) it forces it off; **unset** it means *auto*, and
``start_run`` decides by probing ``OTEL_EXPORTER_OTLP_ENDPOINT`` (default
``http://127.0.0.1:8787`` — groom's collector). Auto is the default because the
env var was a footgun: the runs worth having telemetry for are the unattended
week-long ones, and those are exactly the runs nobody remembers to export a
variable before launching. If groom is listening, a run should be observable.

The probe is what keeps that honest — auto-on may not *cost* anything on a
machine with no collector, so enabling is gated on one short-timeout TCP connect
rather than on hope. The SDK itself is a **required** dependency, so "installed but
unobservable" is not a state a workhorse install can be in — it was, while telemetry
was an `otel` extra, and the fail-soft policy below made that state silent: an install
missing the extra exported nothing, said nothing, and looked from the dashboard exactly
like a run that had died. With the endpoint dead, the SDK absent, or the var set
falsy, every function here is a near-zero-cost no-op — instrumentation must never
change how an unattended run behaves, let alone crash it, so every public entry
point also swallows its own exceptions.

Auto also declines to enable in a **test process** (:func:`_under_test`): a suite
run on a machine with ``groom serve`` up is otherwise the collector's single
largest producer, and none of what it writes is a run anyone will come back to.

The instrumentation sites call module-level functions rather than threading a
tracer object through the engine: there is exactly one run per process, so the
telemetry state is a process-wide singleton. What is process-wide is the
*reference*, not the state — one :class:`TelemetryHost` held in ``_host``, owning
its settings, its two effects (the collector probe and the SDK build) and the
active adapter as fields. The entry point reads the environment once, builds a
host and :func:`install`\\ s it; a test installs its own instead of assigning into
this module. What gets emitted:

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
    # Annotation-only: telemetry is imported by everything, so it must not pull
    # the runner (or the record models) in at runtime just to name the values it
    # is handed. `from __future__ import annotations` keeps these unevaluated.
    from workhorse.records import NodeEvent
    from workhorse.runner.usage import TurnUsage


def _tristate(raw: str | None) -> bool | None:
    """Parse a force-on / force-off / auto env var. ``None`` means unset (auto)."""
    value = (raw or "").strip().lower()
    if not value:
        return None
    return value not in ("0", "false", "no")


def _seconds(environ: Mapping[str, str], name: str, default: float) -> float:
    """A seconds-valued knob, or ``default`` when unset. A malformed value raises —
    it is read at the entry point, so a typo is a loud start-up failure rather than
    a run that silently ignores what an operator asked for."""
    return float(environ.get(name, "").strip() or default)


def _metric_export_every_s(environ: Mapping[str, str], heartbeat_every_s: float) -> float:
    """Seconds between metric exports: our knob, then the SDK's, then the heartbeat.

    This — not the heartbeat — is what bounds a collector's freshness, and the SDK's
    own default is 60s, so leaving it unset meant beating every 10s and *telling
    anyone* once a minute: a run that died could still look alive for the better part
    of a minute, and a consumer deriving liveness from beat recency had to keep a
    minute-wide tolerance to avoid false alarms. Match the heartbeat instead, so one
    beat is one export and silence is detectable within a couple of ticks. The SDK's
    own ``OTEL_METRIC_EXPORT_INTERVAL`` (milliseconds) still wins when set explicitly —
    that knob is documented and predates this default.

    Parsing is tolerant here, unlike :func:`_seconds`: this is the one knob with a
    *next source* to fall through to, so a malformed value costs the more specific
    setting rather than the run.
    """
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
class OtelSettings:
    """Everything telemetry reads from the environment — read once, at the edge.

    These were four module-scope reads, which froze before any test or caller could
    influence them: the only way to exercise the other branch of the gate was to
    reload the module. They are one immutable value now, built by
    :meth:`from_env` at the entry point and carried by the :class:`TelemetryHost`
    that uses them.
    """

    #: ``WORKHORSE_OTEL``, tri-state rather than a bool: True forces telemetry on,
    #: False forces it off, and None ("unset") defers to the collector probe.
    forced: bool | None = None
    #: ``OTEL_EXPORTER_OTLP_ENDPOINT``, defaulting to groom's local port.
    endpoint: str = "http://127.0.0.1:8787"
    #: Seconds the auto-mode probe waits for the collector to accept. Deliberately
    #: tiny: it sits on the critical path of every run start, and the endpoint it
    #: looks for is normally a loopback port that accepts (or refuses) in
    #: microseconds. A remote or firewalled endpoint is the only case that pays the
    #: full timeout, once per run.
    probe_timeout_s: float = 0.25
    #: How often the background thread proves the run's process is alive. Node calls
    #: are why this exists: a ``self.call`` node is ordinary Python that streams
    #: nothing a per-line heartbeat could hook, so a wedged one would otherwise be
    #: indistinguishable from a fast one until it returned.
    heartbeat_every_s: float = 10.0
    #: How often recorded metrics are actually shipped; see
    #: :func:`_metric_export_every_s` for why it tracks the heartbeat. The default
    #: here matches the heartbeat's default; ``from_env`` follows an override of it.
    metric_export_every_s: float = 10.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> OtelSettings:
        """The one place any of these names is read. Defaults come from the field
        defaults above, so they are stated exactly once."""
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


#: Basenames a standalone test file is invoked as. This repo's convention (and
#: workhorse's own rule) is `tests/test_<area>.py`, run as a plain script.
_TEST_ARGV0 = ("test_", "conftest.py")


def _under_test() -> bool:
    """Is this process a test run rather than a real one?

    A test run is telemetry's worst producer: it is short, it is repeated hundreds
    of times per suite, its run dirs are temporary, and nobody will ever go back to
    look at it — one `make test` of the workflows suite wrote a six-figure number of
    spans into groom.db and buried the real runs the dashboard exists to show. Auto-on
    is what makes that happen: the runs worth observing are the unattended ones, but
    the probe cannot tell them from a suite running on the same machine with `groom
    serve` up. The process can, so it is asked here.

    Three signals, because the suites are run three ways: pytest under a runner
    (`PYTEST_CURRENT_TEST`), pytest imported at all (its own collection phase, and
    xdist workers), and this repo's standalone `uv run python tests/test_x.py`
    convention, which imports no test framework at all and is only visible in argv.

    An explicit ``WORKHORSE_OTEL=1`` still wins — a test *of* telemetry has to be
    able to turn it on.
    """
    if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
        return True
    argv0 = os.path.basename(sys.argv[0] or "")
    return argv0.startswith(_TEST_ARGV0[0]) or argv0 == _TEST_ARGV0[1]


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _failsoft(fallback: _R) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Make a telemetry method degrade to `fallback` instead of raising.

    The fail-soft policy lives here and nowhere else: a telemetry bug must cost
    the span, never the run, and an instrumentation site must not have to know
    that. `fallback` is a parameter rather than a fixed `None` so the two
    non-void methods (`current_node`, `enabled`) can use the same decorator and
    keep their return types.
    """

    def decorate(fn: Callable[_P, _R]) -> Callable[_P, _R]:
        @functools.wraps(fn)
        def guarded(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            try:
                return fn(*args, **kwargs)
            except Exception:
                return fallback

        return guarded

    return decorate


# `current_node`'s fallback — and `str()` rather than `""` on purpose. A literal argument
# makes `_R` the type `Literal[""]`, which is not the `-> str` of the method being
# wrapped, so the decorator would stop preserving the signature it exists to preserve.
_NO_OPEN_NODE = str()
# As above, avoid narrowing the fail-soft decorator to ``Literal[0]``.
_NO_WAIT_TOKEN = int()
# `open_depth`'s fallback. Zero rather than -1: with telemetry failing soft the only
# safe reading of "how deep are we" is "no scope of mine is open", which makes the
# matching `unwind_to` a no-op instead of a sweep of somebody else's frames.
_NO_OPEN_DEPTH = int()

#: An exception class sets this `True` to say its raise moves the run rather than breaks
#: it, so `unwind_to` closes the frames it left open without calling them a failure.
CONTROL_UNWIND_MARKER = "workhorse_control_unwind"


def _is_control_unwind(error: BaseException) -> bool:
    """Is this raise a control signal rather than a failure?

    Asked of the exception instead of matched against a type, because this module imports
    nothing from the rest of workhorse — it is the leaf every layer instruments through,
    and an edge from here to `reload` (and so to `control`) inverts that for one boolean.
    The class that unwinds declares itself, next to the docstring that already argues it
    is not a failure.
    """
    return getattr(error, CONTROL_UNWIND_MARKER, False) is True


#: How a span learns the working tree's HEAD. A hook rather than an import, for the
#: reason above: this module is the leaf every layer instruments through, and
#: observing git is `workhorse.gitstate`'s job. The entry point points this at it
#: once the run's tree is known; a process that never binds one — a library caller,
#: a test — keeps the no-op and no attribute is stamped.
#:
#: The argument is *refresh*: False accepts the cached answer (span opens, which
#: happen in bursts), True re-reads (span closes, where the whole point is to catch
#: a HEAD that moved inside the span).
HeadProbe = Callable[[bool], str]


def _no_head(refresh: bool) -> str:  # noqa: ARG001 — the null probe ignores it
    return ""


_head_probe: HeadProbe = _no_head


def set_head_probe(probe: HeadProbe | None) -> None:
    """Point span stamping at a repo observer, or back at the no-op with ``None``."""
    global _head_probe
    _head_probe = probe or _no_head


def _head_attrs(key: str, *, refresh: bool = False) -> dict[str, str]:
    """``{key: <head>}``, or empty for anything that is not an observed hash.

    Empty rather than blank: an absent attribute is honest about a cwd that is not a
    repository, whereas ``git.head.start = ""`` is a claim nobody made. Swallowing is
    deliberate and matches the rest of this module — a probe that raises must cost an
    attribute, never the span.
    """
    try:
        head = _head_probe(refresh)
    except Exception:
        return {}
    return {key: head} if head else {}


class Telemetry(Protocol):
    """What the instrumentation sites may ask of telemetry.

    One typed interface with two implementations: `_Telemetry`, which opens spans
    and records metrics, and `_NullTelemetry`, which does nothing. Absence is the
    null one — never a nullable reference and never a `getattr` by method name,
    which is what this replaced: a string method name defeats rename, signature
    checking and find-usages at once, and paired with the swallow-everything
    policy below a typo in it is a permanent silent no-op with nothing to notice
    it. Fail-soft is still the policy; it lives in `_failsoft` on the real class.
    """

    def enabled(self) -> bool: ...
    def record_event(self, event: NodeEvent) -> None: ...
    def run_attribute(self, name: str, value: str) -> None: ...
    def state_start(self, state: str, seq: int) -> None: ...
    def state_end(
        self, state: str, seq: int, next_state: str | None = None, cut: str = ""
    ) -> None: ...
    def wait_start(self, kind: str, node_id: str) -> int: ...
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
    """Telemetry that is off: every call is a near-zero-cost no-op.

    This is what a host's `active` holds with no collector reachable, so the "do nothing"
    policy exists in exactly one class rather than as an absence test at each of
    the fourteen entry points below.
    """

    def enabled(self) -> bool:
        return False

    def record_event(self, event: NodeEvent) -> None: ...
    def run_attribute(self, name: str, value: str) -> None: ...
    def state_start(self, state: str, seq: int) -> None: ...
    def state_end(
        self, state: str, seq: int, next_state: str | None = None, cut: str = ""
    ) -> None: ...
    def wait_start(self, kind: str, node_id: str) -> int:
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


#: The one "telemetry is off" instance. Stateless, so one reference serves every
#: run in the process.
_NULL: Telemetry = _NullTelemetry()


def _collector_reachable(endpoint: str, timeout_s: float) -> bool:
    """True when something accepts a TCP connection at ``endpoint``.

    A listening socket is as much as a cheap probe can prove, and it is enough:
    the OTLP exporter is batched and fire-and-forget, so guessing wrong costs
    dropped spans, never a broken run. Anything that goes wrong here — refused,
    unresolvable, timed out, malformed endpoint — means "no collector".
    """
    try:
        parsed = urlparse(endpoint)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout_s):
            return True
    except Exception:
        return False


class CollectorProbe(Protocol):
    """Is anything listening at ``endpoint``? :func:`_collector_reachable` is the
    implementation; a test is the other one — left live, the gate's answer would
    depend on whether the machine running the suite happens to have a collector up."""

    def __call__(self, endpoint: str, timeout_s: float) -> bool: ...


class TelemetryFactory(Protocol):
    """Build the run's telemetry, or return None when the optional SDK is absent.
    :func:`_build` is the implementation; a test hands back a fake rather than
    standing up an exporter."""

    def __call__(
        self,
        workflow: str,
        run_id: str,
        run_dir: str | None,
        settings: OtelSettings,
    ) -> Telemetry | None: ...


#: Where the per-run-directory start counter lives, beside the checkpoint and
#: `sessions.jsonl` — durable state about the run belongs with the run.
_GENERATION_FILE = "resume_generation"


def _resume_generation(run_dir: str | None) -> int:
    """Read-increment-write this run directory's start counter, and return the new value.

    A resume reuses the run_id and opens a fresh root span, so run_id alone cannot
    separate "the process died and was restarted here" from "the process sat waiting".
    That distinction is worth a file: on one real run, 41 of 105 wall-clock hours fell
    into eleven gaps of more than five minutes, and nothing in the trace said which
    kind they were — which matters because one is fixed by checkpoint durability and
    the other by a workflow's own gating.

    It counts starts that got as far as building telemetry, so a run resumed with
    telemetry off does not advance it. That costs the absolute number and keeps the
    only property queries rely on: consecutive spans with different generations have a
    restart between them.

    Never raises. An unwritable or corrupt counter yields 0 — instrumentation does not
    get to fail a run over its own bookkeeping.
    """
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
        # Only worth a word to someone who asked for telemetry. In auto mode the
        # collector merely happens to be up, so this would otherwise print on every
        # run start on any machine without the extra — noise nobody opted into.
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
            # The run's artifact directory: what turns a span into a filesystem
            # lookup (prompt.md / output.json / events.jsonl) in one hop, instead
            # of a manual join through the runs/ tree.
            "run_dir": run_dir or "",
            # This process's OS pid — the standard OTel semantic-convention key. A
            # native run shares the collector's host, so advertising it lets a
            # consumer (groom) correlate the run to its process and, later, signal it.
            "process.pid": os.getpid(),
            # The run's working directory — where a same-host consumer reads
            # Files/Diff from. Defaults to the process cwd; a workflow (or its
            # harness) that operates on a checkout elsewhere overrides it by setting
            # AGENT_REPO_DIR, the same working-tree env the script utilities already
            # resolve from (see the kit’s find_repo_root). The engine learns no
            # workflow's schema and no consumer's name — it forwards a value it is
            # handed, exactly like repo/branch above.
            "workspace": os.environ.get("AGENT_REPO_DIR") or os.getcwd(),
            # How many times this run directory has been started. A resume opens a
            # fresh root span under the *same* run_id, so without this a gap between
            # two spans is unattributable: a crash-and-resume, an Await on an
            # operator, and a process simply thinking look identical in span timing.
            # A gap that crosses a generation boundary is the first kind.
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
    # Imported here, not at module scope: logsetup imports this module for
    # current_node(), so a top-level import would be circular.
    from workhorse import logsetup

    logsetup.attach_otel(logger_provider)
    return telemetry


@dataclass(slots=True)
class TelemetryHost:
    """The run's telemetry, and the three decisions that select it.

    ``start_run``'s gate used to read four module globals and call two module
    functions by name, which is why every test of it had to assign into this module
    to set up its scenario. All six are fields now: the settings come from the edge,
    the probe and the factory are the two effects, and ``active`` is the adapter they
    choose — never None, so no instrumentation site branches on absence.

    ``slots=True`` is load-bearing, not decoration: the injected callables land in
    instance slots, so ``self.probe(...)`` is a plain call. Stored as class
    attributes they would become bound methods and silently take the host as their
    first argument.
    """

    settings: OtelSettings = field(default_factory=OtelSettings)
    probe: CollectorProbe = _collector_reachable
    build: TelemetryFactory = _build
    under_test: Callable[[], bool] = _under_test
    active: Telemetry = _NULL

    def start_run(self, workflow: str, run_id: str, run_dir: str | None = None) -> None:
        """Configure the SDK and open the run's root span.

        On unless ``WORKHORSE_OTEL`` is set falsy: with it set truthy the SDK is built
        unconditionally, and with it unset (auto) only when the collector answers the
        probe **and** this is not a test process (:func:`_under_test`). Still a no-op
        if the optional SDK isn't importable.
        """
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
        except Exception as exc:  # instrumentation must never break a run
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
        """Close every open span (root last), flush, and shut the SDK down.
        Idempotent — the finally-backstop in ``main.run`` may call it again."""
        telemetry, self.active = self.active, _NULL
        if not telemetry.enabled():
            return
        try:
            # Unhook logging before the provider below is shut down, so no late
            # record is handed to a dead exporter.
            from workhorse import logsetup

            logsetup.detach_otel()
        except Exception:
            pass
        telemetry.end_run(status, error, error_class, error_kind)


#: The process's host. One run per process, so one reference — held here, and here
#: only. Built from the defaults rather than from the environment: reading it is the
#: entry point's job (``pyflow/run.py``), which installs the host it built.
_host = TelemetryHost()


def install(host: TelemetryHost) -> TelemetryHost:
    """Make ``host`` the one the module-level functions below delegate to, and return
    the previous one so a caller can put it back.

    This is the injection point the whole module hangs off: the entry point uses it
    to hand telemetry the environment it read, and a test uses it to install fakes
    instead of assigning over private names in here.
    """
    global _host
    previous, _host = _host, host
    return previous


def enabled() -> bool:
    """Whether the active telemetry actually exports anything."""
    return _host.active.enabled()


def start_run(workflow: str, run_id: str, run_dir: str | None = None) -> None:
    """Open the installed host's run. See :meth:`TelemetryHost.start_run`."""
    _host.start_run(workflow, run_id, run_dir)


def end_run(
    status: str, error: str | None = None, error_class: str = "", error_kind: str = ""
) -> None:
    """Close the installed host's run. See :meth:`TelemetryHost.end_run`."""
    _host.end_run(status, error, error_class, error_kind)


def record_event(event: NodeEvent) -> None:
    """Mirror one ArtifactWriter event-log record (enter/done/terminal) into
    node spans. Called from ``ArtifactWriter._append_event`` with the same
    ``NodeEvent`` it writes to ``events.jsonl`` — the model is the contract, so
    a field renamed there is a type error here rather than a silently absent
    span attribute."""
    _host.active.record_event(event)


def run_attribute(name: str, value: str) -> None:
    """Stamp a run-level fact on the root span. See :meth:`_Telemetry.run_attribute`."""
    _host.active.run_attribute(name, value)


def state_start(state: str, seq: int) -> None:
    """Open the span for one state-body execution.

    Checkpoint events record durable position and are not execution boundaries: an
    ``Await`` writes its target checkpoint before polling, when that target is not yet
    running. The driver therefore brackets actual dispatch explicitly.
    """
    _host.active.state_start(state, seq)


def state_end(state: str, seq: int, next_state: str | None = None, cut: str = "") -> None:
    """Close a state-body execution — successfully returned, or ``cut`` short.

    A non-empty ``cut`` names why the body did not run to its own end (today: a live
    reload), and is stamped on this span and on every node span still open under it.
    Closing them is what keeps a reload from leaving unclosed spans; saying they were
    cut is what keeps the closed ones from being read as completed work.
    """
    _host.active.state_end(state, seq, next_state, cut)


@contextmanager
def scope() -> Iterator[None]:
    """Close, in this body's own `finally`, every span the body leaves open.

    Span open/close is driven by the enter/done records the engine writes, so a body
    that raises never emits its `done` and its frame stays open. Bracketing the body
    makes the raise close it *here*, at the depth that opened it, with the error
    recorded on the innermost frame only — see :meth:`_Telemetry.unwind_to`.

    `@contextmanager` yields a `ContextDecorator`, so this reads either way::

        with otel.scope():
            value = self._invoke(spec, args, kwargs)

        @otel.scope()
        def run_node(...): ...

    A body that closed its own spans (a reload unwinding through `state_end`) leaves
    the depth already restored, and this is then a no-op.
    """
    depth = _host.active.open_depth()
    try:
        yield
    except BaseException as exc:
        _host.active.unwind_to(depth, exc)
        raise


@contextmanager
def wait(kind: str, node_id: str) -> Iterator[None]:
    """Bracket an actual engine-controlled wait with a completed duration span."""
    token = _host.active.wait_start(kind, node_id)
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
) -> None:
    _host.active.turn_start(node_id, model, effort, timeout, backend)


def turn_end(error: str | None = None, error_class: str = "", error_kind: str = "") -> None:
    _host.active.turn_end(error, error_class, error_kind)


def turn_result(usage: TurnUsage) -> None:
    """Attach a turn's duration + token usage to the open agent-turn span.

    ``usage`` is already normalized (``runner/usage.py``), so every backend's
    dialect arrives here in Claude's key names and one query reads them all."""
    _host.active.turn_result(usage)


def set_labels(labels: dict[str, str]) -> None:
    """Set the workflow-declared dimensions (`labels:`) stamped on later spans.

    Called once per node with the graph's labels rendered against the live
    context. Values must already be strings; ``{}`` clears them."""
    _host.active.set_labels(labels)


def turn_session(session_id: str) -> None:
    """Tag the open agent-turn span with the backend CLI's session id, so a
    node's span leads back to that session's transcript (``opencode export <id>``
    and equivalents) — the agent's reasoning/tool trace, which the node's
    ``prompt.md`` / ``output.json`` do not carry."""
    _host.active.turn_session(session_id)


def turn_event(name: str, *, error: bool = False, **attrs: Any) -> None:
    """Record a recovery-ladder event (retry/reframe/compact/cap_wait/
    watchdog_kill) on the open turn span, falling back to the node span.
    Thread-safe: the watchdog calls this from its daemon timer thread."""
    _host.active.turn_event(name, error, attrs)


def heartbeat(node_id: str, remaining_s: float) -> None:
    """One cap-wait tick: proof the run is alive inside a legitimate multi-hour
    spending-cap sleep (silence, by contrast, means a hang)."""
    _host.active.heartbeat(node_id, remaining_s)


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
    _host.active.turn_heartbeat(node_id, idle_s, elapsed_s)


def current_node() -> str:
    """The node the run is currently inside, or "" — for tagging log records.

    Workhorse opens node spans with ``start_span``, never ``start_as_current_span``,
    so nothing is in the OTel *context* and a log record would otherwise carry
    ``trace_id=0``: the SDK's LoggingHandler correlates via the ambient context,
    which this engine deliberately does not populate. Tagging the node explicitly
    is what makes ``groom logs --node`` work at all.
    """
    return _host.active.current_node()


class _Telemetry:
    """The per-run span/metric state behind the module-level facade.

    All mutation happens under one re-entrant lock: the engine's step loop is
    single-threaded, but the watchdog fires span events from a daemon timer
    thread, and end_run must be able to sweep whatever is open at that moment.
    """

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
        # `end_run` is called more than once by design — every finalizing branch in
        # the driver stamps its own status, and a `finally` stamps `aborted` behind
        # them all as the crash backstop. Only the first may take effect, and that
        # has to include the flush: a second `_shutdown()` would shut an already-shut
        # provider, and a second `turn_end(error)` would attach a bogus error to
        # nothing. Ending is therefore latched, not inferred from `_root`.
        self._ended = False
        # Latched by the first span to carry the failure, so the run exports exactly one
        # ERROR span however deep the frame that raised was. See `unwind_to`.
        self._error_reported = False
        # Open execution spans, innermost last:
        # [((kind, name, seq), span, started_at), ...].
        # The engine's walk nests strictly (a flow node's children open and close
        # while the flow node span is open), so a stack mirrors the tree. The
        # monotonic start stamp feeds the node.elapsed_s gauge, which — unlike the
        # span's own duration — is readable *while* the node is still running.
        self._stack: list[tuple[tuple[str, str, int], Any, float]] = []
        self._wait_seq = 0
        self._wait_keys: dict[int, tuple[str, str, int]] = {}
        self._wait_live: dict[int, tuple[str, str, float]] = {}
        self._turn: Any = None
        # Wall-clock bounds of the open turn, so a harness that reports no duration
        # still gets one (see turn_end); the flag stops that fallback from clobbering
        # a duration the backend did report.
        self._turn_started: float | None = None
        self._turn_node = ""
        self._turn_has_duration = False
        # Workflow-declared dimensions (the graph's `labels:`), already rendered
        # against the live context by the caller. Stamped onto every node and turn
        # span opened while they are set — this is what lets a query group turns by
        # the workflow's own unit of work without workhorse knowing what one is.
        self._labels: dict[str, str] = {}
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

    # ---- spans ---------------------------------------------------------- #
    def start_root(self, workflow: str) -> None:
        with self._lock:
            self._root = self._tracer.start_span(
                f"run:{workflow}", attributes=_head_attrs("git.head.start", refresh=True)
            )

    @_failsoft(None)
    def run_attribute(self, name: str, value: str) -> None:
        """Stamp one run-level fact on the root span.

        A span's attributes are read at export, and the root exports when the run ends,
        so a value set later — or set twice — is not lost: last write wins. That is the
        right rule for the one caller there is today (`workhorse.profile`), where a
        `control switch-profile` means the profile the run *finished* on is the honest
        answer to "which models did this cost buy".
        """
        with self._lock:
            if self._root is not None:
                self._root.set_attribute(name, value)

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
        while not self._stop.wait(self._heartbeat_every_s):
            self._beat_once()

    def _live_attrs(self, node_id: str) -> dict[str, str]:
        """Metric attributes for the live "where is it now" signals: the node plus
        the run's current *activity* and *work_id*.

        Spans export only on completion, so these gauges are the only telemetry that
        reaches a collector while a node is still open — which is exactly when a
        monitor wants to show what the run is doing. So the two label dimensions a
        dashboard renders (*activity*, *work_id*) ride the gauges too, and only those
        two, to keep metric attribute cardinality bounded. ``self._labels`` is rebound
        wholesale by ``set_labels``, so reading it without the lock sees a consistent
        old-or-new dict, never a torn one.

        Both spellings are promoted because the two engines name them differently: the
        YAML engine prefixes every workflow label with ``wf.`` so a workflow cannot
        shadow an OTel convention, while ``pyflow`` leaves them raw. Each engine's own
        key rides as-is — nothing is translated on the way out, so a collector reading
        one spelling never has to guess which engine produced it.
        """
        attrs: dict[str, str] = {"node": node_id}
        labels = self._labels
        for key in ("wf.activity", "wf.work_id", "activity", "work_id"):
            value = labels.get(key)
            if value:
                attrs[key] = value
        return attrs

    # A telemetry bug must degrade to "no heartbeat", never take down the thread
    # (and with it every later liveness signal) mid-run.
    @_failsoft(None)
    def _beat_once(self) -> None:
        """Emit one liveness tick for whatever node is open (or none)."""
        with self._lock:
            top = self._stack[-1] if self._stack else None
            wait = next(reversed(self._wait_live.values()), None)
        node = top[0][1] if top else ""
        attrs = self._live_attrs(node)
        if self._run_beats is not None:
            self._run_beats.add(1, attrs)
        if top is not None and self._node_elapsed is not None:
            self._node_elapsed.set(time.monotonic() - top[2], attrs)
        if wait is not None and self._wait_elapsed is not None:
            wait_node, kind, started = wait
            self._wait_elapsed.set(
                time.monotonic() - started,
                self._wait_attrs(wait_node, kind),
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
        # State checkpoints are durable-position records, not node execution events.
        # Every checkpoint includes this key, including ordinary ones whose value is
        # None. Await checkpoints carry a path and must likewise open no target span.
        if phase == "enter" and "waiting_on" in extra:
            return
        with self._lock:
            if phase == "enter":
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
                )
            elif phase == "done":
                self._end_execution(("node", node_id, seq), next_name=extra.get("next"))
                self._set_node_active(node_id, 0)
            elif phase == "error":
                # `record_interrupt` writes this to events.jsonl when a run is killed
                # mid-node. Mirror it into the open span so a crash and a hang do not
                # look identical while the reason sits on disk only.
                target = self._stack[-1][1] if self._stack else self._root
                if target is not None:
                    target.add_event("error", {"error": str(extra.get("error") or "")})
            elif phase == "terminal":
                # A flow's finish() also emits a terminal (node "<run>") — the
                # stack scopes it to the enclosing flow-node span; the run's own
                # terminal (stack empty) lands on the root span.
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
    def wait_start(self, kind: str, node_id: str) -> int:
        with self._lock:
            self._wait_seq += 1
            token = self._wait_seq
            key = ("wait", node_id, token)
            self._wait_keys[token] = key
            started = time.monotonic()
            self._wait_live[token] = (node_id, kind, started)
            self._start_execution(
                key,
                f"wait:{kind}",
                node_id,
                {
                    "workhorse.span_kind": "wait",
                    "workhorse.wait_kind": kind,
                },
                mark_active=False,
            )
            attrs = self._wait_attrs(node_id, kind)
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
                node_id, kind, started = live
                attrs = self._wait_attrs(node_id, kind)
                if self._wait_elapsed is not None:
                    self._wait_elapsed.set(time.monotonic() - started, attrs)
                if self._wait_active is not None:
                    self._wait_active.set(0, attrs)

    def _wait_attrs(self, node_id: str, kind: str) -> dict[str, str]:
        return {**self._live_attrs(node_id), "wait_kind": kind}

    def _start_execution(
        self,
        key: tuple[str, str, int],
        span_name: str,
        node_id: str,
        attributes: dict[str, Any],
        *,
        mark_active: bool = True,
    ) -> None:
        span = self._tracer.start_span(
            span_name,
            context=self._parent_ctx(),
            attributes={
                "workhorse.node": node_id,
                "workhorse.seq": key[2],
                "workhorse.depth": len(self._stack),
                # Cached: a node opens inside the burst of work the previous one's
                # close already refreshed, so re-reading here would buy a subprocess
                # per transition and the same hash.
                **_head_attrs("git.head.start"),
                **attributes,
                **self._labels,
            },
        )
        self._stack.append((key, span, time.monotonic()))
        # Metrics export independently of span completion, so this is what makes
        # the currently executing state or node visible while it is still open.
        if mark_active:
            self._set_node_active(node_id, 1)

    def _end_execution(
        self,
        key: tuple[str, str, int],
        next_name: Any,
        end_attributes: dict[str, Any] | None = None,
        cut: str = "",
    ) -> None:
        """End the span for ``key``, sweeping anything left open above it.

        ``cut`` is stamped on every span this closes, swept ones included: a scope that
        ended because the work under it was interrupted did not *complete*, and a reader
        with only start and end timestamps cannot tell the two apart. It is what lets
        groom count a node visit that a reload cut as an interruption rather than as one
        more completed repeat of the same work.
        """
        if all(k != key for k, _, _ in self._stack):
            return
        # One refreshed read for the whole sweep: every span closing here closes *now*,
        # so they share an end state, and re-reading per span would spawn a git per
        # frame. Unequal to the span's `git.head.start` means something moved HEAD
        # inside it — which this records and does not interpret.
        end_head = _head_attrs("git.head.end", refresh=True)
        while self._stack:
            stack_key, span, _ = self._stack.pop()
            for name, value in end_head.items():
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

    @_failsoft(_NO_OPEN_DEPTH)
    def open_depth(self) -> int:
        """How many execution spans are open — the mark a `scope()` unwinds back to."""
        with self._lock:
            return len(self._stack)

    @_failsoft(None)
    def unwind_to(self, depth: int, error: BaseException) -> None:
        """Close every span opened above ``depth`` because the body raised.

        Two rules, and both are why this exists rather than letting `end_run` sweep:

        A span is closed by the scope that opened it, in that scope's own `finally`.
        Swept at the end of the run instead, a node span's duration runs to the moment
        the process gave up rather than to the moment its work stopped, and every frame
        between them is stamped with whatever verdict the run ended on.

        The error is recorded **once**, on the innermost frame — the one whose body
        actually raised. Nesting depth is not a count of failures: one `AttributeError`
        three frames down used to close as three ERROR spans, so a dashboard summing
        `status = 'ERROR'` reported "3 errors" for one defect and the number moved when
        the *shape* of the workflow changed. The outer frames record that they ended in
        an error (`workhorse.outcome`) without claiming to be one.

        Not every raise is a failure. A control unwind — `ReloadRequested` is the one —
        travels as an exception because it has to leave an arbitrarily deep stack of
        re-entrant `drive` frames, and those frames really are over, so they still close
        here. But the run did what the operator asked, so they close *cleanly*: outcome
        recorded, no ERROR status, no `error.class`, and the once-per-run error slot left
        for a genuine one. `AgentRunner.turn` already reasons exactly this way about the
        turn span it closes for a cut; a node span that stayed ERROR made groom badge a
        successful reload as the run's one error.
        """
        control = _is_control_unwind(error)
        with self._lock:
            innermost = True
            while len(self._stack) > depth:
                _, span, _ = self._stack.pop()
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
        # Stop beating before the flush below, so the last export cannot race a
        # tick that would claim the run is still alive after it ended.
        self._stop.set()
        if self._beat_thread is not None:
            self._beat_thread.join(timeout=2)
            self._beat_thread = None
        failed = status in {"fail", "aborted"} and error is not None
        with self._lock:
            for token in list(self._wait_live):
                self.wait_end(token, "interrupted")
            self.turn_end(error if failed else None)
            # Whatever is still open here was not closed by its own scope — a frame with
            # no `finally` around it, or a kill between two of them. Closing it is the
            # backstop; stamping it is not. An abandoned frame says so with an attribute,
            # so a reader can still tell it apart from one that ran to its own end.
            end_head = _head_attrs("git.head.end", refresh=True)
            while self._stack:
                _, span, _ = self._stack.pop()
                span.set_attribute("workhorse.outcome", "abandoned")
                for name, value in end_head.items():
                    span.set_attribute(name, value)
                span.end()
            if self._root is not None:
                self._root.set_attribute("workhorse.terminal", status)
                for name, value in end_head.items():
                    self._root.set_attribute(name, value)
                if error_class:
                    self._root.set_attribute("error.class", error_class)
                if error_kind:
                    self._root.set_attribute("error.kind", error_kind)
                # Only when nothing under it already carried the failure. The run-level
                # verdict is `workhorse.terminal` — an attribute, readable on every run —
                # so the ERROR *status* is free to mean "this is the span that broke".
                if failed and not self._error_reported:
                    self._error_reported = True
                    self._root.set_status(
                        self._trace.Status(self._trace.StatusCode.ERROR, error)
                    )
                self._root.end()
                self._root = None
        self._shutdown()  # flushes the batch processor + metric reader

    # ---- agent turns ----------------------------------------------------- #
    @_failsoft(None)
    def turn_start(
        self,
        node_id: str,
        model: str | None,
        effort: str | None,
        timeout: float,
        backend: str | None = None,
    ) -> None:
        with self._lock:
            if self._turn is not None:  # defensive: never leak an open turn
                self.turn_end()
            self._turn_started = time.monotonic()
            self._turn_node = node_id
            self._turn_has_duration = False
            self._turn = self._tracer.start_span(
                "agent_turn",
                context=self._parent_ctx(),
                attributes={
                    "workhorse.node": node_id,
                    # Which harness ran the turn. `model` alone cannot answer it —
                    # two backends can drive the same model slug, and comparing
                    # harnesses was impossible without this.
                    "backend": backend or "",
                    "model": model or "",
                    "effort": effort or "",
                    "timeout_s": -1 if timeout == float("inf") else int(timeout),
                    # Refreshed, unlike a node open: the agent is what most often moves
                    # HEAD, so the tree a turn *started* against is worth a subprocess.
                    **_head_attrs("git.head.start", refresh=True),
                    **self._labels,
                },
            )
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
            if turn is None:
                return
            # Every turn gets a duration, even from a harness that reports none —
            # the engine timed it either way. Only fill the gap: a backend-reported
            # duration excludes process spawn, so it is the truer number and wins.
            if not self._turn_has_duration and self._turn_started is not None:
                turn.set_attribute(
                    "duration_ms", int((time.monotonic() - self._turn_started) * 1000)
                )
            self._turn_started = None
            for name, value in _head_attrs("git.head.end", refresh=True).items():
                turn.set_attribute(name, value)
            if error:
                # The class and the recovery bucket, not just the message. A store can
                # count failed turns from the status alone; only these say whether they
                # were rate limits ridden out, context overflows, or a broken CLI —
                # which are the same number and opposite problems.
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
                self._turn_has_duration = True  # turn_end must not overwrite it
            # `token_counts()` omits whatever the harness did not report — e.g.
            # `reasoning_output_tokens`, which codex and opencode send and Claude's
            # result event does not. Left off the span entirely rather than zeroed,
            # so "no reasoning tokens" stays distinguishable from "not measured".
            for field, count in usage.token_counts().items():
                turn.set_attribute(f"usage.{field}", int(count))
            if usage.total_cost_usd is not None:
                turn.set_attribute("total_cost_usd", float(usage.total_cost_usd))

    @_failsoft(None)
    def set_labels(self, labels: dict[str, str]) -> None:
        """Replace the workflow-declared dimensions stamped on subsequent spans.

        Replace, not merge: the labels describe what the run is working on *now*,
        and a key that stopped resolving (the epic finished, the story cleared)
        must stop appearing rather than linger at its last value and mislabel
        every later span.
        """
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

    # ---- metrics ---------------------------------------------------------- #
    @_failsoft(None)
    def gas_level(self, gas: int, capacity: int) -> None:
        # Both instruments are named, not just the first: they are created together and
        # cleared together above, but that is a fact about the constructor and nothing
        # here can see it.
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
