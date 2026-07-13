---
type: concept
slug: sidecar-error
title: Sidecar error
---
# Sidecar error

Sidecar error is the host-side failure signal for a data-plane RPC attempted through a [sidecar connection](sidecar-connection.md). The [Groom sidecar hub module](groom-sidecar-hub-module.md) defines it as the soft-failure exception shared by connection RPCs, [sidecar connection registry](sidecar-connection-registry.md) displacement cleanup, and socket-close cleanup. The [sidecar RPC helper](sidecar-rpc-helper.md) catches this exception and turns it into `None` so HTTP file, file-content, and diff invocations can fall back to Docker volume readers without exposing sidecar transport failures as endpoint-specific errors. The error is produced by the [sidecar connection](sidecar-connection.md) when an outgoing [sidecar websocket frame](../sidecar-websocket-frame.md) cannot complete or when an incoming RPC result reports failure.

- code: groom/groom/sidecar_hub.py::SidecarError
- verify: groom/tests/test_sidecar_hub.py::test_rpc_error_result_raises_sidecar_error,
  groom/tests/test_sidecar_hub.py::test_rpc_times_out_when_no_reply,
  groom/tests/test_sidecar_hub.py::test_register_displaces_and_fails_prior_connection,
  groom/tests/test_sidecar_hub.py::test_unregister_only_removes_current_connection,
  groom/tests/test_app.py::test_files_falls_back_to_volume_when_socket_errors

## Contract

- type: exception class for unavailable or failed host-to-sidecar RPCs.
- inheritance: derives directly from the standard exception type and adds no service-owned methods, class attributes, class-level constants, or instance fields.
- purpose: separates expected sidecar data-plane unavailability from endpoint errors so callers can preserve successful HTTP responses and use slower Docker-volume fallbacks.
- scope: applies only to host-issued RPCs over a live sidecar socket and pending RPCs owned by that socket; it is not used for browser dashboard websocket failures, Docker fallback failures, request parsing failures, or unexpected programmer errors.
- consumer: caught by the [sidecar RPC helper](sidecar-rpc-helper.md), which treats it as a soft data-plane miss and returns `None` to the endpoint handler.
- state: carries no structured data beyond the standard exception argument tuple; creating or catching it does not mutate the sidecar connection registry, pending futures, workflow state, or dashboard clients.
- construction: every current producer creates the error with one human-readable message string; there is no stable error code, status code, correlation-id field, method field, container-id field, or retry hint on the exception object.
- delivery: direct `rpc` failures raise to the awaiting caller, while [method-resolve](sidecar-connection.md#method-resolve) and [method-fail-all](sidecar-connection.md#method-fail-all) place the same exception type onto already-pending futures so in-flight callers observe the soft failure at their await point.
- catch boundary: the app-level helper catches this exception type as the expected sidecar-unavailable path; it does not catch arbitrary exceptions from Docker fallbacks, endpoint parsing, or unexpected non-sidecar failures.
- producer boundary: the class itself has no logic for selecting fallback behavior; producer methods decide when to instantiate it and consumer helpers decide whether to suppress it.
- subclass boundary: no Groom-owned subclass or alternate implementation exists; code that needs this soft-failure channel uses this exact class.
- wire boundary: the exception is never serialized as a websocket or HTTP response; only its message may originate from a sidecar `rpc_result.error` string before being wrapped on the host.

## Raising Conditions

- send failure: when an RPC frame cannot be sent through the sidecar socket, the connection removes that request from its pending map and raises this error with a `send failed: ...` message while preserving the underlying exception as the cause.
- timeout: when no matching `rpc_result` arrives before the call timeout, the connection raises this error with a message naming the method and timeout seconds; the pending request is then removed so late replies are ignored.
- sidecar error result: when a sidecar returns `ok=false` for an RPC result, the connection completes the waiting request with this error, using the sidecar-provided error text or `sidecar reported an error` when the result has no text.
- superseded connection: when a new connection registers for the same container, all unresolved requests on the previous connection are completed with this error and the message `superseded by a new sidecar connection`.
- closed connection: when a current or stale connection is unregistered on socket close, every unresolved request owned by that connection is completed with this error and the message `sidecar connection closed`.
- non-producing cases: a missing registry entry, a reload-send failure, malformed sidecar websocket input, Docker fallback failure, and ordinary dashboard websocket disconnect are not required to instantiate this error class.

## Consumer Semantics

- fallback: file-list, file-content, and diff endpoint handlers receive `None` from the RPC helper after this error and then use their Docker-volume read paths when the workflow has a workspace volume.
- response preservation: endpoint handlers do not return this error text to browsers; sidecar failure keeps the request on the normal HTTP success path unless the fallback path itself cannot produce content.
- cleanup: sidecar connection methods remove or clear affected pending RPC entries before callers observe completion, so duplicate or late `rpc_result` frames do not re-raise this error.
- reload boundary: sidecar reload sends may fail, but reload handling treats any send exception as best-effort unavailability and does not require this specific exception type.
- wire boundary: sidecar-side read failures remain `rpc_result` frames with `ok=false` and an error string until the host connection resolves them; only the host-side connection turns that wire error into this exception.

## Exception Shape

- args: standard exception argument tuple; current service producers pass exactly one message string.
- message: human-readable reason suitable for internal logs or tests, not a stable wire format.
- cause: send-failure and timeout cases preserve the lower-level exception as the exception cause; sidecar-reported, superseded, and closed-connection cases have no required cause.
- fields: no custom fields; consumers must not depend on structured attributes beyond standard exception text and standard exception metadata.
- methods: no custom methods; behavior is defined by the raising and catching sites, not by instance operations on the error object.
- equality: no service-owned equality semantics; tests and callers compare by type and, where needed, message text.

## Service-Owned Members

- custom-fields: none; the concept intentionally exposes no Groom-owned field nodes beyond standard exception state.
- custom-methods: none; the class inherits standard exception behavior and defines no Groom-owned methods to descend into.
- implementations: no Groom-owned subclasses or alternate implementations are defined; the service uses this single exception class as the sidecar soft-failure signal.
- public-members: no public service-owned members are exported by this class beyond the class object itself; there are therefore no nested `method` or `field` sections to model for this concept.
