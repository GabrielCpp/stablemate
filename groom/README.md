# groom

A local, single-process web dashboard for `workhorse` agent-workflow operator
gates. Run `groom serve` on your host while `author`/`coder` (or any other
`workhorse`-based workflow) containers run in the background; `groom` shows
every running workflow, pages you the moment one blocks on an operator gate,
and lets you answer the gate right from the browser — no more finding and
restarting blocked containers one by one. The shared `await_operator` node blocks in
place via `inotify` rather than exiting, so the container keeps running and
just wakes up once you answer; `groom` only falls back to `docker start` if
a container has genuinely stopped.

## How it works

- Each workflow container runs a tiny in-container sidecar, `groom-sidecar`,
  that watches its own `/workspace` and `/runs` mounts (via `watchfiles`, so the
  container gets inotify and a developer's macOS or Windows box still works) and holds
  one persistent WebSocket open to the host's `groom` (dialing out over
  `host.docker.internal`, so no inbound reachability is needed). It advertises
  full state on connect, streams `progress`/`blocked` deltas, and serves the
  Files/Diff panels from local disk via `getTree`/`getFile`/`getDiff` RPC over
  the same socket. The connection is best-effort and re-syncs on reconnect —
  a container with no `groom` listening behaves exactly as it does today. See
  `docs/features/groom/sidecar-live-sessions.md` for the message schema and the
  local `reload` dev loop.
- `groom` itself holds all state in memory (no database, no broker) and pushes
  JSON state to open browser tabs over a websocket; the browser renders it with
  Preact + htm (the vendored `htm/preact` standalone build — no build step, no
  `node_modules`). Every shape the socket pushes is also fetchable over HTTP, so a
  tab whose socket has gone quiet resyncs instead of going stale.
  Those pushes are edge-triggered — something changed, so tell the
  tabs — which covers everything except the half of a run row that is derived from
  the clock: the liveness dot, `silent 4m`, `in node 12m`. The event that should
  turn a row dead is the run *ceasing* to emit, and an absence cannot be pushed, so
  the run list is additionally re-rendered and broadcast every `GROOM_LIVE_TICK_S`
  (5s), skipped entirely when no tab is connected. That is what makes the dashboard
  safe to leave open and read without refreshing.
  Gate questions render as Markdown (`marked`, sanitized with
  `DOMPurify` before insertion since the content is LLM-authored) and each
  workflow row can expand a `git diff` of its working tree (rendered with
  `diff2html`). All front-end assets are vendored locally; nothing is loaded
  from a CDN at runtime.
- On startup (or on-demand refresh), `groom` runs a one-shot `docker ps -a` +
  `docker inspect` reconciliation scan so workflows that were already
  blocked before `groom` was started are still picked up.

## Install

groom is not on PyPI (that name belongs to an unrelated project), so install it from a
checkout of the [stablemate](https://github.com/GabrielCpp/stablemate) workspace:

```bash
pipx install ./groom        # isolated CLI on your PATH
```

Requires Python ≥ 3.12. groom is an optional add-on — no base workflow requires it — and
nothing has to be configured on the workflow side: `workhorse` probes for a collector at
the default port when a run starts, and containers dial out to it on their own.

## Usage

```bash
groom serve                       # binds 127.0.0.1:8787 — loopback only, the default
groom serve --host 0.0.0.0       # all interfaces: required for containerized runs (see note)
```

From a checkout of this workspace, prefix each command with `uv run` (`uv run groom serve`)
to use the working tree instead of the installed copy.

> **Binding.** groom binds loopback by default because it has **no
> authentication** — it controls docker and answers operator gates. The
> in-container `groom-sidecar`s reach the host over the docker bridge
> (`host.docker.internal` → the bridge gateway on Linux, not loopback), so
> containerized runs need `--host 0.0.0.0` — an explicit choice that prints a
> one-line exposure warning (`--allow-non-loopback` acknowledges it). Only do
> that on a trusted network.

## Telemetry collector (OTLP) + AFK alerting

`groom` is also the default local **OpenTelemetry collector** for `workhorse`
runs. The same uvicorn process
and port expose standard OTLP/HTTP receivers — `POST /v1/traces`,
`POST /v1/metrics` and `POST /v1/logs` — so an ordinary run

```bash
pip install 'workhorse-agent[otel]'   # the extra carries the OTel SDK; without it, no export
workhorse-coder run                # probes the endpoint at start; exports if groom answers
```

(No env var is needed while `groom serve` is up on the default port — workhorse
enables telemetry when it finds a collector listening. Point elsewhere with
`OTEL_EXPORTER_OTLP_ENDPOINT`, or opt out with `WORKHORSE_OTEL=0`.)

It streams node/agent-turn spans, gas/heartbeat metrics, and the log records of the
engine and every node it runs in-process into `groom`. Because a
pushed span carries its own identity, **native (non-Docker) runs appear too** —
no discovery gate. Spans and metrics persist in an embedded SQLite file
(`groom.db` in the platform data dir; override with `GROOM_DB`), searchable
from the dashboard's *Telemetry* pane, via `GET /traces?run=…&node=…&status=…&
slower_than=…`, or with raw `sqlite3` queries. Rows older than
`GROOM_RETENTION_DAYS` (14) are pruned at startup and on a periodic tick.

The liveness counters — `workhorse.run.heartbeat`, `workhorse.turn.heartbeat`,
`workhorse.cap_wait.heartbeat` — expire much sooner
(`GROOM_LIVENESS_RETENTION_DAYS`, 1). They tick every ~10s for every open node, so
on long runs they outgrow everything else combined: in one real store the run
heartbeat alone was 1.77M of 2.21M metric rows. Nothing reads their history — the
alert rules fold them into memory at ingest and `groom status` reads only the newest
point — so the full window bought nothing and cost most of the file. The gauges
(`turn.active`, `turn.idle_s`, `wait.active`, `wait.elapsed_s`, `node.elapsed_s`,
`node.active`) keep the normal window: climbing idle on an active turn diagnoses a
wedged agent, while an explicit wait is expected parked work.

**The pane shows the runs connected right now.** Two weeks of retention means the
unfiltered strip is mostly runs that ended days ago, and a dashboard is for
watching, so a run card (and its spans — a span table listing a hidden run's nodes
is telemetry from nowhere) appears only while the run is `live` by the same
heartbeat predicate the fleet rows use. History is one tick of *show ended* away
(`GET /traces?show_ended=1`), and searching an explicit `run=` always finds it:
naming a run is asking for that run, finished or not.

**Native runs are first-class dashboard rows, not just telemetry.** A run on
groom's own host advertises its `run_dir`, workspace path, pid, and per-node
`activity` label on the OTLP resource; groom materializes a fleet row from that
(keyed by `run_id`), shows what it is doing ("coder · reviewing ACME-A2JX"), and —
because it shares the host — serves the row's Files/Diff panels and answers its
operator gates straight from the local filesystem (`groom.localfs`), no docker
volume or sidecar needed. The native test is self-validating: groom draws the row
only for a run whose `run_dir` it can actually read locally, so a containerized
producer (whose paths don't resolve on the host) never double-lists.

Alert rules run on every ingest plus a periodic tick, and page you through
browser notifications **and** an away-from-keyboard push — configure
`GROOM_NTFY_TOPIC` (posts to `https://ntfy.sh/<topic>`; override the server
with `GROOM_NTFY_URL`) and/or `GROOM_WEBHOOK_URL` (JSON `{"title","message"}`):

| Rule | Fires when | Knob (default) |
|---|---|---|
| STALL | a live run emits **nothing** — no span, no heartbeat | `GROOM_STALL_MIN` (90) |
| STUCK | a live agent turn is silent too long, or deterministic work has sat in one node too long; explicit waits are excluded | `GROOM_STUCK_MIN` (75) |
| CHURN | the same node span repeats with no gas refuel | `GROOM_CHURN_REPEATS` (5) |
| WATCHDOG | a `watchdog_kill` span event arrives | — |
| GAVE-UP | a give-up node's span arrives | `GROOM_GIVEUP_NODES` (qa_give_up,fix_give_up) |

Groom deliberately does not alert on total run age: resumptions reuse a run identity and multi-day
runs are normal. Use workhorse's `WORKHORSE_MAX_RUNTIME_S` when a run needs a hard wall-clock limit.

The crux: workhorse **heartbeats** for as long as its process lives, so silence
and slowness are different observations. STALL means the run stopped emitting
(dead/killed/frozen); STUCK means it is alive and parked. Alerts dedupe per
`(run, rule)`. Run `groom serve` under nohup/systemd as the always-on collector
(the consuming repo's `make groom-serve` target does exactly that).

## Where is my run right now?

Spans export **on completion**, so a run's current node — the only one that
matters when it will not finish — has no row in `spans` and never will while it
hangs. The live picture therefore comes from metrics, which ship on a timer
regardless of span state:

```bash
uv run groom status              # every live run: open node, node age, agent idleness
uv run groom status --run <id>   # one run
uv run groom status --json       # same data, machine-readable
```

Read it like this:

| Reading | Means |
|---|---|
| `alive`, node age small | working normally |
| `alive`, explicit wait | operator/cap/retry wait — parked deliberately |
| `alive`, active turn age large, agent `idle` small | a long but **streaming** turn — healthy |
| `alive`, active turn, agent `idle` large | **wedged** agent/tool/API inside the node |
| `alive`, no turn or wait, node age large | **wedged deterministic work** inside the node |
| no heartbeat (`DEAD?`) | the process is gone — SIGKILL, OOM, crashed host |

## What was it saying? (`groom logs`)

`status` says *where* a run is; logs say what it was doing on the way there.

```bash
uv run groom logs --run <id>                 # everything, oldest-first
uv run groom logs --run <id> --node select_item
uv run groom logs --level WARNING            # a FLOOR: WARNING + ERROR + FATAL
uv run groom logs --contains "over budget"
```

Deterministic (non-agent) nodes appear here only because workhorse **runs them
in-process** and hands each one a per-node `logger`. Under the retired YAML engine they
were child processes: stdout was consumed whole as the node's JSON and stderr surfaced
only on failure, so a node's account of what it decided was unrecoverable after the fact
— the gap that made a script-heavy workflow (okf-builder) hard to debug live.

Records carry the same `run_id`/`run_dir` resource as the spans, so a log line
joins to its node span and its on-disk artifacts with no correlation step. They
are correlated by an explicit `node` attribute rather than `trace_id`, which is
zeroes: workhorse never makes its node spans current, so there is no ambient
context for the SDK to attach.

No alert rule fires on logs, deliberately — liveness is already answered by the
heartbeat metrics, and paging on log *content* would mean guessing which strings
are worth waking someone for, per workflow. Logs are for reading once a metric has
told you where to look. They prune on their own shorter window
(`GROOM_LOG_RETENTION_DAYS`, 3) because they are one row per line rather than one
per node visit.

### Test runs are not telemetry

A test suite is not a run anyone comes back to, and on a machine where
`groom serve` is up it is by far the loudest producer: one `make test` of the
workflows suite wrote a six-figure number of spans, burying every real run in
the fleet view. So test telemetry is kept out at both ends — workhorse declines
to auto-enable export from a test process (`WORKHORSE_OTEL=1` still forces it
on), and the receivers drop any record whose `run_dir` is *certainly* a test
dir — one containing `pytest-of-` or `.workhorse-test/`. Neither undoes what an
older producer already wrote:

```bash
uv run groom purge-tests --dry-run   # what would go
uv run groom purge-tests             # delete it, then VACUUM to shrink the file
```

`purge-tests` casts the wider net: it also evicts runs whose dir is a
`tempfile.mkdtemp` scratch dir (`/tmp/tmpXXXXXXXX/…`), which is how the largest
single junk run in a real store got there. That one is a guess — a genuine run
launched from a mkdtemp directory matches too — so it is confined to a command
you run deliberately and can preview with `--dry-run`, rather than to the ingest
path, where the same guess would discard evidence unasked. Runs are identified
by their run dir in both cases, never by name.

### What a run cost (`groom cost`)

Where the money and the rework went, per node:

```console
$ groom cost --run RUN
node                         turns  /work      usd  share    min
----------------------------------------------------------------
plan-qa                         84   4.67   181.38  21.7%    730
document-story                  89   4.68   116.54  13.9%    602
implement-plan                  23   1.21   104.40  12.5%    317
```

Only `agent_turn` spans are counted — a node span wraps its turn, so totalling
both would double every figure, and an in-process `self.call` node spent no agent
money by definition.

`/work` is turns per work item, and it is the column to read first. A workflow
stamps `work_id` itself (the coder workflow uses the story slug), so a node at
`1.00` ran once per story while a node at `4.67` re-ran three and a half times on
average. Raw turn count tells you a node is *busy*; this tells you it is
*looping*, which is a different and usually more actionable problem.

**Cost coverage is not uniform, and the unit is harness × _provider_.** codex reports
no money at all under subscription auth. opencode reports real money through OpenRouter
and a literal `0` through a subscription provider — the same CLI, the same event shape,
because cost belongs to the provider behind it. copilot reports neither cost nor tokens
at all (it bills in premium requests).

The two ways of not pricing a turn differ in how visible they are. Nothing-reported is
recorded as absent rather than a fabricated `0.0`, so it is excluded from the sum and
shows up as a gap. A reported `0` is *summed* — so a run that spent forty minutes can
total `$0.00` and look complete. `groom cost` flags both, naming the backends:

```
note: 2 of 3 turns reported no cost, so usd and share cover only the 1 that did.
note: 2 turn(s) reported a cost of exactly 0 while spending output tokens. A turn that
      emitted tokens did not cost nothing — it was not priced. …
```

A turn that emitted no tokens and cost 0 is *not* flagged: it really was free.

Nodes that reported no cost are ranked among themselves by minutes rather than by
turn count, so an unpriced node that spent an hour in three turns still sorts above
one that spent two minutes in twenty.

Duration is comparable across harnesses but not identical: when the CLI reports a
turn duration that value is used, and when it does not (codex reports none) the
engine's own wall clock is stamped instead, which includes process spawn.

### What occupied the wall clock (`groom profile`)

For one retained run, partition observed wall time and group agent work by the
workflow's attempt and verdict labels:

```bash
groom profile --run RUN
groom profile --run RUN --json
```

The time buckets are disjoint: agent turns, deterministic nodes, infrastructure,
explicit waits, gaps between resume generations, and unclassified time sum to the
reported wall clock without counting nested spans twice. Wait time is also split by
kind (`operator`, `cap`, `retry`, `reframe`, or `exec-retry`).

Attempt and verdict groups report turns, agent time, work items, cost coverage, and
tokens for each telemetry label value. `profile` reads every retained span for the
named run rather than the paginated trace search, so a long run is not silently
truncated. As with `cost`, absent and suspicious zero pricing remain visible.

### The schema, and one footgun

Three tables — `spans`, `metrics`, `logs` — plus `attrs_json` on each, holding
whatever OpenTelemetry attributes the producer set.

**OTel attribute keys are flat strings that merely look nested.** `set_attribute`
is called with `usage.output_tokens`, and that reaches `attrs_json` as a literal
key with a dot in it — not as a nested object. So:

```sql
json_extract(attrs_json, '$.usage.output_tokens')     -- NULL, always, no error
json_extract(attrs_json, '$."usage.output_tokens"')   -- 17550
```

SQLite reads the unquoted dot as navigation into an object that is not there and
returns NULL silently. **Quote every dotted key.**

The fields most queries want dodge this entirely by being real columns on
`spans`: `duration_ms`, `total_cost_usd`, `input_tokens`, `output_tokens`,
`cache_read_tokens`, `cache_creation_tokens`, `pid`, `resume_generation`.

`resume_generation` counts how many times a run directory has been started. A
resume reuses the `run_id` and opens a fresh root span, so it is what tells a gap
between two spans apart: one that crosses a generation boundary is a
crash-and-resume, one that does not is the process waiting or thinking. They are populated at ingest
and are **nullable on purpose** — a harness that does not report cost yields NULL,
never `0.0`, because averaging a real zero together with an unknown understates
spend. Spans ingested before these columns shipped have NULL in them and are not
backfilled; `groom cost` falls back to `attrs_json`, and anything else you write
should too.

Everything else — `workhorse.node`, `backend`, `model`, `session.id`, and whatever
the workflow declared in `labels()` — stays in `attrs_json`. Adding a column means
editing both `_SCHEMA` and `_ADDED_SPAN_COLUMNS` in `groom/store.py`: the first
only runs on a fresh database, so a column added there alone never appears on a
`groom.db` that already exists.

### Querying it yourself

There is no privileged view: the dashboard, `groom status`, and any agent all
read the same SQLite file, so `sqlite3` answers anything the CLI doesn't.

```bash
sqlite3 -header "$(uv run groom db-path)" "
  SELECT node, ROUND(end_ts - start_ts, 1) AS secs, status
  FROM spans WHERE run_id = 'RUN' ORDER BY start_ts DESC LIMIT 20;"
```

```sql
-- Which node is open right now, and for how long (no span exists for it yet).
SELECT json_extract(attrs_json, '$.node') AS node, value AS secs_in_node
FROM metrics WHERE name = 'workhorse.node.elapsed_s'
ORDER BY ts DESC LIMIT 1;

-- Recovery-ladder events: retries, reframes, compactions, watchdog kills.
SELECT s.node, e.value ->> 'name' AS event, datetime(e.value ->> 'ts', 'unixepoch')
FROM spans s, json_each(s.attrs_json, '$.events') e
WHERE s.run_id = 'RUN' ORDER BY s.start_ts;

-- Slowest nodes across every run.
SELECT node, COUNT(*) n, ROUND(AVG(end_ts - start_ts), 1) avg_s
FROM spans WHERE name NOT LIKE 'run:%' GROUP BY node ORDER BY avg_s DESC LIMIT 10;

-- From a span to the artifacts that produced it (prompt.md, output.json).
SELECT DISTINCT run_dir FROM spans WHERE run_id = 'RUN';
```

The last one is why this stays local: `run_dir` is a resource attribute on every
span, so a query hands you the path to the prompt and outputs on disk — a join a
hosted trace backend cannot make.

See `docs/features/groom/` at the repo root for the full design — groom's own OKF book,
queryable with `ostler graph --surface groom`.
