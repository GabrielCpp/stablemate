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
`groom` without a command is an argument error. [`serve`](#serve) starts the
local [groom server](http/groom.md) and keeps it running until the server exits;
`status`, `logs` and `db-path` read the collected telemetry, and
[`profile`](#profile) partitions a retained run's wall clock and distinguishes
workflow revisits from backend retries. [`purge-tests`](#purge-tests) evicts the
part of it a test process wrote. The [Groom CLI entrypoints
module](concepts/groom-cli-entrypoints-module.md) owns this executable root and
the companion [`groom-sidecar`](groom-sidecar.md)
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
- verify: count(subject="server runners started", equals=1)
  - Passes the selected host unchanged to the server startup layer.
- verify: json_path(path="server.config.host", equals="127.0.0.1")
  - Passes the selected port unchanged to the server startup layer.
- verify: json_path(path="server.config.port", equals=8787)
  - Does not rewrite an invalid bind name before server startup.
- verify: json_path(path="server.config.host", equals="invalid-bind-name")
  - Does not reserve the selected port before server startup.
- verify: json_path(path="server.bind_calls", equals=0)
  - Does not add authentication before server startup.
- verify: json_path(path="server.config.authentication", absent=true)
- errors:
  - Missing command, unknown flags, invalid `--port` values, or extra
    positional arguments are parser errors before server startup.
- verify: json_path(path="stderr", matches="usage:.*error:")
  - Server app construction failures propagate out of the command handler.
- verify: exit_status(code=1)
  - Server bind failures propagate out of the command handler.
- verify: exit_status(code=1)
  - Server startup failures propagate out of the command handler.
- verify: exit_status(code=1)
  - Server runtime failures propagate out of the command handler.
- verify: exit_status(code=1)
- exits:
  - Successful server stop returns normally from the command handler, so the
    console process exits with status 0 when no outer exception is raised.
- verify: exit_status(code=0)
  - A racing second `KeyboardInterrupt` during server shutdown is swallowed so
    the command still returns normally from the command handler.
- verify: exit_status(code=0)
  - Parser failures exit with status 2 before the command handler runs.
- verify: exit_status(code=2)
  - Uncaught server startup/runtime exceptions leave the process through Python's
    normal unhandled-exception path.
- verify: exit_status(code=1)
- code: groom/groom/cli.py::serve
- detail: [groom server](http/groom.md)

### purge-tests
- usage: `groom purge-tests [--dry-run] [--no-vacuum]`
- parent: [groom](#groom)
- flags:
  - `--dry-run`
    - type: boolean
    - required: false
    - default: `false`
    - Reports the same counts the real purge would and deletes nothing.
  - `--no-vacuum`
    - type: boolean
    - required: false
    - default: `false` (i.e. vacuum by default)
    - Skips the `VACUUM` that follows a purge. Faster, but SQLite keeps the freed
      pages for reuse, so the file holds its old size on disk.
- args:
  - none: `purge-tests` accepts no positional arguments.
- does:
  - Classifies every distinct `(run_id, run_dir)` in the `spans` and `logs`
    tables — the two that carry `run_dir` — as throwaway or real by the run dir
    alone: a path containing `pytest-of-`, `.workhorse-test/` or `.groom-test/`,
    or one whose first segment under a temp root is a `tempfile.mkdtemp` name
    (`tmp` + a random suffix), is throwaway. The second rule is the purge's
    alone; the OTLP receivers drop only the first, unambiguous kind.
  - verify: unchanged(subject="real-run telemetry")
  - Deletes every `spans`, `metrics` and `logs` row belonging to those run ids,
    in chunks of 500 ids.
    `metrics` has no `run_dir` column, so its rows are reachable only through a
    run id some span or log record identified.
  - verify: removed(subject="test-run telemetry rows")
  - Commits the deletion before returning the purge counts.
  - verify: persists(subject="purged test-run telemetry")
  - Vacuums the store after a non-dry purge unless `--no-vacuum` is set.
  - verify: persists(subject="vacuumed telemetry store")
  - Prints the run/span/metric/log counts removed, or `no test-run telemetry
    found.` when the store is already clean.
- errors:
  - none specific: a store with nothing to purge is a successful no-op, and a
    second pass over an already-purged store removes zero rows.
- code: groom/groom/cli.py::purge_tests

### profile
- usage: `groom profile --run RUN [--json]`
- parent: [groom](#groom)
- flags:
  - `--run RUN`
    - type: string
    - required: true
    - default: none
    - Selects one exact retained `run_id`; omitting the flag is rejected by the
      argument parser, while an explicitly empty value produces the normal
      no-telemetry result.
  - `--json`
    - type: boolean
    - required: false
    - default: `false`
    - Emits the complete profile object as indented JSON instead of the
      human-readable summary.
- args:
  - none: `profile` accepts no positional arguments.
- does:
  - Reads every retained span for the selected run without applying the trace
    search page limit.
  - verify: json_path(path="$.time_s.wall", equals=201.0)
  - Includes retained metric timestamps when determining the observed start and
    end.
  - verify: json_path(path="$.observed_start_ts", equals=0.0)
  - Partitions observed wall time into a disjoint agent bucket.
  - verify: json_path(path="$.time_s.agent", equals=30.0)
  - Partitions observed wall time into a disjoint deterministic bucket.
  - verify: json_path(path="$.time_s.deterministic", equals=10.0)
  - Partitions observed wall time into a disjoint infrastructure bucket.
  - verify: json_path(path="$.time_s.infra", equals=10.0)
  - Partitions observed wall time into a disjoint explicit-wait bucket.
  - verify: json_path(path="$.time_s.wait", equals=20.0)
  - Partitions observed wall time into a disjoint cross-resume-gap bucket.
  - verify: json_path(path="$.time_s.resume_gap", equals=10.0)
  - Partitions observed wall time into a disjoint unclassified bucket.
  - verify: json_path(path="$.time_s.unclassified", equals=30.0)
  - Groups explicit waits by wait kind.
  - verify: json_path(path="$.time_s.waits_by_kind.operator", equals=10.0)
  - Reports agent turns as raw CLI invocations.
  - verify: json_path(path="$.work.turns", equals=3)
  - Reports workflow visits as distinct trace-scoped parent node spans.
  - verify: json_path(path="$.work.visits", equals=2)
  - Reports additional turns under the same visit as `backend_retries`.
  - verify: json_path(path="$.work.backend_retries", equals=1)
  - Counts a legacy turn with no parent id as its own visit.
  - verify: json_path(path="$.work.visits", equals=2)
  - Reports `visits_per_work` from distinct workflow visits and `work_id`
    labels, so backend retries do not inflate the convergence ratio.
  - verify: json_path(path="$.work.visits_per_work", equals=1.0)
  - Groups agent work by integer attempt labels.
  - verify: json_path(path="$.attempt_groups[0].value", equals="0")
  - Groups agent work by closed verdict labels.
  - verify: json_path(path="$.verdict_groups[0].value", equals="revise")
  - Preserves turn totals for each agent-work group.
  - verify: json_path(path="$.attempt_groups[0].turns", equals=2)
  - Preserves visit totals for each agent-work group.
  - verify: json_path(path="$.attempt_groups[0].visits", equals=1)
  - Preserves backend-retry totals for each agent-work group.
  - verify: json_path(path="$.attempt_groups[0].backend_retries", equals=1)
  - Preserves duration totals for each agent-work group.
  - verify: json_path(path="$.attempt_groups[0].agent_s", equals=20.0)
  - Preserves token totals for each agent-work group.
  - verify: json_path(path="$.attempt_groups[0].output_tokens", equals=150)
  - Preserves backend coverage for each agent-work group.
  - verify: json_path(path="$.attempt_groups[0].backends[0]", equals="claude")
  - Preserves cost coverage totals for each agent-work group.
  - verify: json_path(path="$.attempt_groups[0].cost_coverage", equals=1.0)
  - Prints `no telemetry found for that run.` in text mode when neither spans
    nor metrics exist for the selected run.
  - verify: json_path(path="stdout", equals="no telemetry found for that run.\n")
  - Prints JSON `null` in JSON mode when neither spans nor metrics exist for the
    selected run.
  - verify: json_path(path="$", equals=null)
- errors:
  - Missing `--run`, unknown flags, extra positional arguments, or malformed
    command lines are parser errors.
  - verify: exit_status(code=2)
  - Argparse writes usage and error text for parser errors.
  - verify: json_path(path="stderr", matches="usage:.*error:")
  - Parser errors exit before querying telemetry.
  - verify: exit_status(code=2)
  - SQLite read failures propagate through Python's normal unhandled-exception
    path.
  - verify: exit_status(code=1)
  - Malformed retained attribute JSON propagates through Python's normal
    unhandled-exception path.
  - verify: exit_status(code=1)
- exits:
  - A found profile and the no-telemetry result both return normally and exit
    with status 0 when output succeeds.
  - verify: exit_status(code=0)
  - Parser failures exit with status 2 before the command handler runs.
  - verify: exit_status(code=2)
- code: groom/groom/cli.py::profile
- detail: [retained-run profiler](../../../groom/docs/STORE.md#what-occupied-the-wall-clock-groom-profile)

### transcript
- usage: `groom transcript {ls|show|harvest|export|backfill} [...]`
- parent: [groom](#groom)
- flags:
  - `ls [--run RUN] [--node NODE] [--session SESSION] [--workflow WORKFLOW] [--limit N] [--json]`
    - Lists archived turn records, ordered by the visit key `(run_id, generation,
      seq)` rather than by timestamp, so a node's laps read in the order the run
      took them across a checkpoint rewind. `--limit` defaults to 200.
  - `show --session SESSION [--json]`
    - Prints one record's directory, the files in it, and its `prompt.md`. The
      transcript body is never printed: a record runs to tens of megabytes and the
      path is what a pager or a replay needs.
  - `harvest`
    - Runs the copy pass immediately instead of waiting for the periodic tick.
  - `export --by-node DIR [--workflow W] [--run RUN] [--node NODE] [--limit N]`
    - Materializes the archive as `DIR/<workflow>/<node>/<source>__<session_id>.json`
      plus `DIR/INDEX.json`, one JSON object per session (`task`, `source`,
      `session_id`, `cwd`, `model`, `time_created`, `n_messages`, `messages[]`).
      `--by-node` is required and has no default: the export is a view, and where it
      lands is the caller's decision. `task` is the node from the index join, so
      classification is exact and no session is unclassified.
  - `backfill [--dry-run]`
    - Archives turns whose transcript never reached the run dir but is still in the
      agent CLI's own session store, joined on the session ids in each known run's
      `sessions.jsonl`. `--dry-run` reports the same records and copies nothing.
- args:
  - none: every verb takes flags only; a missing verb is a parser error.
- does:
  - Reads and writes the archive beside `groom.db` — `$GROOM_DB`'s directory, or
    the platform data dir.
  - verify: persists(subject="archived turn record beside the configured groom.db")
  - Pointing `$GROOM_DB` elsewhere moves archived bodies with the index.
  - verify: persists(subject="archived turn record beside the relocated groom.db")
  - Harvest detects a changed record from a content digest over the whole record.
  - verify: persists(subject="updated archived turn record")
  - Harvest re-copies a live run's growing transcript.
  - verify: count(subject="records copied after a transcript grows", equals=1)
  - An unchanged record costs a digest and no copy.
  - verify: count(subject="records copied after an unchanged harvest", equals=0)
  - Run dirs that look throwaway (`pytest-of-`, a `tempfile.mkdtemp` name under a
    temp root) are excluded from the inventory and never archived.
  - verify: count(subject="archived records from throwaway run directories", equals=0)
  - A run dir this host no longer has is skipped rather than reported as a failure.
  - verify: count(subject="archived records from unavailable run directories", equals=0)
  - `export` streams one session at a time and never holds the corpus in memory.
  - verify: count(subject="exported session files", equals=2)
  - `export` does not duplicate archive records.
  - verify: keys_unchanged(subject="archived turn-record keys after export")
  - `export` sanitizes workflow names into single path components.
  - verify: omits(subject="exported relative paths", matches="(^|/)\\.\\.(/|$)")
  - `export` sanitizes node names into single path components.
  - verify: omits(subject="exported relative paths", matches="(^|/)\\.\\.(/|$)")
- errors:
  - An unknown verb is a parser error.
  - verify: exit_status(code=2)
  - Argparse writes usage text for an unknown verb.
  - verify: json_path(path="$.stderr", matches="usage:")
  - An unknown flag is a parser error.
  - verify: exit_status(code=2)
  - Argparse writes usage text for an unknown flag.
  - verify: json_path(path="$.stderr", matches="usage:")
  - A missing `--session` on `show` is a parser error.
  - verify: exit_status(code=2)
  - Argparse writes usage text when `show` has no `--session`.
  - verify: json_path(path="$.stderr", matches="usage:")
  - A record whose bodies were removed under the index reports its files as empty
    rather than raising.
  - verify: count(subject="files reported for an indexed record with removed bodies", equals=0)
- exits:
  - An unknown verb exits with status 2.
  - verify: exit_status(code=2)
  - An unknown flag exits with status 2.
  - verify: exit_status(code=2)
  - `show` without `--session` exits with status 2.
  - verify: exit_status(code=2)
- code: groom/groom/cli.py::transcript_ls
- detail: [the turn record](../../../groom/docs/STORE.md#what-the-node-actually-said-groom-transcript)

## Invocations

### groom-serve
- on: [serve](#serve)
- trigger: the user runs `groom serve` after the `groom` parser has selected the
  `serve` command.
- when:
  - The parsed host is retained as `127.0.0.1` when `--host` is omitted.
  - verify: json_path(path="parsed.host", equals="127.0.0.1")
  - The parsed port is retained as integer `8787` when `--port` is omitted.
  - verify: json_path(path="parsed.port", equals=8787)
  - `--allow-non-loopback` is represented as a boolean flag, false when omitted.
  - verify: json_path(path="parsed.allow_non_loopback", equals=false)
  - No authentication precondition is enforced by the command.
  - verify: json_path(path="authorization.authentication", absent=true)
  - No authorization precondition is enforced by the command.
  - verify: json_path(path="authorization.authorization", absent=true)
- does:
  - Treats `localhost` as loopback for the warning decision.
  - verify: json_path(path="loopback", equals=true)
  - Treats an IP address whose parsed address is loopback as loopback for the warning decision.
  - verify: json_path(path="loopback", equals=true)
  - Treats an unparsable host string as non-loopback for the warning decision.
  - verify: json_path(path="loopback", equals=false)
  - Writes one stderr warning before constructing the server app when the selected host is not
    loopback and `--allow-non-loopback` is false.
  - verify: emitted(event="non-loopback bind warning", count=1)
  - States in the non-loopback warning that groom has no authentication.
  - verify: json_path(path="stderr", matches="NO authentication")
  - States in the non-loopback warning that reachable clients can control Docker.
  - verify: json_path(path="stderr", matches="exposes docker control")
  - States in the non-loopback warning that reachable clients can answer operator gates.
  - verify: json_path(path="stderr", matches="gate answers")
  - States in the non-loopback warning that in-container sidecars need a non-loopback bind to
    reach the host over the Docker bridge.
  - verify: json_path(path="stderr", matches="sidecars need this to reach the host over the docker bridge")
  - States in the non-loopback warning that `--allow-non-loopback` acknowledges the exposure.
  - verify: json_path(path="stderr", matches="pass --allow-non-loopback to acknowledge")
  - States in the non-loopback warning that the service should run only on a trusted network.
  - verify: json_path(path="stderr", matches="Only run on a trusted network")
  - Creates the [groom server](http/groom.md) app for the server runner.
  - verify: created(subject="groom server app")
  - Gives the created app to the server runner.
  - verify: json_path(path="server.config.app", equals="groom server app")
  - Configures the server runner with the selected host.
  - verify: json_path(path="server.config.host", equals="127.0.0.1")
  - Configures the server runner with the selected port.
  - verify: json_path(path="server.config.port", equals=8787)
  - Starts one server runner.
  - verify: count(subject="server runners started", equals=1)
  - Configures info-level server logging.
  - verify: json_path(path="server.config.log_level", equals="info")
  - Leaves authentication unconfigured.
  - verify: json_path(path="server.config.authentication", absent=true)
  - Leaves TLS unconfigured.
  - verify: json_path(path="server.config.tls", absent=true)
  - Leaves worker fan-out unconfigured.
  - verify: json_path(path="server.config.workers", absent=true)
  - Leaves hot reload unconfigured.
  - verify: json_path(path="server.config.reload", absent=true)
  - Leaves access controls unconfigured.
  - verify: json_path(path="server.config.access_controls", absent=true)
  - Controls network exposure through the selected bind host.
  - verify: json_path(path="server.config.host", equals="127.0.0.1")
  - Relies on the operator's local network boundary to limit access to a non-loopback bind.
  - verify: json_path(path="stderr", matches="Only run on a trusted network")
  - Configures graceful shutdown to time out after three seconds.
  - verify: json_path(path="server.config.timeout_graceful_shutdown", equals=3)
  - Allows persistent browser websocket connections to stop without requiring a second interrupt.
  - verify: exit_status(code=0)
  - Returns after the server runner stops.
  - verify: exit_status(code=0)
  - Ignores a `KeyboardInterrupt` raised while the server runner is unwinding.
  - verify: exit_status(code=0)
  - Does not convert a server app construction exception into a command-specific result.
  - verify: exit_status(code=1)
  - Does not convert a server bind exception into a command-specific result.
  - verify: exit_status(code=1)
  - Does not convert a server startup exception into a command-specific result.
  - verify: exit_status(code=1)
  - Does not convert a server runtime exception into a command-specific result.
  - verify: exit_status(code=1)
- emits:
  - stderr warning text only for a non-loopback bind without
    `--allow-non-loopback`.
  - verify: emitted(event="non-loopback bind warning", count=1)
  - Uvicorn/server logs while the server is running.
  - verify: emitted(event="Uvicorn/server logs", count=1)
  - HTTP, websocket, and static-asset service on the selected bind address via
    the [groom server](http/groom.md).
  - verify: emitted(event="HTTP, websocket, and static-asset service", count=1)
- consumes:
  - `host` string from `--host`, default `0.0.0.0`.
  - verify: json_path(path="server.config.host", equals="0.0.0.0")
  - `port` integer from `--port`, default `8787`.
  - verify: json_path(path="server.config.port", equals=8787)
  - `allow_non_loopback` boolean from `--allow-non-loopback`, default `false`.
  - verify: json_path(path="server.config.allow_non_loopback", equals=false)
  - [groom server](http/groom.md) application produced for this invocation.
  - verify: json_path(path="server.config.app", equals="groom server app")
- errors:
  - Parser errors exit before this invocation starts.
  - verify: exit_status(code=2)
  - Server app construction failures propagate from the server startup path.
  - verify: exit_status(code=1)
  - Server bind failures propagate from the server startup path.
  - verify: exit_status(code=1)
  - Server startup failures propagate from the server startup path.
  - verify: exit_status(code=1)
  - Server runtime failures propagate from the server startup path.
  - verify: exit_status(code=1)
- code: groom/groom/cli.py::serve
- exits:
  - Returns normally after the server runner stops, producing the console
    process's normal success status when no outer exception is raised.
  - verify: exit_status(code=0)
  - Ignores a racing second `KeyboardInterrupt` during server shutdown so the
    handler can still return normally.
  - verify: exit_status(code=0)
  - Leaves uncaught server startup/runtime exceptions to Python's normal
    unhandled-exception process exit behavior.
  - verify: exit_status(code=1)
- refs: [loopback host classifier](concepts/loopback-host-classifier.md)
