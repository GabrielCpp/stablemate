---
type: cli
slug: groom-cli
title: groom
---
# groom

- binary: groom
- code: groom/groom/cli.py::main

The `groom` CLI is the manually launched host-side surface for the
[groom dashboard service](groom.md). It has no default action: invoking
`groom` without a command is an argument error. Its command tree contains
exactly one command, [`serve`](#serve), which starts the local
[groom server](http/groom.md) and keeps it running until the server exits. The
[`Groom CLI entrypoints module`](concepts/groom-cli-entrypoints-module.md) owns
this executable root and the companion [`groom-sidecar`](groom-sidecar.md)
console script; `groom-sidecar` is separate, not a subcommand of `groom`, and its
container protocol is documented in [sidecar protocol](sidecar-protocol.md).

Invalid command lines, unknown flags, and invalid `--port` values are rejected
by the argument parser before any server starts and exit through argparse's
standard usage/error path.

## Commands


### serve
- usage: `groom serve [--host HOST] [--port PORT] [--allow-non-loopback]`
- parent: [groom](#groom)
- flags:
  - `--host HOST`
    - type: string
    - required: false
    - default: `0.0.0.0`
    - The network interface address for the host dashboard server to bind. The
      default is `0.0.0.0`, which is reachable from workflow containers over the
      Docker bridge; `127.0.0.1` or `localhost` limits the dashboard to
      loopback clients. Any host string that is not recognized as loopback is
      treated as externally reachable for warning purposes before the server
      attempts to bind it.
  - `--port PORT`
    - type: integer
    - required: false
    - default: `8787`
    - The TCP port for the host dashboard server. The value must parse as an
      integer before the command handler runs; bind-time port errors are left to
      the server startup path.
  - `--allow-non-loopback`
    - type: boolean
    - required: false
    - default: `false`
    - Silences only the startup warning shown when the selected host is not
      loopback. It does not add authentication, change the bind address, or
      limit the HTTP/WebSocket routes exposed by the server.
- args:
  - none: `serve` accepts no positional arguments.
- does:
  - Invokes [`groom-serve`](#groom-serve) with the parsed host, port, and
    warning-suppression flag.
  - Passes the selected host and port unchanged to the server startup layer; the
    command does not rewrite invalid bind names, reserve the port, or add
    authentication before startup.
- code: groom/groom/cli.py::serve
- detail: [groom server](http/groom.md)
- errors:
  - Missing command, unknown flags, invalid `--port` values, or extra
    positional arguments are parser errors; argparse writes usage/error text and
    exits with status 2 before server startup.
  - Bind failures, app startup failures, and server runtime failures are server
    startup/runtime errors rather than command-specific recovery cases; they
    propagate out of the command handler.
- exits:
  - Successful server stop returns normally from the command handler, so the
    console process exits with status 0 when no outer exception is raised.
  - A racing second `KeyboardInterrupt` during server shutdown is swallowed so
    the command still returns normally from the command handler.
  - Parser failures exit with status 2 before the command handler runs; uncaught
    server startup/runtime exceptions leave the process through Python's normal
    unhandled-exception path.

## Invocations

### groom-serve
- on: [serve](#serve)
- trigger: the user runs `groom serve` after the `groom` parser has selected the
  `serve` command.
- when:
  - The parsed host is a string, the parsed port is an integer, and
    `--allow-non-loopback` is represented as a boolean flag.
  - No authentication or authorization precondition is enforced by the command.
- does:
  - Classifies the selected host with the [loopback host classifier](concepts/loopback-host-classifier.md).
    `localhost` and IP addresses whose parsed address is loopback are loopback; unparsable host
    strings are treated as non-loopback for the warning decision.
  - If the selected host is not loopback and `--allow-non-loopback` is false,
    writes a warning to stderr before constructing the server app. The warning
    states that groom has no authentication, exposes Docker control and
    operator-gate answers to reachable clients, defaults to non-loopback so
    sidecars can reach it over the Docker bridge, and should only run on a
    trusted network.
  - Creates the [groom server](http/groom.md) app, gives it to the server runner,
    and starts exactly one server process on the selected host and port with
    info-level server logging.
  - Leaves authentication, TLS, worker fan-out, hot reload, and access controls
    unconfigured; network exposure is controlled only by the selected bind host
    and the operator's local network boundary.
  - Configures graceful shutdown to time out after three seconds so persistent
    browser websocket connections do not require a second interrupt to stop the
    process.
  - Returns after the server stops. A `KeyboardInterrupt` raised while the server
    runner is already unwinding is ignored by the command handler; other server
    creation, bind, startup, or runtime exceptions are not converted into a
    command-specific result.
- emits:
  - stderr warning text only for a non-loopback bind without
    `--allow-non-loopback`.
  - Uvicorn/server logs while the server is running.
  - HTTP, websocket, and static-asset service on the selected bind address via
    the [groom server](http/groom.md).
- consumes:
  - `host` string from `--host`, default `0.0.0.0`.
  - `port` integer from `--port`, default `8787`.
  - `allow_non_loopback` boolean from `--allow-non-loopback`, default `false`.
  - [groom server](http/groom.md) application produced for this invocation.
- errors:
  - Parser errors exit before this invocation starts.
  - Server app construction, bind, startup, and runtime failures propagate from
    the server startup path; the invocation does not wrap them in a
    command-specific error result.
- exits:
  - Returns normally after the server runner stops, producing the console
    process's normal success status when no outer exception is raised.
  - Ignores a racing second `KeyboardInterrupt` during server shutdown so the
    handler can still return normally.
  - Leaves uncaught server startup/runtime exceptions to Python's normal
    unhandled-exception process exit behavior.
- code: groom/groom/cli.py::serve
- refs: [loopback host classifier](concepts/loopback-host-classifier.md)
