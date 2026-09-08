---
type: cli
slug: groom-sidecar
title: groom-sidecar
---
# groom-sidecar

- binary: groom-sidecar
- code: groom/groom/cli.py::sidecar_main

The `groom-sidecar` CLI is the in-container companion executable for the
[groom dashboard service](groom.md). It is separate from the host-side
[`groom`](groom-cli.md) CLI and is launched by the workflow container entrypoint
described in [sidecar autostart](sidecar-autostart.md). The
[`Groom CLI entrypoints module`](concepts/groom-cli-entrypoints-module.md) owns
both executable roots. Its root command has no subcommands: root-level flags
select between the default long-running [sidecar live session](sidecar-live-sessions.md),
a legacy one-shot snapshot for the [sidecar protocol](sidecar-protocol.md), or a
post-workflow exited notice. The executable delegates those runtime modes to the
[Groom sidecar module](concepts/groom-sidecar-module.md), which owns the local
snapshot readers, residual push producers, websocket session, sidecar RPC data
plane, and reload exit handoff.

Its query behavior is exercised by
`groom/tests/test_sidecar.py::test_cli_query_prints_snapshot_json_and_does_not_watch`,
and its default session behavior by
`groom/tests/test_sidecar_session.py::test_cli_sidecar_default_runs_session`.

Invalid flags, non-integer `--exit-code` values, and unexpected positional
arguments are rejected by the argument parser before any sidecar work starts and
exit through argparse's standard usage/error path.

## Commands


### root
- usage: `groom-sidecar [--query] [--exit-code EXIT_CODE]`
- parent: [groom-sidecar](#groom-sidecar)
- flags: two optional root-level mode selectors; absent flags select the default
  long-running [sidecar live session](sidecar-live-sessions.md).
  - `--query`
    - type: boolean
    - required: false
    - default: `false`
    - mode: one-shot snapshot query.
    - applies: host pull paths and diagnostic calls that need current in-container
      sidecar state without starting the watcher/session loop.
    - Prints this container's current sidecar snapshot as JSON on stdout
      and exits without starting the watch/session loop. When combined with
      `--exit-code`, query mode wins because it is evaluated first.
  - `--exit-code EXIT_CODE`
    - type: integer
    - required: false
    - default: `null`
    - mode: one-shot post-workflow exited notice.
    - applies: the workflow container entrypoint after the workflow process has
      returned and the live sidecar session is being torn down.
    - Sends one best-effort `exited` notice carrying the workflow process exit
      code to the host groom service and exits. The workflow entrypoint uses this
      after workhorse returns, when the live sidecar session is being torn down.
- args: no positional arguments are accepted.
  - none: `groom-sidecar` accepts no positional arguments.
- does: parses the root flags, chooses exactly one runtime mode, and invokes
  [`groom-sidecar-root`](#groom-sidecar-root) for the accepted command line.
  - Invokes [`groom-sidecar-root`](#groom-sidecar-root) after parsing the root
    flags.
- errors: unknown flags make argparse exit before sidecar module work starts.
- verify: exit_status(code=2)
- errors: unexpected positional arguments make argparse exit before sidecar
  module work starts.
- verify: exit_status(code=2)
- errors: a non-integer `--exit-code` value makes argparse exit before sidecar
  module work starts.
- verify: exit_status(code=2)
- errors: a runtime error from the selected sidecar mode propagates through the
  command dispatcher.
- verify: json_path(path="exception.type", equals="RuntimeError")
- exits: query mode returns after writing one JSON snapshot to stdout.
- verify: exit_status(code=0)
- exits: exit-notice mode returns after attempting one exited push.
- verify: exit_status(code=0)
- exits: default live-session mode keeps running until its session handler
  returns or raises its own process exit.
- verify: json_path(path="sidecar.run.call_count", equals=1)
- code: groom/groom/cli.py::sidecar_main
- detail: [sidecar live sessions](sidecar-live-sessions.md)

## Invocations

### groom-sidecar-root
- on: [root](#root)
- trigger: the container entrypoint or a host pull path runs `groom-sidecar`
  after the parser has accepted its root flags.
- when:
  - The command line contains no subcommand and no positional arguments.
  - `--query` is represented as a boolean flag and defaults to false.
  - `--exit-code` is either absent/null or an integer supplied by the
    entrypoint after the workflow process exits.
- does:
  - Parses the root flags before importing the sidecar module.
  - Parser errors do not load the sidecar runtime dependency set.
  - Imports the sidecar module only after parsing succeeds.
  - The default argument-error path is free of the sidecar runtime dependency
    set.
  - If importing the sidecar runtime module fails after successful parsing, the
    selected mode is never entered.
  - An import-time sidecar runtime failure propagates out of the command.
  - When `--query` is true, calls `groom/groom/sidecar.py::snapshot`.
  - Query mode serializes the returned [sidecar snapshot data](sidecar-snapshot-data.md)
    as JSON to stdout.
  - Query mode returns after writing its JSON snapshot.
  - Query mode does not start the exit-notice path.
  - Query mode does not start the live watch/session loop.
  - Query mode wins when `--query` and `--exit-code` are both supplied.
  - The query snapshot obtains the current node from the latest checkpoint.
  - The query snapshot obtains the terminal state from the latest run metadata.
  - The query snapshot obtains the open-gate list from a workspace scan.
  - The query snapshot returns exactly the keys `current_node`, `terminal`, and
    `gates`.
  - When `--query` is false and `--exit-code` is present, calls
    `groom/groom/sidecar.py::push_exited` with that integer exit code.
  - The exited notice path is best-effort.
  - Exit-notice mode returns after calling `groom/groom/sidecar.py::push_exited`.
  - Exit-notice mode does not start the live watch/session loop.
  - The exited notice path merges sidecar identity into the
    [exited push payload](exited-push-payload.md).
  - The exited push payload carries the supplied `exit_code` integer.
  - The exited notice posts its JSON body to `POST /push/exited` on the host
    groom service.
  - The [sidecar residual HTTP push helper](concepts/sidecar-residual-http-push-helper.md)
    serializes the merged object as UTF-8 JSON.
  - The residual HTTP push helper declares `Content-Type: application/json`.
  - The residual HTTP push helper targets the configured `GROOM_HOST` and
    `GROOM_PORT`.
  - The residual HTTP push helper makes exactly one `POST` attempt.
  - `GROOM_HOST` defaults to `host.docker.internal`.
  - `GROOM_PORT` defaults to `8787`.
  - The request declares a JSON content type.
  - The request uses `GROOM_PUSH_TIMEOUT` as its timeout.
  - `GROOM_PUSH_TIMEOUT` defaults to one second.
  - Connection failures are swallowed by the exited-notice path.
  - HTTP client errors raised by the HTTP open are swallowed by the exited-notice
    path.
  - Response-close errors are swallowed by the exited-notice path.
  - The exited-notice path returns normally after a swallowed push error.
  - A swallowed push error does not change the workflow process exit result.
  - When neither mode flag is selected, calls the
    [sidecar live session runner](concepts/sidecar-live-session-runner.md).
  - The live session runner hands synchronous command execution to the async
    websocket serving loop.
  - The live-session runner starts the async sidecar serving loop.
  - The live-session runner waits for the serving loop to complete.
  - The serving loop connects to the host [groom server](http/groom.md).
  - The serving loop advertises current state.
  - The serving loop watches the container's workspace/run mounts.
  - The serving loop serves the live sidecar data plane described by
    [sidecar live sessions](sidecar-live-sessions.md).
  - When the serving loop returns zero, the runner returns normally.
  - A zero return from the serving loop leaves the sidecar command with its
    normal success exit status.
  - When the serving loop returns a non-zero code, the runner raises a process
    exit with exactly that code.
  - The reserved reload code reaches the container entrypoint without CLI
    dispatcher translation.
  - Query mode returns normally after stdout is written.
  - Exit-notice mode returns normally after the push handler returns.
  - Default live-session mode returns only if the live session handler returns.
  - A sidecar reload request exits the process through that handler's reserved
    reload exit code, bypassing this bullet's normal-return path.
- emits:
  - Query mode writes exactly one JSON object followed by stdout's normal print
    newline.
  - Exit-notice mode performs no command-line output of its own.
  - Default live-session mode performs no command-line output of its own before
    handing off to the live session handler.
- consumes:
  - `query` boolean from `--query`, default `false`.
  - `exit_code` nullable integer from `--exit-code`, default `null`.
- errors:
  - Parser errors exit through argparse before this invocation starts.
  - Import-time sidecar runtime failures, including malformed sidecar environment
    values parsed when the sidecar module loads, propagate before query,
    exit-notice, or live-session mode can run.
  - Query-mode snapshot/read failures propagate from the snapshot path.
  - Exit-notice mode keeps the sidecar's fire-and-forget guarantee: an
    unreachable host does not raise from the push handler.
  - Default live-session connection, reload, and shutdown behavior is owned by
    the live session handler.
- verify: json_path(path="$.current_node", equals="n1")
- verify: json_path(path="$.terminal", equals="")
- verify: count(subject="snapshot gates", equals=1)
- verify: exit_status(code=0)
- code: groom/groom/cli.py::sidecar_main
- tests: groom/tests/test_sidecar.py::test_cli_query_prints_snapshot_json_and_does_not_watch
- tests: groom/tests/test_sidecar.py::test_snapshot_reports_node_terminal_and_gates
- tests: groom/tests/test_sidecar_session.py::test_cli_sidecar_default_runs_session
