---
type: cli
slug: groom-sidecar
title: groom-sidecar
---
# groom-sidecar

- binary: groom-sidecar
- code: groom/groom/cli.py::sidecar_main
- verify: groom/tests/test_sidecar.py::test_cli_query_prints_snapshot_json_and_does_not_watch
- verify: groom/tests/test_sidecar_session.py::test_cli_sidecar_default_runs_session

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
- code: groom/groom/cli.py::sidecar_main
- detail: [sidecar live sessions](sidecar-live-sessions.md)
- errors: parser errors happen before sidecar work; runtime errors follow the
  selected sidecar mode's own contract.
  - Unknown flags, unexpected positional arguments, and non-integer
    `--exit-code` values are parser errors and prevent any sidecar module work
    from starting.
  - Runtime errors from query, exit notification, or the live session are not
    handled by the command dispatcher except for normal returns from those
    handlers.
- exits: query and exit-notice modes return after one action; default mode keeps
  the process in the live sidecar session until that handler returns or exits.
  - Query mode returns after writing one JSON snapshot to stdout.
  - Exit-notice mode returns after attempting one exited push.
  - Default live-session mode normally keeps running until the session handler
    returns or raises its own process exit.

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
  - Parses the root flags before importing the sidecar module, so parser errors
    do not load the sidecar runtime dependency set.
  - Imports the sidecar module only after parsing succeeds; this keeps the
    default argument-error path free of the sidecar runtime dependency set.
  - If importing the sidecar runtime module fails after successful parsing, the
    selected mode is never entered and that import-time failure propagates out of
    the command.
  - If `--query` is true, calls `groom/groom/sidecar.py::snapshot`, serializes
    the returned [sidecar snapshot data](sidecar-snapshot-data.md) as JSON to
    stdout, and returns without starting either the exit-notice path or the live
    watch/session loop. Query mode wins when `--query` and `--exit-code` are both
    supplied.
  - The query snapshot is a pure local read: it obtains the current node from the
    latest checkpoint, the terminal state from the latest run metadata, and the
    open-gate list from a workspace scan, then returns exactly the three keys
    `current_node`, `terminal`, and `gates`.
  - If `--query` is false and `--exit-code` is present, sends one best-effort
    workflow-exited notice by calling `groom/groom/sidecar.py::push_exited` with
    that integer exit code and returns without starting the live watch/session
    loop.
  - The exited notice path builds the [exited push payload](exited-push-payload.md)
    by merging sidecar identity (`container_id`, `name`, `repo_name`, and
    `repo_branch`) with the supplied `exit_code` integer, then posts that JSON
    body to `POST /push/exited` on the host groom service.
  - The JSON POST is performed by the [sidecar residual HTTP push helper](concepts/sidecar-residual-http-push-helper.md):
    it serializes the merged object as UTF-8 JSON, declares
    `Content-Type: application/json`, targets the configured `GROOM_HOST` and
    `GROOM_PORT`, and makes exactly one `POST` attempt.
  - The host address comes from `GROOM_HOST` and `GROOM_PORT`, defaulting to
    `host.docker.internal` and `8787`; the request declares a JSON content type
    and uses the `GROOM_PUSH_TIMEOUT` value, defaulting to one second.
  - The exited notice is fire-and-forget: connection failures, HTTP client
    errors raised by the HTTP open, and response-close errors are swallowed so
    the sidecar command returns normally and never changes the workflow process
    exit result.
  - If neither mode flag is selected, starts the default long-running sidecar
    session by calling the [sidecar live session runner](concepts/sidecar-live-session-runner.md),
    which owns the handoff from synchronous command execution into the async
    websocket serving loop.
  - The live-session runner starts the async sidecar serving loop and waits for
    it to complete; the serving loop connects to the host [groom server](http/groom.md),
    advertises current state, watches the container's workspace/run mounts, and
    serves the live sidecar data plane described by [sidecar live sessions](sidecar-live-sessions.md).
  - When the serving loop returns zero, the runner returns normally and leaves
    the sidecar command with its normal success exit status.
  - When the serving loop returns a non-zero code, the runner raises a process
    exit with exactly that code; the reserved reload code is therefore surfaced
    to the container entrypoint without being translated by the CLI dispatcher.
- consumes:
  - `query` boolean from `--query`, default `false`.
  - `exit_code` nullable integer from `--exit-code`, default `null`.
- emits:
  - Query mode writes exactly one JSON object followed by stdout's normal print
    newline.
  - Exit-notice mode performs no command-line output of its own.
  - Default live-session mode performs no command-line output of its own before
    handing off to the live session handler.
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
- exits:
  - Query mode returns normally after stdout is written.
  - Exit-notice mode returns normally after the push handler returns.
  - Default live-session mode returns only if the live session handler returns;
    a sidecar reload request exits the process through that handler's reserved
    reload exit code.
- code: groom/groom/cli.py::sidecar_main
- verify: groom/tests/test_sidecar.py::test_cli_query_prints_snapshot_json_and_does_not_watch
- verify: groom/tests/test_sidecar.py::test_snapshot_reports_node_terminal_and_gates
- verify: groom/tests/test_sidecar_session.py::test_cli_sidecar_default_runs_session
