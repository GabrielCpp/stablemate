"""Tests for the console + OpenTelemetry logging pipeline (workhorse.logsetup).

The two properties that matter here are both about what happens to a log record
when a script node is running in-process: it must still reach the terminal even
though the script's stdout/stderr are redirected for JSON capture, and it must
carry the node it came from — since workhorse's spans are never made current,
nothing else correlates it. Runnable two ways:
    ./.venv/bin/python -m pytest tests/test_logsetup.py
"""
from __future__ import annotations

import io
import logging
import sys
from contextlib import redirect_stderr, redirect_stdout

from workhorse import logsetup, otel


def _fresh_root():
    """A root logger with no handlers, restored by the caller."""
    root = logging.getLogger()
    saved = root.handlers[:]
    root.handlers[:] = []
    return root, saved


def test_console_handler_survives_the_script_stdout_capture():
    """The load-bearing one. The in-process runner redirects stdout/stderr to
    capture a script's JSON; a console handler that resolved sys.stderr lazily
    would write into that buffer, so every log line a script emitted would be
    swallowed into the JSON parse instead of reaching the operator. Binding the
    real stderr at setup time is what prevents that."""
    root, saved = _fresh_root()
    real_stderr = io.StringIO()
    logsetup._configured = False
    try:
        with redirect_stderr(real_stderr):
            logsetup.setup()  # binds THIS stderr
        # Now simulate the runner: redirect both streams elsewhere and log.
        captured_out, captured_err = io.StringIO(), io.StringIO()
        with redirect_stdout(captured_out), redirect_stderr(captured_err):
            logging.getLogger("script.demo").warning("still visible")
    finally:
        root.handlers[:] = saved
        logsetup._configured = False

    assert "still visible" in real_stderr.getvalue(), (
        "log went into the script's capture buffer instead of the console"
    )
    assert "still visible" not in captured_out.getvalue(), (
        "a log record reached stdout — it would corrupt the node's JSON outputs"
    )
    assert "still visible" not in captured_err.getvalue()


def test_records_are_stamped_with_the_current_node(monkeypatch):
    """Correlation is by explicit attribute, not trace context: the engine opens
    node spans with start_span (never start_as_current_span), so a record's
    trace_id is zeroes and only this stamp joins a log to a node."""
    monkeypatch.setattr(otel, "current_node", lambda: "select_item")
    record = logging.LogRecord("script.x", logging.INFO, __file__, 1, "hi", None, None)
    assert logsetup._NodeFilter().filter(record) is True
    assert record.node == "select_item"


def test_an_explicit_node_is_not_overwritten(monkeypatch):
    monkeypatch.setattr(otel, "current_node", lambda: "current")
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hi", None, None)
    record.node = "explicit"
    logsetup._NodeFilter().filter(record)
    assert record.node == "explicit"


def test_node_stamp_is_empty_rather_than_raising_when_telemetry_is_off():
    """Telemetry is opt-in; with it off, current_node has no state to read. A
    logging filter that raised would break logging itself, not just telemetry."""
    otel._active = None
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hi", None, None)
    assert logsetup._NodeFilter().filter(record) is True
    assert record.node == ""


def test_sdk_internal_logs_are_kept_out_of_the_otel_handler():
    """Without this the pipeline feeds itself: a collector that is down makes the
    exporter log a failure, which the handler queues, whose export fails, which
    logs... The console still shows them; only the path back into the exporter
    is cut."""
    drop = logsetup._DropOtelInternals()

    def rec(name):
        return logging.LogRecord(name, logging.ERROR, __file__, 1, "x", None, None)

    assert drop.filter(rec("opentelemetry.sdk._logs.export")) is False
    assert drop.filter(rec("opentelemetry.exporter.otlp")) is False
    # A workhorse or script record must still get through.
    assert drop.filter(rec("script.select_item")) is True
    assert drop.filter(rec("workhorse.main")) is True


def test_script_logger_is_named_per_node():
    assert logsetup.script_logger("select_item").name == "script.select_item"


def test_attach_and_detach_otel_are_safe_without_a_provider():
    """Telemetry off is the default path: attach must no-op rather than explode,
    and detach must be callable regardless — end_run calls it unconditionally."""
    root, saved = _fresh_root()
    try:
        logsetup.attach_otel(None)
        assert root.handlers == []
        logsetup.detach_otel()  # must not raise
    finally:
        root.handlers[:] = saved


def test_detach_removes_the_handler_before_the_provider_dies():
    """end_run shuts the LoggerProvider down; a handler left attached would hand
    later records to a dead exporter on the way out of the process."""
    root, saved = _fresh_root()
    sentinel = logging.NullHandler()
    try:
        logsetup._otel_handler = sentinel
        root.addHandler(sentinel)
        logsetup.detach_otel()
        assert sentinel not in root.handlers
        assert logsetup._otel_handler is None
    finally:
        root.handlers[:] = saved
        logsetup._otel_handler = None


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
