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
- does: binds the console handler's stream to the setup-time `sys.stderr`, not a per-record lookup, so log lines still reach the terminal while an in-process script redirects the live standard streams to capture JSON
- verify: emitted(event="log record still visible while stdout/stderr are redirected to a JSON capture buffer", count=1)
- does: raises noisy third-party logger thresholds to `WARNING`
- does: returns without adding another console handler when already configured
- verify: unchanged(subject="the root logger's handler collection")
- returns: `None`
- code: `workhorse/workhorse/logsetup.py::setup`
- tests: `workhorse/tests/test_logsetup.py::test_console_handler_survives_the_script_stdout_capture`

### attach_otel
- sig: `attach_otel(logger_provider: Any) -> None`
- does: adds one OTLP logging handler with node, repository, and exporter-recursion filters when a provider is supplied
- verify: created(subject="the root logger's OTLP logging handler")
- does: leaves logging unchanged when the provider is absent, the handler is already attached, or the logging SDK import is unavailable
- verify: unchanged(subject="the root logger's handler collection")
- does: drops any record whose logger name starts with `opentelemetry` from the OTel handler, so a failing collector cannot feed its own diagnostics back into the export queue
- verify: count(subject="records dropped because their logger name starts with opentelemetry", equals=2)
- returns: `None`
- code: `workhorse/workhorse/logsetup.py::attach_otel`
- tests: `workhorse/tests/test_logsetup.py::test_sdk_internal_logs_are_kept_out_of_the_otel_handler`, `workhorse/tests/test_logsetup.py::test_attach_and_detach_otel_are_safe_without_a_provider`

### detach_otel
- sig: `detach_otel() -> None`
- does: removes the attached OTLP handler
- verify: removed(subject="the root logger's OTLP logging handler")
- does: clears the attachment reference
- verify: removed(subject="the OTLP handler attachment reference")
- does: runs safely when no provider has ever been attached, so `end_run` can call it unconditionally
- verify: exit_status(code=0)
- returns: `None`
- code: `workhorse/workhorse/logsetup.py::detach_otel`
- tests: `workhorse/tests/test_logsetup.py::test_detach_removes_the_handler_before_the_provider_dies`, `workhorse/tests/test_logsetup.py::test_attach_and_detach_otel_are_safe_without_a_provider`

### script_logger
- sig: `script_logger(node_id: str) -> logging.Logger`
- does: returns the logger named `script.<node_id>` for an in-process script node
- returns: a standard-library logger that propagates to the configured root handlers
- verify: emitted(event="script logger record at configured root handlers", count=1)
- code: `workhorse/workhorse/logsetup.py::script_logger`
- tests: `workhorse/tests/test_logsetup.py::test_script_logger_is_named_per_node`

### _NodeFilter
- sig: `_NodeFilter() -> logging.Filter`
- does: stamps every record with the value of `otel.current_node()` at emit time, since spans are never made current and trace context alone cannot join a log to its node
- verify: json_path(path="record.node", equals="select_item")
- does: preserves an existing `node` attribute on the record when one is already set
- verify: unchanged(subject="an explicit record.node attribute")
- does: stamps `node` as the empty string when telemetry is off, rather than raising and breaking logging
- verify: json_path(path="record.node", equals="")
- code: `workhorse/workhorse/logsetup.py::_NodeFilter`
- tests: `workhorse/tests/test_logsetup.py::test_records_are_stamped_with_the_current_node`, `workhorse/tests/test_logsetup.py::test_an_explicit_node_is_not_overwritten`, `workhorse/tests/test_logsetup.py::test_node_stamp_is_empty_rather_than_raising_when_telemetry_is_off`

### _DropOtelInternals
- sig: `_DropOtelInternals() -> logging.Filter`
- does: filters records whose logger name starts with `opentelemetry` so the OTel handler does not feed the exporter's own diagnostics back into the export queue
- verify: absent(subject="opentelemetry records reaching the OTel handler")
- code: `workhorse/workhorse/logsetup.py::_DropOtelInternals`
- tests: `workhorse/tests/test_logsetup.py::test_sdk_internal_logs_are_kept_out_of_the_otel_handler`
