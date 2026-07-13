---
type: concept
slug: sidecar-serving-loop
title: Sidecar serving loop
---
# Sidecar serving loop

Sidecar serving loop is the async websocket dial-and-retry layer started by the
[sidecar live session runner](sidecar-live-session-runner.md). It connects the
container-side sidecar to the host [websocket-sidecar](../http/groom.md#websocket-sidecar)
endpoint, hands each accepted socket to the connected session layer, and returns
the reserved reload exit code when a host-issued `reload` [sidecar websocket
frame](../sidecar-websocket-frame.md) asks the container entrypoint to restart the
sidecar. Ordinary socket drops are not terminal; they cause a reconnect and a new
session advertisement for [sidecar live sessions](../sidecar-live-sessions.md).

- code: groom/groom/sidecar.py::_serve
- verify: groom/tests/test_sidecar_session.py::test_serve_returns_reload_code_when_session_requests_reload

## Contract

- sig: `async _serve() -> int`
- input: no call arguments; target host and port come from the sidecar process
  environment as `GROOM_HOST` and `GROOM_PORT`, defaulting upstream to
  `host.docker.internal` and `8787`.
- uri: websocket URL `ws://{GROOM_HOST}:{GROOM_PORT}/sidecar`; no path, query,
  authentication header, or request body is added by this layer.
- output: returns integer `3` only when the connected session reports a reload
  request; returns `0` only if the websocket connector's async iterator ends
  without yielding another socket.
- effects: opens outbound websocket client connections to the host groom service,
  delegates each connected socket to the session layer, closes the current socket
  best-effort before returning on reload, and performs no filesystem reads,
  inotify setup, frame parsing, or frame emission itself.
- reconnect rule: a normal websocket close from the connected session is swallowed
  and the connector loop continues, allowing the sidecar to reconnect and
  re-advertise state instead of exiting the process.
- reload rule: a session-level reload request is terminal for this serving loop;
  the current socket is closed if possible and the reserved reload exit code is
  returned to the caller.
- errors: exceptions other than websocket close and reload request propagate to
  the caller; socket-close errors during the reload cleanup are suppressed.
- liveness: groom being unavailable is not represented as a process error by this
  layer; the connector owns retry/backoff behavior and yields sockets when a
  connection is available.

## Algorithm

1. Build the sidecar websocket URL from the configured host and port.
2. Enter the websocket connector's async iteration over live connections.
3. For each connected websocket, run exactly one [sidecar connected
   session](sidecar-connected-session.md) on that socket.
4. If the connected session raises a reload request, close the socket
   best-effort, return `3`, and stop reconnecting.
5. If the connected session ends because the socket closed, ignore that close and
   continue to the next yielded connection.
6. If the connector iteration ever finishes without a reload, return `0`.

## Exit Codes

- `0`: the connector produced no further sockets and no reload request occurred;
  this is the non-reload normal completion result consumed by the runner.
- `3`: reserved [sidecar live sessions](../sidecar-live-sessions.md) reload code;
  the container entrypoint interprets this as recopy-and-relaunch for the
  sidecar process.

## Deeper Calls

- [Sidecar connected session](sidecar-connected-session.md) owns the
  per-connection hello frame, inotify watches, outbound progress/blocked queue,
  inbound RPC dispatch, and reload detection for one connected websocket.
