---
type: concept
slug: sidecar-residual-http-push-helper
title: Sidecar residual HTTP push helper
---
# Sidecar residual HTTP push helper

Sidecar residual HTTP push helper is the shared producer used by residual
`groom-sidecar` HTTP notices before they reach the [groom server](../http/groom.md)
push endpoints. It is reached from the [`groom-sidecar-root`](../groom-sidecar.md#groom-sidecar-root)
exit-notice invocation and by the progress/blocked residual paths described in
[sidecar protocol](../sidecar-protocol.md); it turns [sidecar identity data](../sidecar-identity-data.md)
plus one event payload into a best-effort JSON POST for [progress push payload](../progress-push-payload.md),
[blocked push payload](../blocked-push-payload.md), or [exited push payload](../exited-push-payload.md).

- code: groom/groom/sidecar.py::_push
- verify: groom/tests/test_sidecar.py::test_push_progress_posts_expected_shape
- verify: groom/tests/test_sidecar.py::test_push_blocked_posts_expected_shape
- verify: groom/tests/test_sidecar.py::test_push_exited_posts_expected_shape
- verify: groom/tests/test_sidecar.py::test_push_exited_is_silent_when_groom_is_unreachable
- verify: groom/tests/test_sidecar.py::test_push_is_silent_when_groom_is_unreachable
- verify: groom/tests/test_sidecar.py::test_push_is_silent_on_any_unexpected_exception
- refs: [sidecar identity data](../sidecar-identity-data.md), [progress push payload](../progress-push-payload.md), [blocked push payload](../blocked-push-payload.md), [exited push payload](../exited-push-payload.md), [sidecar protocol](../sidecar-protocol.md)

## Contract

- input-path: absolute route path string beginning with the host-side push route,
  such as `/push/progress`, `/push/blocked`, or `/push/exited`; the helper appends
  it exactly after the configured host and port without validation or escaping.
- caller paths: the first-party residual wrappers call this helper with exactly
  `/push/progress`, `/push/blocked`, or `/push/exited`; no other first-party
  residual HTTP route is produced by `groom-sidecar`.
- input-payload: JSON-serializable object fields specific to the notice being
  sent; keys in this payload override same-named sidecar identity keys before
  serialization because event payload fields are merged after identity fields.
- payload variants: progress supplies only `current_node`, blocked supplies
  `file_path` and `question`, and exited supplies only `exit_code` before the
  shared identity fields are merged.
- identity: each request body includes [sidecar identity data](../sidecar-identity-data.md)
  fields from the sidecar process before event-specific fields are applied:
  `container_id`, `name`, `repo_name`, and `repo_branch`.
- endpoint: sends to `http://{GROOM_HOST}:{GROOM_PORT}{path}`; `GROOM_HOST`
  defaults to `host.docker.internal`, and `GROOM_PORT` defaults to `8787` when the
  sidecar module is imported without environment overrides.
- media: serializes the merged object as UTF-8 JSON and declares
  `Content-Type: application/json` on the request.
- method: performs exactly one HTTP `POST` attempt; it does not retry, redirect
  itself, enqueue for later, or emit any CLI/stdout/stderr output.
- timeout: passes the module's `PUSH_TIMEOUT` value to the HTTP call; that value
  comes from the `GROOM_PUSH_TIMEOUT` environment variable, defaults to `1.0`
  seconds, and is parsed as a float when the sidecar module is imported.
- success-result: returns `None` after the HTTP response object has been opened
  and closed; response body, response headers, and successful response status are
  not inspected by this helper.
- failure-result: exceptions raised while opening the URL or closing the response
  are swallowed, so an unreachable groom process, refused connection, HTTP-open
  failure, or close failure does not block or change workflow-side behavior.
- uncaught-errors: errors that occur before the HTTP attempt, including a
  non-JSON-serializable payload or request-construction failure, are outside the
  fire-and-forget catch region and may propagate to the caller; an invalid
  `GROOM_PUSH_TIMEOUT` value prevents the sidecar module from importing before
  this helper can run.

## Algorithm

1. Build [sidecar identity data](../sidecar-identity-data.md) for the current
   process.
2. Merge the identity object with the caller's event payload, letting payload
   keys win on collision.
3. Serialize the merged object to UTF-8 JSON bytes.
4. Build the target URL from the configured groom host, configured groom port,
   and caller-supplied path.
5. Create one JSON `POST` request for that URL.
6. Open the request with the configured push timeout and immediately close the
   returned response object.
7. If the HTTP open or response close raises an exception, suppress it and return
   `None`.

## Methods

### method-_push

- sig: `_push(path: str, payload: dict) -> None`
- abstract: false
- raises: none intentionally raised for HTTP open or response-close failures;
  JSON serialization, request construction, malformed imported configuration,
  and other errors before the guarded HTTP open are not normalized by the helper.
- input: an absolute host-side route path string and a JSON-serializable event
  payload dictionary.
- output: always returns `None` on the normal path and on suppressed HTTP-open or
  response-close failures.
- effects: creates one UTF-8 JSON request body, attempts one HTTP `POST` to the
  configured groom host and port, closes an opened response object, and performs
  no retry, queueing, logging, stdout/stderr output, workflow mutation, or local
  filesystem mutation.
- calls: [sidecar identity data](../sidecar-identity-data.md) production and
  standard-library JSON and HTTP request/open helpers.
- algorithm:
  1. Read current sidecar identity fields.
  2. Merge identity fields before event payload fields so event keys win on
     collision.
  3. JSON-serialize the merged object and encode it as UTF-8 bytes.
  4. Build `http://{GROOM_HOST}:{GROOM_PORT}{path}` exactly from the imported
     configuration values and caller-provided path.
  5. Create one `POST` request with `Content-Type: application/json`.
  6. Open the request with `PUSH_TIMEOUT` and close the returned response.
  7. Suppress any exception raised by the HTTP open or response close.

### method-push-progress

- sig: `push_progress(current_node: str = "") -> None`
- abstract: false
- raises: same producer-side propagation boundary as [method-_push](#method-_push).
- input: current workhorse node id or an empty string when no current node is
  known.
- output: returns `None`; it does not report whether groom accepted, rejected, or
  received the notice.
- effects: delegates one [progress push payload](../progress-push-payload.md)
  producer call to [method-_push](#method-_push) with endpoint path
  `/push/progress` and payload key `current_node`.

### method-push-blocked

- sig: `push_blocked(file_path: str, question: str) -> None`
- abstract: false
- raises: same producer-side propagation boundary as [method-_push](#method-_push).
- input: workspace-relative awaiting gate file path and extracted operator
  question text.
- output: returns `None`; it does not report whether groom accepted, rejected, or
  received the notice.
- effects: delegates one [blocked push payload](../blocked-push-payload.md)
  producer call to [method-_push](#method-_push) with endpoint path
  `/push/blocked` and payload keys `file_path` and `question`.

### method-push-exited

- sig: `push_exited(exit_code: int) -> None`
- abstract: false
- raises: same producer-side propagation boundary as [method-_push](#method-_push).
- input: integer workflow process exit code supplied by the one-shot
  `groom-sidecar --exit-code` invocation after workhorse returns.
- output: returns `None`; it does not report whether groom accepted, rejected, or
  received the notice.
- effects: delegates one [exited push payload](../exited-push-payload.md)
  producer call to [method-_push](#method-_push) with endpoint path
  `/push/exited` and payload key `exit_code`.

## Deeper Calls

- [Sidecar identity data](../sidecar-identity-data.md) supplies the shared
  sidecar identity fields merged into every residual push body.
- [Progress push payload](../progress-push-payload.md), [blocked push payload](../blocked-push-payload.md),
  and [exited push payload](../exited-push-payload.md) are the three first-party
  residual request shapes produced through this helper.
- The helper's remaining callees are standard-library JSON and HTTP functions;
  the identity producer calls only standard-library process, socket, and
  environment readers. There are no undocumented first-party deeper layers below
  this item.
