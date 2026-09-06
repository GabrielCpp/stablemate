---
type: concept
slug: logging-setup
title: Console and OpenTelemetry logging
---
# Console and OpenTelemetry logging

Workhorse configures the root logger once with a console handler bound to the setup-time
`sys.stderr`, preserving terminal output even while an in-process script redirects the live
standard streams to capture JSON. The handler formats `[logger] message`, applies the configured
`WORKHORSE_LOG_LEVEL` (default `INFO`), and raises noisy third-party logger thresholds to
`WARNING`.

When telemetry has a logger provider, a second handler ships root records to OTLP. It stamps the
current node and repository snapshot at emission time, excludes `opentelemetry` diagnostics from
the exporter path to prevent recursive failure logging, and is removed before provider shutdown.
Script nodes receive a logger named `script.<node_id>`; their records use the same root handlers
and run correlation as engine records.

- code: `workhorse/workhorse/logsetup.py::setup`
- code: `workhorse/workhorse/logsetup.py::attach_otel`
- code: `workhorse/workhorse/logsetup.py::detach_otel`
- code: `workhorse/workhorse/logsetup.py::script_logger`
- code: `workhorse/workhorse/logsetup.py::_NodeFilter`
- code: `workhorse/workhorse/logsetup.py::_HeadFilter`
- code: `workhorse/workhorse/logsetup.py::_DropOtelInternals`
- tests: `workhorse/tests/test_otel.py`

## Methods

### setup
- sig: `setup() -> None`
- does: configures the root console handler once
- verify: created(subject="the root logger's console handler")
- does: raises noisy third-party logger thresholds to `WARNING`
- does: returns without adding another console handler when already configured
- verify: unchanged(subject="the root logger's handler collection")
- returns: `None`
- code: `workhorse/workhorse/logsetup.py::setup`

### attach_otel
- sig: `attach_otel(logger_provider: Any) -> None`
- does: adds one OTLP logging handler with node, repository, and exporter-recursion filters when a provider is supplied
- verify: created(subject="the root logger's OTLP logging handler")
- does: leaves logging unchanged when the provider is absent, the handler is already attached, or the logging SDK import is unavailable
- verify: unchanged(subject="the root logger's handler collection")
- returns: `None`
- code: `workhorse/workhorse/logsetup.py::attach_otel`

### detach_otel
- sig: `detach_otel() -> None`
- does: removes the attached OTLP handler
- verify: removed(subject="the root logger's OTLP logging handler")
- does: clears the attachment reference
- verify: removed(subject="the OTLP handler attachment reference")
- returns: `None`
- code: `workhorse/workhorse/logsetup.py::detach_otel`

### script_logger
- sig: `script_logger(node_id: str) -> logging.Logger`
- does: returns the logger named `script.<node_id>` for an in-process script node
- returns: a standard-library logger that propagates to the configured root handlers
- verify: emitted(event="script logger record at configured root handlers", count=1)
- code: `workhorse/workhorse/logsetup.py::script_logger`
