---
type: concept
slug: sidecar-error
title: Sidecar error
---
# Sidecar error

Sidecar error is the host-side failure signal for a data-plane RPC attempted through a [sidecar connection](sidecar-connection.md). The [Groom sidecar hub module](groom-sidecar-hub-module.md) defines it as the soft-failure exception shared by connection RPCs, [sidecar connection registry](sidecar-connection-registry.md) displacement cleanup, and socket-close cleanup. The [sidecar RPC helper](sidecar-rpc-helper.md) catches this exception and turns it into `None` so HTTP file, file-content, and diff invocations can fall back to Docker volume readers without exposing sidecar transport failures as endpoint-specific errors. The error is produced by the [sidecar connection](sidecar-connection.md) when an outgoing [sidecar websocket frame](../sidecar-websocket-frame.md) cannot complete or when an incoming RPC result reports failure.

- code: groom/groom/sidecar_hub.py::SidecarError

The implementation is covered by `groom/tests/test_sidecar_hub.py::test_rpc_error_result_raises_sidecar_error`,
`groom/tests/test_sidecar_hub.py::test_rpc_times_out_when_no_reply`,
`groom/tests/test_sidecar_hub.py::test_register_displaces_and_fails_prior_connection`,
`groom/tests/test_sidecar_hub.py::test_unregister_only_removes_current_connection`, and
`groom/tests/test_app.py::test_files_falls_back_to_volume_when_socket_errors`.

## Contract

The class carries no structured data beyond the standard exception argument tuple, and neither
constructing nor catching it touches the sidecar connection registry, pending futures, workflow
state, or dashboard clients — those are the responsibility of the code that raises or handles it.
Every current producer happens to construct it with one human-readable message string; nothing in
the class enforces that shape, so it carries no stable error code, status code, correlation-id
field, method field, container-id field, or retry hint of its own.

- type: exception class for unavailable or failed host-to-sidecar RPCs.
- inheritance: derives directly from the standard exception type and adds no service-owned methods, class attributes, class-level constants, or instance fields.
- purpose: separates expected sidecar data-plane unavailability from endpoint errors so callers can preserve successful HTTP responses and use slower Docker-volume fallbacks.
- scope: applies only to host-issued RPCs over a live sidecar socket and pending RPCs owned by that socket; it is not used for browser dashboard websocket failures, Docker fallback failures, request parsing failures, or unexpected programmer errors.
- delivery: direct `rpc` failures raise to the awaiting caller, while [method-resolve](sidecar-connection.md#method-resolve) and [method-fail-all](sidecar-connection.md#method-fail-all) place the same exception type onto already-pending futures so in-flight callers observe the soft failure at their await point.
- catch boundary: the app-level helper catches this exception type as the expected sidecar-unavailable path; it does not catch arbitrary exceptions from Docker fallbacks, endpoint parsing, or unexpected non-sidecar failures.
- producer boundary: the class itself has no logic for selecting fallback behavior; producer methods decide when to instantiate it and consumer helpers decide whether to suppress it.
- subclass boundary: no Groom-owned subclass or alternate implementation exists; code that needs this soft-failure channel uses this exact class.

On the wire, the exception has no counterpart: it is a purely host-side object with no
serialization to a websocket or HTTP response. Its message text is the only part that can
trace back to the sidecar side, since [method-resolve](sidecar-connection.md#method-resolve)
constructs it from a sidecar `rpc_result.error` string (or the fallback text `sidecar reported
an error` when the sidecar sends none) before wrapping it as the exception's argument on the
host.

## Raising Conditions

When an RPC frame cannot be sent through the sidecar socket, the resulting error has a
`send failed: ...` message and preserves the underlying exception as its cause.

- consistency: field-pending — a socket-send failure removes the RPC's [pending entry](sidecar-connection.md#field-pending) before the caller observes `SidecarError`.
- verify: removed(subject="the sent RPC's pending entry")
- timeout: when no matching `rpc_result` arrives before the call timeout, the connection raises this error with a message naming the method and timeout seconds; the pending request is then removed so late replies are ignored.
- sidecar error result: when a sidecar returns `ok=false` for an RPC result, the connection completes the waiting request with this error, using the sidecar-provided error text or `sidecar reported an error` when the result has no text.
- superseded connection: when a new connection registers for the same container, all unresolved requests on the previous connection are completed with this error and the message `superseded by a new sidecar connection`.
- closed connection: when a current or stale connection is unregistered on socket close, every unresolved request owned by that connection is completed with this error and the message `sidecar connection closed`.
- non-producing cases: a missing registry entry, a reload-send failure, malformed sidecar websocket input, Docker fallback failure, and ordinary dashboard websocket disconnect are not required to instantiate this error class.

## Consumer Semantics

- fallback: file-list, file-content, and diff endpoint handlers receive `None` from the RPC helper after this error and then use their Docker-volume read paths when the workflow has a workspace volume.
- consistency: sidecar-rpc-helper — the [sidecar RPC helper](sidecar-rpc-helper.md) catches `SidecarError` as a soft data-plane miss and returns `None` to the endpoint handler.
- verify: http_status(code=200, path="/files/abc123")
- consistency: workspace-file-list-data — after a `SidecarError`, the file-list handler returns its normal HTTP success response from the Docker-volume fallback rather than propagating the sidecar failure to the browser.
- verify: http_status(code=200, path="/files/abc123")
- cleanup: sidecar connection methods remove or clear affected pending RPC entries before callers observe completion, so duplicate or late `rpc_result` frames do not re-raise this error.
- reload boundary: sidecar reload sends may fail, but reload handling treats any send exception as best-effort unavailability and does not require this specific exception type.
- wire boundary: sidecar-side read failures remain `rpc_result` frames with `ok=false` and an error string until the host connection resolves them; only the host-side connection turns that wire error into this exception.

## Exception Shape

`SidecarError` declares no custom fields. Its consumers use standard exception text and metadata
rather than a service-defined structured error payload.

- args: standard exception argument tuple; current service producers pass exactly one message string.
- message: human-readable reason suitable for internal logs or tests, not a stable wire format.
- cause: send-failure and timeout cases preserve the lower-level exception as the exception cause; sidecar-reported, superseded, and closed-connection cases have no required cause.
- methods: no custom methods; behavior is defined by the raising and catching sites, not by instance operations on the error object.
- equality: no service-owned equality semantics; tests and callers compare by type and, where needed, message text.

## Service-Owned Members

- custom-fields: none; the concept intentionally exposes no Groom-owned field nodes beyond standard exception state.
- custom-methods: none; the class inherits standard exception behavior and defines no Groom-owned methods to descend into.
- implementations: no Groom-owned subclasses or alternate implementations are defined; the service uses this single exception class as the sidecar soft-failure signal.
- public-members: no public service-owned members are exported by this class beyond the class object itself; there are therefore no nested `method` or `field` sections to model for this concept.
