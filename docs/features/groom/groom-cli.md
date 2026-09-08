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
[`status`](#status), [`logs`](#logs), and [`cost`](#cost) read the collected
telemetry; [`loops`](#loops) ranks review→rework cycles by convergence and rework
cost; [`prices`](#prices) shows the rate card used by `cost`; and [`profile`](#profile)
partitions a retained run's wall clock and distinguishes workflow revisits from
backend retries. [`purge-tests`](#purge-tests) evicts telemetry a test process wrote.
The [`transcript`](#transcript) commands archive and recover the input/output records of
every node visit, and [`archive`](#archive) freezes entire run telemetry to disk for
long-term storage. The [Groom CLI entrypoints
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
  - Invokes [`groom-serve`](#groom-serve) with the parsed host, port, and warning-suppression flag.
- verify: count(subject="server runners started", equals=1)
- does:
  - Passes the selected host unchanged to the server startup layer.
- verify: json_path(path="server.config.host", equals="127.0.0.1")
- does:
  - Passes the selected port unchanged to the server startup layer.
- verify: json_path(path="server.config.port", equals=8787)
- does:
  - Does not rewrite an invalid bind name before server startup.
- verify: json_path(path="server.config.host", equals="invalid-bind-name")
- does:
  - Does not reserve the selected port before server startup.
- verify: json_path(path="server.bind_calls", equals=0)
- does:
  - Does not add authentication before server startup.
- verify: json_path(path="server.config.authentication", absent=true)
- errors: Missing command, unknown flags, invalid `--port` values, or extra
  positional arguments are parser errors before server startup.
- verify: json_path(path="stderr", matches="usage:.*error:")
- errors: Server app construction failures propagate out of the command
  handler.
- verify: exit_status(code=1)
- errors: Server bind failures propagate out of the command handler.
- verify: exit_status(code=1)
- errors: Server startup failures propagate out of the command handler.
- verify: exit_status(code=1)
- errors: Server runtime failures propagate out of the command handler.
- verify: exit_status(code=1)
- exits: Successful server stop returns normally from the command handler, so
  the console process exits with status 0 when no outer exception is raised.
- verify: exit_status(code=0)
- exits: A racing second `KeyboardInterrupt` during server shutdown is
  swallowed so the command still returns normally from the command handler.
- verify: exit_status(code=0)
- exits: Parser failures exit with status 2 before the command handler runs.
- verify: exit_status(code=2)
- exits: Uncaught server startup/runtime exceptions leave the process through
  Python's normal unhandled-exception path.
- verify: exit_status(code=1)
- code: groom/groom/cli.py::serve
- detail: [groom server](http/groom.md)

### status
- usage: `groom status [--run RUN] [--json]`
- parent: [groom](#groom)
- flags:
  - `--run RUN`
    - type: string
    - required: false
    - default: none
    - Selects one exact run_id; omitting the flag returns status for all live runs.
  - `--json`
    - type: boolean
    - required: false
    - default: `false`
    - Emits the status rows as indented JSON instead of human-readable text.
- args:
  - none: `status` accepts no positional arguments.
- does:
  - Asks the running [`groom serve`](#groom-serve) over HTTP (`/api/live`).
- verify: http_status(200, path="/api/live")
- does:
  - Reports where each live run is right now: open node, time in that node, agent idleness, last heartbeat age.
- verify: json_path(path="$[0].run_id", equals="some-run-id")
- does:
  - Prints `groom serve is not reachable` and exits with status 1 if the server is not running.
- verify: exit_status(code=1)
- errors: Unknown flags or extra positional arguments are parser errors.
- verify: exit_status(code=2)
- errors: Argparse writes usage and error text for parser errors.
- verify: json_path(path="stderr", matches="usage:.*error:")
- exits: A successful query exits with status 0.
- verify: exit_status(code=0)
- exits: Server unreachable exits with status 1.
- verify: exit_status(code=1)
- exits: Parser failures exit with status 2 before the command handler runs.
- verify: exit_status(code=2)
- code: groom/groom/cli.py::status
- detail: [retained-run live status](../../../groom/docs/STORE.md)

### logs
- usage: `groom logs [--run RUN] [--node NODE] [--level LEVEL] [--contains CONTAINS] [--limit N] [--json]`
- parent: [groom](#groom)
- flags:
  - `--run RUN`
    - type: string
    - required: false
    - default: none
    - Limits results to one run_id; omitting the flag returns logs from all runs.
  - `--node NODE`
    - type: string
    - required: false
    - default: none
    - Limits results to one node id.
  - `--level LEVEL`
    - type: string
    - required: false
    - default: none
    - Minimum severity: `WARNING` shows `WARNING`, `ERROR`, and `FATAL` entries.
  - `--contains CONTAINS`
    - type: string
    - required: false
    - default: none
    - Substring match on the message body.
  - `--limit N`
    - type: integer
    - required: false
    - default: `200`
    - Maximum records to return; the query returns newest-first so the limit keeps the most recent slice.
  - `--json`
    - type: boolean
    - required: false
    - default: `false`
    - Emits log rows as indented JSON instead of human-readable formatted text.
- args:
  - none: `logs` accepts no positional arguments.
- does:
  - Queries the telemetry store for log records matching all specified filters.
- verify: exit_status(code=0)
- does:
  - Returns the most recent n records ordered newest-first, then formats as oldest-first for reading as the output when results exist.
- verify: exit_status(code=0)
- does:
  - Includes logs only from script nodes running in-process (subprocess logs are consumed as JSON on failure only).
- verify: exit_status(code=0)
- does:
  - Prints `no log records match` with notes about telemetry enablement when the query returns empty.
- verify: exit_status(code=0)
- errors: Unknown flags or extra positional arguments are parser errors.
- verify: exit_status(code=2)
- errors: Argparse writes usage and error text for parser errors.
- verify: json_path(path="stderr", matches="usage:.*error:")
- errors: SQLite read failures propagate through Python's normal unhandled-exception path.
- verify: exit_status(code=1)
- exits: A successful query exits with status 0, regardless of whether results were found.
- verify: exit_status(code=0)
- exits: Parser failures exit with status 2 before the command handler runs.
- verify: exit_status(code=2)
- code: groom/groom/cli.py::logs
- detail: [retained-run logs](../../../groom/docs/STORE.md)

### cost
- usage: `groom cost [--run RUN] [--limit N] [--json]`
- parent: [groom](#groom)
- flags:
  - `--run RUN`
    - type: string
    - required: false
    - default: none
    - Limits results to one run_id; omitting the flag aggregates across all runs.
  - `--limit N`
    - type: integer
    - required: false
    - default: `100`
    - Maximum number of nodes to return.
  - `--json`
    - type: boolean
    - required: false
    - default: `false`
    - Emits cost data as indented JSON instead of human-readable table.
- args:
  - none: `cost` accepts no positional arguments.
- does:
  - Queries the telemetry store for per-node agent turn costs.
- verify: exit_status(code=0)
- does:
  - Reports turn count, cost in USD, per-work-item metrics (rework signal), and duration in the output.
- verify: exit_status(code=0)
- does:
  - Prints `/work` column showing turns per work item: 1.0 means the node ran once per story, 4.6 means re-ran 3.5 times on average.
- verify: exit_status(code=0)
- does:
  - Prints notes about unpriced turns when some turns reported no cost or a literal zero.
- verify: exit_status(code=0)
- does:
  - Prints `no agent turns recorded` when no turns have been stamped with cost.
- verify: exit_status(code=0)
- errors: Unknown flags or extra positional arguments are parser errors.
- verify: exit_status(code=2)
- errors: SQLite read failures propagate through Python's normal unhandled-exception path.
- verify: exit_status(code=1)
- exits: A successful query exits with status 0, regardless of whether results were found.
- verify: exit_status(code=0)
- exits: Parser failures exit with status 2 before the command handler runs.
- verify: exit_status(code=2)
- code: groom/groom/cli.py::cost
- detail: [per-node agent spend](../../../groom/docs/STORE.md)

### prices
- usage: `groom prices [--reprice] [--run RUN] [--all] [--resolve] [--json]`
- parent: [groom](#groom)
- flags:
  - `--reprice`
    - type: boolean
    - required: false
    - default: `false`
    - Applies the rate card to turns already in the store and writes `est_cost_usd`; does not modify `cost_usd`.
  - `--run RUN`
    - type: string
    - required: false
    - default: none
    - Limits `--reprice` to one run_id; omitting limits to only unpriced turns.
  - `--all`
    - type: boolean
    - required: false
    - default: `false`
    - With `--reprice`, redo turns that already carry an estimate (useful after a rate card change).
  - `--resolve`
    - type: boolean
    - required: false
    - default: `false`
    - Prices turns whose model is an alias (e.g. `sonnet`) by reading the concrete model id from their session store.
  - `--json`
    - type: boolean
    - required: false
    - default: `false`
    - Emits prices and repricing results as indented JSON instead of human-readable text.
- args:
  - none: `prices` accepts no positional arguments.
- does:
  - Prints the per-million token rates in the active rate card (builtin plus overrides).
- verify: exit_status(code=0)
- does:
  - Lists all models in the rate card with their input, output, cache-read, and cache-write rates in the output.
- verify: exit_status(code=0)
- does:
  - Prints the path to the override file that extends the builtin rates.
- verify: exit_status(code=0)
- does:
  - When `--reprice` is set, prices every agent turn carrying token counts and writes `est_cost_usd` to the database.
- verify: persists(subject="est_cost_usd values for priced turns")
- does:
  - When `--resolve` is set, reads concrete model ids from sessions and prices turns whose model is an alias.
- verify: exit_status(code=0)
- does:
  - Lists all models that could not be priced because they have no rate in the card.
- verify: exit_status(code=0)
- does:
  - Prints notes explaining when est$ covers only a subset of turns and how to improve coverage.
- verify: exit_status(code=0)
- errors: Unknown flags or extra positional arguments are parser errors.
- verify: exit_status(code=2)
- errors: SQLite or file I/O failures propagate through Python's normal unhandled-exception path.
- verify: exit_status(code=1)
- exits: A successful prices query or reprice exits with status 0.
- verify: exit_status(code=0)
- exits: Parser failures exit with status 2 before the command handler runs.
- verify: exit_status(code=2)
- code: groom/groom/cli.py::prices_cmd
- detail: [rate card pricing](../../../groom/docs/STORE.md)

### loops
- usage: `groom loops [--run RUN] [--workflow WORKFLOW] [--min-items N] [--json]`
- parent: [groom](#groom)
- flags:
  - `--run RUN`
    - type: string
    - required: false
    - default: none
    - Limits results to one run_id; omitting defaults to all runs, which is the useful default.
  - `--workflow WORKFLOW`
    - type: string
    - required: false
    - default: none
    - Limits results to one workflow name.
  - `--min-items N`
    - type: integer
    - required: false
    - default: `3`
    - Skips nodes with fewer work items than this threshold (one run's loop is anecdotal).
  - `--json`
    - type: boolean
    - required: false
    - default: `false`
    - Emits lap distributions as indented JSON instead of human-readable table.
- args:
  - none: `loops` accepts no positional arguments.
- does:
  - Queries per-node lap distributions: how many times each review→rework gate accepted before exit per work item.
- verify: exit_status(code=0)
- does:
  - Reports the unit as lap count per work item, and excess$ as money spent on every lap after the first.
- verify: exit_status(code=0)
- does:
  - Ranks nodes by gate acceptance rate, max lap count observed, and share of work items at the max in the output.
- verify: exit_status(code=0)
- does:
  - Lists nodes where unpriced or zero-priced turns distort the excess$ ranking and recommends ranking by turns instead.
- verify: exit_status(code=0)
- does:
  - Prints `no looping nodes found` when the store has insufficient data for meaningful distributions.
- verify: exit_status(code=0)
- errors: Unknown flags or extra positional arguments are parser errors.
- verify: exit_status(code=2)
- errors: SQLite read failures propagate through Python's normal unhandled-exception path.
- verify: exit_status(code=1)
- exits: A successful query exits with status 0, regardless of whether results were found.
- verify: exit_status(code=0)
- exits: Parser failures exit with status 2 before the command handler runs.
- verify: exit_status(code=2)
- code: groom/groom/cli.py::loops
- detail: [loop convergence analysis](../../../groom/docs/STORE.md)

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
    (`tmp` + a random suffix), is throwaway.
  - Purges rows for the wider, `tempfile.mkdtemp`-matched kind of throwaway run
    dir on top of the marker-matched kind — the OTLP ingest path never drops
    the `mkdtemp` kind, since it applies only the narrower marker rule.
  - Deletes every `spans`, `metrics` and `logs` row belonging to those run ids,
    in chunks of 500 ids.
    `metrics` has no `run_dir` column, so its rows are reachable only through a
    run id some span or log record identified.
  - Commits the deletion before returning the purge counts.
  - Vacuums the store after a non-dry purge unless `--no-vacuum` is set.
  - Prints the run/span/metric/log counts removed.
  - Prints `no test-run telemetry found.` when the store is already clean.
- verify: unchanged(subject="real-run telemetry")
- verify: removed(subject="telemetry from a mkdtemp-matched run dir the OTLP ingest path left in place")
- verify: removed(subject="test-run telemetry rows")
- verify: persists(subject="purged test-run telemetry")
- verify: persists(subject="vacuumed telemetry store")
- verify: json_path(path="stdout", matches="removed \\d+ test run\\(s\\): \\d+ spans, \\d+ metrics, \\d+ logs")
- verify: json_path(path="stdout", equals="no test-run telemetry found.\n")
- errors:
  - none specific: a store with nothing to purge exits without raising, and a
    second pass over an already-purged store exits without raising.
- verify: exit_status(code=0)
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
  - Reads every retained span for the selected run without applying the trace search page limit.
- verify: json_path(path="$.time_s.wall", equals=201.0)
- does:
  - Includes retained metric timestamps when determining the observed start and end.
- verify: json_path(path="$.observed_start_ts", equals=0.0)
- does:
  - Partitions observed wall time into a disjoint agent bucket.
- verify: json_path(path="$.time_s.agent", equals=30.0)
- does:
  - Partitions observed wall time into a disjoint deterministic bucket.
- verify: json_path(path="$.time_s.deterministic", equals=10.0)
- does:
  - Partitions observed wall time into a disjoint infrastructure bucket.
- verify: json_path(path="$.time_s.infra", equals=10.0)
- does:
  - Partitions observed wall time into a disjoint explicit-wait bucket.
- verify: json_path(path="$.time_s.wait", equals=20.0)
- does:
  - Partitions observed wall time into a disjoint cross-resume-gap bucket.
- verify: json_path(path="$.time_s.resume_gap", equals=10.0)
- does:
  - Partitions observed wall time into a disjoint unclassified bucket.
- verify: json_path(path="$.time_s.unclassified", equals=30.0)
- does:
  - Groups explicit waits by wait kind.
- verify: json_path(path="$.time_s.waits_by_kind.operator", equals=10.0)
- does:
  - Reports agent turns as raw CLI invocations.
- verify: json_path(path="$.work.turns", equals=3)
- does:
  - Reports workflow visits as distinct trace-scoped parent node spans.
- verify: json_path(path="$.work.visits", equals=2)
- does:
  - Reports additional turns under the same visit as `backend_retries`.
- verify: json_path(path="$.work.backend_retries", equals=1)
- does:
  - Counts a legacy turn with no parent id as its own visit.
- verify: json_path(path="$.work.visits", equals=2)
- does:
  - Reports `visits_per_work` from distinct workflow visits and `work_id` labels, so backend retries do not inflate the convergence ratio.
- verify: json_path(path="$.work.visits_per_work", equals=1.0)
- does:
  - Groups agent work by integer attempt labels.
- verify: json_path(path="$.attempt_groups[0].value", equals="0")
- does:
  - Groups agent work by closed verdict labels.
- verify: json_path(path="$.verdict_groups[0].value", equals="revise")
- does:
  - Preserves turn totals for each agent-work group.
- verify: json_path(path="$.attempt_groups[0].turns", equals=2)
- does:
  - Preserves visit totals for each agent-work group.
- verify: json_path(path="$.attempt_groups[0].visits", equals=1)
- does:
  - Preserves backend-retry totals for each agent-work group.
- verify: json_path(path="$.attempt_groups[0].backend_retries", equals=1)
- does:
  - Preserves duration totals for each agent-work group.
- verify: json_path(path="$.attempt_groups[0].agent_s", equals=20.0)
- does:
  - Preserves token totals for each agent-work group.
- verify: json_path(path="$.attempt_groups[0].output_tokens", equals=150)
- does:
  - Preserves backend coverage for each agent-work group.
- verify: json_path(path="$.attempt_groups[0].backends[0]", equals="claude")
- does:
  - Preserves cost coverage totals for each agent-work group.
- verify: json_path(path="$.attempt_groups[0].cost_coverage", equals=1.0)
- does:
  - Prints `no telemetry found for that run.` in text mode when neither spans nor metrics exist for the selected run.
- verify: json_path(path="stdout", equals="no telemetry found for that run.\n")
- does:
  - Prints JSON `null` in JSON mode when neither spans nor metrics exist for the selected run.
- verify: json_path(path="$", absent=true)
- errors: Missing `--run`, unknown flags, extra positional arguments, or
  malformed command lines are parser errors.
- verify: exit_status(code=2)
- errors: Argparse writes usage and error text for parser errors.
- verify: json_path(path="stderr", matches="usage:.*error:")
- errors: Parser errors exit before querying telemetry.
- verify: exit_status(code=2)
- errors: SQLite read failures propagate through Python's normal
  unhandled-exception path.
- verify: exit_status(code=1)
- errors: Malformed retained attribute JSON propagates through Python's normal
  unhandled-exception path.
- verify: exit_status(code=1)
- exits: A found profile and the no-telemetry result both return normally and
  exit with status 0 when output succeeds.
- verify: exit_status(code=0)
- exits: Parser failures exit with status 2 before the command handler runs.
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
  - Reads and writes the archive beside `groom.db` — `$GROOM_DB`'s directory, or the platform data dir.
- verify: persists(subject="archived turn record beside the configured groom.db")
- does:
  - Pointing `$GROOM_DB` elsewhere moves archived bodies with the index.
- verify: persists(subject="archived turn record beside the relocated groom.db")
- does:
  - Harvest detects a changed record from a content digest over the whole record.
- verify: persists(subject="updated archived turn record")
- does:
  - Harvest re-copies a live run's growing transcript.
- verify: count(subject="records copied after a transcript grows", equals=1)
- does:
  - An unchanged record costs a digest and no copy.
- verify: count(subject="records copied after an unchanged harvest", equals=0)
- does:
  - Run dirs that look throwaway (`pytest-of-`, a `tempfile.mkdtemp` name under a temp root) are excluded from the inventory and never archived.
- verify: count(subject="archived records from throwaway run directories", equals=0)
- does:
  - A run dir this host no longer has is skipped rather than reported as a failure.
- verify: count(subject="archived records from unavailable run directories", equals=0)
- does:
  - `export` streams one session at a time and never holds the corpus in memory.
- verify: count(subject="exported session files", equals=2)
- does:
  - `export` does not duplicate archive records.
- verify: keys_unchanged(subject="archived turn-record keys after export")
- does:
  - `export` sanitizes workflow names into single path components.
- verify: omits(subject="exported relative paths", matches="(^|/)\\.\\.(/|$)")
- does:
  - `export` sanitizes node names into single path components.
- verify: omits(subject="exported relative paths", matches="(^|/)\\.\\.(/|$)")
- errors: An unknown verb is a parser error.
- verify: exit_status(code=2)
- errors: Argparse writes usage text for an unknown verb.
- verify: json_path(path="$.stderr", matches="usage:")
- errors: An unknown flag is a parser error.
- verify: exit_status(code=2)
- errors: Argparse writes usage text for an unknown flag.
- verify: json_path(path="$.stderr", matches="usage:")
- errors: A missing `--session` on `show` is a parser error.
- verify: exit_status(code=2)
- errors: Argparse writes usage text when `show` has no `--session`.
- verify: json_path(path="$.stderr", matches="usage:")
- errors: A record whose bodies were removed under the index reports its files as empty
  rather than raising.
- verify: count(subject="files reported for an indexed record with removed bodies", equals=0)
- exits: An unknown verb exits with status 2.
- verify: exit_status(code=2)
- exits: An unknown flag exits with status 2.
- verify: exit_status(code=2)
- exits: `show` without `--session` exits with status 2.
- verify: exit_status(code=2)
- code: groom/groom/cli.py::transcript_ls
- detail: [the turn record](../../../groom/docs/STORE.md#what-the-node-actually-said-groom-transcript)

### archive
- usage: `groom archive {ls|show|now|status} [...]`
- parent: [groom](#groom)
- flags:
  - `ls [--run RUN] [--long] [--json]`
    - Lists frozen (archived) runs. The directory name *is* the run id, so the plain listing opens no files at all — which is the point of having no index table. `--long` reads each manifest; `--run` filters by exact id or prefix; `--json` emits the listing as a JSON array of objects with fields: run, dir, workflow, repo, branch, archived_at, min_ts, max_ts, spans, logs, metrics.
  - `show --run RUN [--limit N]`
    - Streams one frozen run's `telemetry.jsonl` to stdout line by line, in the interchange format. `--limit` stops after n records for a look at the shape. `--run` is required and can match by exact id or prefix (first match is used).
  - `now [--dry-run] [--limit N] [--json]`
    - Runs an archival sweep immediately instead of waiting for the periodic six-hour tick. `--dry-run` reports what would be archived without writing. `--limit` bounds how many runs to archive in this pass (0 = `GROOM_ARCHIVE_RUNS_PER_PASS`). Useful for draining a backlog faster or testing the feature.
  - `status [--json]`
    - Reports what the archive holds, what is waiting for it, and results from the last sweep: archived runs count, pending runs past retention window, runs held by ongoing activity, and the last sweep's timestamp and row count.
- args:
  - none: every verb takes flags only; a missing verb is a parser error.
- does:
  - Reads and writes the archive beside `groom.db` — `$GROOM_DB`'s directory, or the platform data dir.
- verify: persists(subject="archived run telemetry in groom.db's directory")
- does:
  - `ls` lists directories in the archive root without opening files for the plain listing.
- verify: exit_status(code=0)
- does:
  - `ls --long` reads each manifest, a one-line file per run with telemetry row counts, workflow name, repo, and branch.
- verify: exit_status(code=0)
- does:
  - `show` opens one `telemetry.jsonl`, streams it line by line, and exits when limit is reached or EOF.
- verify: count(subject="telemetry rows streamed from archive", equals=1)
- does:
  - `now` runs the same sweep that the six-hour ticker runs, exporting rows from the live database to the archive.
- verify: persists(subject="archived run telemetry")
- does:
  - `now` resumes incomplete sweeps from prior passes.
- verify: exit_status(code=0)
- does:
  - `now` reports which runs were archived and how many rows and bytes.
- verify: exit_status(code=0)
- does:
  - `now` reports any failures that occurred during the sweep.
- verify: exit_status(code=0)
- does:
  - `status` queries the current pending list (runs past retention window that are not yet archived).
- verify: exit_status(code=0)
- errors: An unknown verb is a parser error.
- verify: exit_status(code=2)
- errors: Argparse writes usage text for an unknown verb.
- verify: json_path(path="stderr", matches="usage:")
- errors: An unknown flag is a parser error.
- verify: exit_status(code=2)
- errors: A missing `--run` on `show` is a parser error.
- verify: exit_status(code=2)
- errors: A run that does not exist in the archive reports "no archived run" and exits with status 0 (not an error).
- verify: exit_status(code=0)
- errors: File I/O failures (e.g., reading a manifest or telemetry file) propagate through Python's normal unhandled-exception path.
- verify: exit_status(code=1)
- errors: Database failures during `now` propagate as Python exceptions.
- verify: exit_status(code=1)
- exits: An unknown verb exits with status 2.
- verify: exit_status(code=2)
- exits: An unknown flag exits with status 2.
- verify: exit_status(code=2)
- exits: `show` without `--run` exits with status 2.
- verify: exit_status(code=2)
- exits: Successful commands exit with status 0.
- verify: exit_status(code=0)
- code: groom/groom/cli.py::archive_ls
- detail: [run archival and retention](../../../groom/docs/STORE.md)

## Invocations

### groom-serve
- on: [serve](#serve)
- trigger: the user runs `groom serve` after the `groom` parser has selected the
  `serve` command.
- when:
  - The parsed host is retained as `127.0.0.1` when `--host` is omitted.
  - The parsed port is retained as integer `8787` when `--port` is omitted.
  - `--allow-non-loopback` is represented as a boolean flag, false when omitted.
  - No authentication precondition is enforced by the command.
  - No authorization precondition is enforced by the command.
- does:
  - Treats `localhost` as loopback for the warning decision.
  - Treats an IP address whose parsed address is loopback as loopback for the warning decision.
  - Treats an unparsable host string as non-loopback for the warning decision.
  - Writes one stderr warning before constructing the server app when the selected host is not
    loopback and `--allow-non-loopback` is false.
  - States in the non-loopback warning that groom has no authentication.
  - States in the non-loopback warning that reachable clients can control Docker.
  - States in the non-loopback warning that reachable clients can answer operator gates.
  - States in the non-loopback warning that in-container sidecars need a non-loopback bind to
    reach the host over the Docker bridge.
  - States in the non-loopback warning that `--allow-non-loopback` acknowledges the exposure.
  - States in the non-loopback warning that the service should run only on a trusted network.
  - Creates the [groom server](http/groom.md) app for the server runner.
  - Gives the created app to the server runner.
  - Configures the server runner with the selected host.
  - Configures the server runner with the selected port.
  - Starts one server runner.
  - Configures info-level server logging.
  - Leaves authentication unconfigured.
  - Leaves TLS unconfigured.
  - Leaves worker fan-out unconfigured.
  - Leaves hot reload unconfigured.
  - Leaves access controls unconfigured.
  - Controls network exposure through the selected bind host.
  - Relies on the operator's local network boundary to limit access to a non-loopback bind.
  - Configures graceful shutdown to time out after three seconds.
  - Allows persistent browser websocket connections to stop without requiring a second interrupt.
  - Returns after the server runner stops.
  - Ignores a `KeyboardInterrupt` raised while the server runner is unwinding.
  - Does not convert a server app construction exception into a command-specific result.
  - Does not convert a server bind exception into a command-specific result.
  - Does not convert a server startup exception into a command-specific result.
  - Does not convert a server runtime exception into a command-specific result.
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
- status:
  - Returns normally after the server runner stops, producing the console
    process's normal success status when no outer exception is raised.
  - Ignores a racing second `KeyboardInterrupt` during server shutdown so the
    handler can still return normally.
  - Leaves uncaught server startup/runtime exceptions to Python's normal
    unhandled-exception process exit behavior.
- errors:
  - Parser errors exit before this invocation starts.
  - Server app construction failures propagate from the server startup path.
  - Server bind failures propagate from the server startup path.
  - Server startup failures propagate from the server startup path.
  - Server runtime failures propagate from the server startup path.
- verify: json_path(path="parsed.host", equals="127.0.0.1")
- verify: json_path(path="parsed.port", equals=8787)
- verify: json_path(path="parsed.allow_non_loopback", equals=false)
- verify: json_path(path="authorization.authentication", absent=true)
- verify: json_path(path="authorization.authorization", absent=true)
- verify: json_path(path="loopback", equals=true)
- verify: json_path(path="loopback", equals=true)
- verify: json_path(path="loopback", equals=false)
- verify: emitted(event="non-loopback bind warning", count=1)
- verify: json_path(path="stderr", matches="NO authentication")
- verify: json_path(path="stderr", matches="exposes docker control")
- verify: json_path(path="stderr", matches="gate answers")
- verify: json_path(path="stderr", matches="sidecars need this to reach the host over the docker bridge")
- verify: json_path(path="stderr", matches="pass --allow-non-loopback to acknowledge")
- verify: json_path(path="stderr", matches="Only run on a trusted network")
- verify: created(subject="groom server app")
- verify: json_path(path="server.config.app", equals="groom server app")
- verify: json_path(path="server.config.host", equals="127.0.0.1")
- verify: json_path(path="server.config.port", equals=8787)
- verify: count(subject="server runners started", equals=1)
- verify: json_path(path="server.config.log_level", equals="info")
- verify: json_path(path="server.config.authentication", absent=true)
- verify: json_path(path="server.config.tls", absent=true)
- verify: json_path(path="server.config.workers", absent=true)
- verify: json_path(path="server.config.reload", absent=true)
- verify: json_path(path="server.config.access_controls", absent=true)
- verify: json_path(path="server.config.host", equals="127.0.0.1")
- verify: json_path(path="stderr", matches="Only run on a trusted network")
- verify: json_path(path="server.config.timeout_graceful_shutdown", equals=3)
- verify: exit_status(code=0)
- verify: exit_status(code=0)
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- verify: exit_status(code=1)
- verify: exit_status(code=1)
- verify: exit_status(code=1)
- verify: emitted(event="non-loopback bind warning", count=1)
- verify: emitted(event="Uvicorn/server logs", count=1)
- verify: emitted(event="HTTP, websocket, and static-asset service", count=1)
- verify: json_path(path="server.config.host", equals="0.0.0.0")
- verify: json_path(path="server.config.port", equals=8787)
- verify: json_path(path="server.config.allow_non_loopback", equals=false)
- verify: json_path(path="server.config.app", equals="groom server app")
- verify: exit_status(code=0)
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- verify: exit_status(code=2)
- verify: exit_status(code=1)
- verify: exit_status(code=1)
- verify: exit_status(code=1)
- verify: exit_status(code=1)
- code: groom/groom/cli.py::serve
- refs: [loopback host classifier](concepts/loopback-host-classifier.md)
