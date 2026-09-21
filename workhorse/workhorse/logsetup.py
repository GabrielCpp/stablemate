"""Console + OpenTelemetry logging for workhorse and its in-process script nodes."""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from workhorse import otel

_LEVEL = (os.environ.get("WORKHORSE_LOG_LEVEL") or "INFO").strip().upper()
_NOISY = ("httpx", "httpcore", "urllib3", "asyncio", "markdown_it", "PIL")

_configured = False
_otel_handler: logging.Handler | None = None


class _NodeFilter(logging.Filter):
    """Stamp every record with the node the run is currently inside."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "node"):
            record.node = otel.current_node()
        return True


class _HeadFilter(logging.Filter):
    """Stamp every record from the immutable snapshot of its innermost active span."""

    def filter(self, record: logging.LogRecord) -> bool:
        snapshot = otel.current_repository()
        for key, value in snapshot.items():
            record.__dict__.setdefault(key, value)
        head = snapshot.get("git.head")
        if head:
            record.__dict__.setdefault("head", head)
        return True


class _DropOtelInternals(logging.Filter):
    """Keep the SDK's own diagnostics out of the OTel handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith("opentelemetry")


def setup() -> None:
    """Configure console logging."""
    global _configured
    if _configured:
        return
    _configured = True
    root = logging.getLogger()
    root.setLevel(getattr(logging, _LEVEL, logging.INFO))
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    console.addFilter(_NodeFilter())
    root.addHandler(console)
    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)


def attach_otel(logger_provider: Any) -> None:
    """Also ship root-logger records to the collector."""
    global _otel_handler
    if logger_provider is None or _otel_handler is not None:
        return
    try:
        from opentelemetry.sdk._logs import LoggingHandler
    except ImportError:
        return
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    handler.addFilter(_NodeFilter())
    handler.addFilter(_HeadFilter())
    handler.addFilter(_DropOtelInternals())
    logging.getLogger().addHandler(handler)
    _otel_handler = handler


def detach_otel() -> None:
    """Drop the OTel handler before its provider shuts down."""
    global _otel_handler
    handler, _otel_handler = _otel_handler, None
    if handler is not None:
        logging.getLogger().removeHandler(handler)


def script_logger(node_id: str) -> logging.Logger:
    """The logger handed to a script node's ``main(logger)``."""
    return logging.getLogger(f"script.{node_id}")
