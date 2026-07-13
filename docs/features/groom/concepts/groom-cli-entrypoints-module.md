---
type: concept
slug: groom-cli-entrypoints-module
title: Groom CLI entrypoints module
---
# Groom CLI entrypoints module

The Groom CLI entrypoints module is the console-script boundary for the
host-side [`groom`](../groom-cli.md) executable and the in-container
[`groom-sidecar`](../groom-sidecar.md) executable. It owns command-line parsing,
startup defaults, exposure-warning decisions, and the handoff into the
[groom server](../http/groom.md), the [sidecar snapshot](sidecar-snapshot.md),
the [sidecar residual HTTP push helper](sidecar-residual-http-push-helper.md),
and the [sidecar live session runner](sidecar-live-session-runner.md). Its
non-loopback bind warning uses the [loopback host classifier](loopback-host-classifier.md);
the server app itself is produced by the [Groom app module](groom-app-module.md).

- code: groom/groom/cli.py

## Contract

- role: console-script entrypoint module for `groom` and `groom-sidecar`.
- executables: exposes one host command tree rooted at [`groom`](../groom-cli.md)
  and one container command rooted at [`groom-sidecar`](../groom-sidecar.md); the
  two roots are separate executables, not subcommands of each other.
- import behavior: imports only argument parsing, IP-address classification, and
  process I/O helpers at module import time. Server runtime dependencies are
  imported only by [method-serve](#method-serve), and sidecar runtime
  dependencies are imported only by [method-sidecar-main](#method-sidecar-main)
  after parser errors have been ruled out.
- defaults: `groom serve` binds to [field-default-host](#field-default-host) and
  [field-default-port](#field-default-port) unless the operator supplies command
  flags.
- warning boundary: non-loopback host classification controls only the stderr
  exposure warning for the host dashboard; it does not add authentication,
  reject the bind address, rewrite the selected address, or limit server routes.
- parser failure model: unknown flags, invalid integer values, missing required
  commands, and unexpected positional arguments exit through the parser before
  the selected command handler performs server or sidecar work.
- runtime failure model: server startup/runtime failures, sidecar snapshot
  failures, and sidecar live-session failures are not converted into a shared
  module-level error envelope. The sidecar exit-notice mode keeps the residual
  push helper's best-effort behavior.

## Fields

### field-default-host

- type: `str`
- default: `0.0.0.0`
- required: true
- code: groom/groom/cli.py::DEFAULT_HOST
- meaning: default host passed to [`groom serve`](../groom-cli.md#serve), chosen
  so in-container sidecars can reach the host dashboard over the Docker bridge.
  Because it is not loopback, the default emits the exposure warning unless the
  operator passes `--allow-non-loopback`.

### field-default-port

- type: `int`
- default: `8787`
- required: true
- code: groom/groom/cli.py::DEFAULT_PORT
- meaning: default TCP port passed to [`groom serve`](../groom-cli.md#serve) and
  aligned with the sidecar host-port default used for residual pushes and live
  sidecar sessions.

## Public Members

### method-main

- sig: `main(argv: list[str] | None = None) -> None`
- abstract: false
- raises: parser exits for invalid command lines; exceptions from
  [method-serve](#method-serve) propagate when the selected command reaches the
  server startup path.
- code: groom/groom/cli.py::main
- cli: [`groom`](../groom-cli.md)
- does:
  - Builds the `groom` argument parser with exactly one required subcommand,
    [`serve`](../groom-cli.md#serve).
  - Defines `--host`, `--port`, and `--allow-non-loopback` as the full flag set
    for the `serve` command, with defaults from [field-default-host](#field-default-host)
    and [field-default-port](#field-default-port).
  - Parses the supplied `argv` list, or the process command line when `argv` is
    absent.
  - Dispatches the accepted `serve` command to [method-serve](#method-serve) with
    the parsed host string, parsed port integer, and warning-suppression boolean.
  - Performs no server construction, socket binding, sidecar import, or workflow
    state mutation unless the parser accepted `serve`.

### method-serve

- sig: `serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *, allow_non_loopback: bool = False) -> None`
- abstract: false
- raises: server app construction, bind, startup, and runtime failures propagate;
  a racing second `KeyboardInterrupt` during server shutdown is swallowed.
- code: groom/groom/cli.py::serve
- command: [`serve`](../groom-cli.md#serve)
- invocation: [`groom-serve`](../groom-cli.md#groom-serve)
- refs: [loopback host classifier](loopback-host-classifier.md)
- refs: [Groom app module](groom-app-module.md#method-create-app)
- does:
  - Classifies `host` with the [loopback host classifier](loopback-host-classifier.md).
  - Writes the documented non-loopback exposure warning to stderr when `host` is
    not loopback and `allow_non_loopback` is false.
  - Constructs one [groom server](../http/groom.md) app through
    [method-create-app](groom-app-module.md#method-create-app).
  - Starts one server runner on the selected host and port with info-level server
    logging.
  - Sets the graceful-shutdown timeout to three seconds so persistent dashboard
    websocket connections do not require a second interrupt to terminate the
    process.
  - Returns after the server runner stops; it does not add authentication, TLS,
    worker fan-out, hot reload, or access controls around the server app.

### method-sidecar-main

- sig: `sidecar_main(argv: list[str] | None = None) -> None`
- abstract: false
- raises: parser exits for invalid command lines; query-mode snapshot failures
  propagate; exit-notice HTTP-open failures are swallowed by the residual push
  helper; default live-session failures follow the sidecar live session runner's
  exit and exception contract.
- code: groom/groom/cli.py::sidecar_main
- verify: groom/tests/test_sidecar.py::test_cli_query_prints_snapshot_json_and_does_not_watch
- verify: groom/tests/test_sidecar_session.py::test_cli_sidecar_default_runs_session
- cli: [`groom-sidecar`](../groom-sidecar.md)
- command: [`root`](../groom-sidecar.md#root)
- invocation: [`groom-sidecar-root`](../groom-sidecar.md#groom-sidecar-root)
- refs: [sidecar snapshot](sidecar-snapshot.md#method-snapshot)
- refs: [sidecar residual HTTP push helper](sidecar-residual-http-push-helper.md#method-push-exited)
- refs: [sidecar live session runner](sidecar-live-session-runner.md)
- does:
  - Builds the `groom-sidecar` parser with no subcommands and exactly two
    root-level mode flags: `--query` and `--exit-code`.
  - Parses the supplied `argv` list, or the process command line when `argv` is
    absent, before importing the sidecar module.
  - Imports the sidecar runtime module only after parsing succeeds.
  - In query mode, reads [method-snapshot](sidecar-snapshot.md#method-snapshot),
    serializes the returned [sidecar snapshot data](../sidecar-snapshot-data.md)
    as compact JSON to stdout, and returns without attempting the exit-notice or
    live-session paths.
  - In exit-notice mode, calls
    [method-push-exited](sidecar-residual-http-push-helper.md#method-push-exited)
    with the parsed integer exit code and returns without starting the live
    sidecar session.
  - In default mode, calls the [sidecar live session runner](sidecar-live-session-runner.md)
    and leaves process-exit behavior to that runner.
  - Gives query mode precedence over exit-notice mode when both `--query` and
    `--exit-code` are supplied.

## Private Members

### method-_is-loopback

- sig: `_is_loopback(host: str) -> bool`
- abstract: false
- raises: none for ordinary host strings; unparsable hosts are classified as
  non-loopback.
- code: groom/groom/cli.py::_is_loopback
- detail: [loopback host classifier](loopback-host-classifier.md)
- does:
  - Provides the private implementation behind the public [loopback host classifier](loopback-host-classifier.md).
  - Returns `true` for the literal string `localhost` and for parseable loopback
    IP address literals.
  - Returns `false` for non-loopback IP address literals and host strings that
    are not parseable as IP addresses.
