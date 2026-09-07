---
type: concept
slug: telemetry-documentation-scope
title: Telemetry documentation scope
---
# Telemetry documentation scope

`workhorse/workhorse/otel.py::OtelSettings` is the immutable value built once from
the environment at the run edge and then supplied to `TelemetryHost`. It has no
alternative settings implementation: the two concepts that cite it describe different
reader tasks rather than competing runtime paths.

Use [telemetry settings selection](telemetry-settings-selection.md) to configure the
telemetry gate and export cadence. Use [OpenTelemetry
instrumentation](telemetry-instrumentation.md) to understand the facade's active and
inert adapters, exported spans, metrics, logs, and fail-soft lifecycle. Neither concept
supersedes the other; both remain current because configuring settings and understanding
instrumentation are separate tasks.

- rule: use telemetry settings selection for `OtelSettings` environment configuration and telemetry instrumentation for runtime telemetry behavior; neither is a replacement for the other
