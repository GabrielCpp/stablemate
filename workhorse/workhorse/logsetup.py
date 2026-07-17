"""Console + OpenTelemetry logging for workhorse and its in-process script nodes.

One root-logger configuration serves both, which is the point: since
``runner/script.py`` imports script nodes and calls their ``main(logger)`` in
*this* process, a script's log records travel the same handlers as the engine's
— no separate sink, no per-script SDK init, and one ``run_id`` on both.

Two handlers, deliberately different in kind:

- a **console** handler, always on, so a run watched in a terminal reads exactly
  as it did before telemetry existed;
- an **OTel** handler, attached only once ``otel._build`` has a LoggerProvider,
  which ships the same records to the collector.

The console handler binds ``sys.stderr`` **at setup time** rather than resolving
it per record, and that is load-bearing rather than incidental. The in-process
script runner redirects ``sys.stdout``/``sys.stderr`` to capture a script's JSON
payload; a handler that looked up ``sys.stderr`` lazily would write into that
capture buffer, so every log line a script emitted would be swallowed into the
JSON parse instead of reaching the terminal. Holding the true stderr means log
records bypass the capture entirely — which is what keeps script logs on the
console while their stdout is still parsed as data.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from workhorse import otel

_LEVEL = (os.environ.get("WORKHORSE_LOG_LEVEL") or "INFO").strip().upper()
# Third-party loggers that are chatty at DEBUG and say nothing about the run.
_NOISY = ("httpx", "httpcore", "urllib3", "asyncio", "markdown_it", "PIL")

_configured = False
_otel_handler: logging.Handler | None = None


class _NodeFilter(logging.Filter):
    """Stamp every record with the node the run is currently inside.

    Never a lookup at query time: by the time a log is read, the run has moved on
    (or died), so the node has to be captured at emit. This is also the only
    correlation available — see ``otel.current_node`` for why trace_id is not.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "node"):
            record.node = otel.current_node()
        return True


class _DropOtelInternals(logging.Filter):
    """Keep the SDK's own diagnostics out of the OTel handler.

    Without this, a collector that is down or slow is self-amplifying: the
    exporter fails, logs the failure, the handler queues that log, the export of
    *that* fails, and so on. The console still shows these records — it is only
    the path back into the exporter that is cut.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith("opentelemetry")


def setup() -> None:
    """Configure console logging. Safe to call more than once."""
    global _configured
    if _configured:
        return
    _configured = True
    root = logging.getLogger()
    root.setLevel(getattr(logging, _LEVEL, logging.INFO))
    # Bound now, on purpose — see the module docstring: this reference must
    # outlive the script runner's stdout/stderr redirection.
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    console.addFilter(_NodeFilter())
    root.addHandler(console)
    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)


def attach_otel(logger_provider: Any) -> None:
    """Also ship root-logger records to the collector. No-op without a provider."""
    global _otel_handler
    if logger_provider is None or _otel_handler is not None:
        return
    try:
        from opentelemetry.sdk._logs import LoggingHandler
    except ImportError:
        return
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    handler.addFilter(_NodeFilter())
    handler.addFilter(_DropOtelInternals())
    logging.getLogger().addHandler(handler)
    _otel_handler = handler


def detach_otel() -> None:
    """Drop the OTel handler before its provider shuts down.

    end_run flushes and shuts the provider down; a handler left attached would
    then hand records to a dead provider on the way out of the process.
    """
    global _otel_handler
    handler, _otel_handler = _otel_handler, None
    if handler is not None:
        logging.getLogger().removeHandler(handler)


def script_logger(node_id: str) -> logging.Logger:
    """The logger handed to a script node's ``main(logger)``.

    Named per node so console output says which script spoke, and so a reader can
    filter to one script's records without needing the node attribute.
    """
    return logging.getLogger(f"script.{node_id}")
