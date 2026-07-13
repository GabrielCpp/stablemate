---
type: concept
slug: sidecar-live-session-runner
title: Sidecar live session runner
---
# Sidecar live session runner

Sidecar live session runner is the `groom-sidecar` default-mode bridge from the
[`groom-sidecar-root`](../groom-sidecar.md#groom-sidecar-root) invocation into
[sidecar live sessions](../sidecar-live-sessions.md). It starts the sidecar's
[sidecar serving loop](sidecar-serving-loop.md), waits for that loop to finish,
and converts any non-zero loop result into the process exit observed by the
workflow-container entrypoint.

- code: groom/groom/sidecar.py::run
- verify: groom/tests/test_sidecar_session.py::test_run_maps_reload_code_to_systemexit

## Contract

- input: no call arguments; host, port, workspace, runs, and timeout settings are
  inherited from the sidecar process environment and consumed by the async serving
  layer it starts.
- output: returns `None` only when the async serving layer returns exit code `0`.
- effects: starts and owns one blocking run of the async sidecar serving layer for
  the current process; performs no filesystem reads, network I/O, or websocket
  frame emission itself before delegating.
- exit: raises `SystemExit(exit_code)` when the async serving layer returns any
  truthy integer exit code; the numeric value is preserved exactly.
- errors: exceptions raised by the async serving layer before it returns propagate
  out of the runner; only returned non-zero exit codes are converted into
  `SystemExit`.
- lifecycle: intended as the terminal call for default `groom-sidecar` mode; it
  does not restart itself, retry command parsing, or handle query/exit-notice
  modes.

## Algorithm

1. Start the sidecar serving coroutine and wait until it returns an integer exit
   code.
2. If the exit code is zero or otherwise falsey, return normally to the CLI
   invocation.
3. If the exit code is non-zero, raise `SystemExit` with that same value so the
   surrounding process exits with the sidecar serving layer's requested status.

## Exit Codes

- `0`: the serving layer ended without requesting a special process status; the
  runner returns normally.
- `3`: reserved sidecar reload status from [sidecar live sessions](../sidecar-live-sessions.md);
  the runner preserves it as `SystemExit(3)` so the entrypoint can restart the
  sidecar process.
- other non-zero integer: preserved as `SystemExit(value)` for any future serving
  layer result that intentionally asks the process to exit non-successfully.

## Deeper Calls

- [Sidecar serving loop](sidecar-serving-loop.md) (`groom/groom/sidecar.py::_serve`)
  owns the websocket connection loop, reconnect behavior, session handoff, and
  reload-code decision for the live sidecar data plane.
