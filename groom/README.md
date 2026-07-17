# groom

A local, single-process web dashboard for `workhorse` agent-workflow operator
gates. Run `groom serve` on your host while `author`/`coder` (or any other
`workhorse`-based workflow) containers run in the background; `groom` shows
every running workflow, pages you the moment one blocks on an operator gate,
and lets you answer the gate right from the browser — no more finding and
restarting blocked containers one by one. `await_operator.py` blocks in
place via `inotify` rather than exiting, so the container keeps running and
just wakes up once you answer; `groom` only falls back to `docker start` if
a container has genuinely stopped.

## How it works

- Each workflow container runs a tiny in-container sidecar, `groom-sidecar`,
  that watches its own `/workspace` and `/runs` mounts with `inotify` and holds
  one persistent WebSocket open to the host's `groom` (dialing out over
  `host.docker.internal`, so no inbound reachability is needed). It advertises
  full state on connect, streams `progress`/`blocked` deltas, and serves the
  Files/Diff panels from local disk via `getTree`/`getFile`/`getDiff` RPC over
  the same socket. The connection is best-effort and re-syncs on reconnect —
  a container with no `groom` listening behaves exactly as it does today. See
  `docs/features/groom/sidecar-live-sessions.md` for the message schema and the
  local `reload` dev loop.
- `groom` itself holds all state in memory (no database, no broker) and
  pushes updates to open browser tabs over a websocket using htmx +
  htmx-ext-ws. Gate questions render as Markdown (`marked`, sanitized with
  `DOMPurify` before insertion since the content is LLM-authored) and each
  workflow row can expand a `git diff` of its working tree (rendered with
  `diff2html`). All front-end assets are vendored locally; nothing is loaded
  from a CDN at runtime.
- On startup (or on-demand refresh), `groom` runs a one-shot `docker ps -a` +
  `docker inspect` reconciliation scan so workflows that were already
  blocked before `groom` was started are still picked up.

## Usage

```
uv run groom serve                # binds 0.0.0.0:8787 by default (see note below)
uv run groom serve --host 127.0.0.1   # loopback only (no container access)
```

> **Binding.** groom defaults to `0.0.0.0` so the in-container `groom-sidecar`s
> can reach it over the docker bridge (`host.docker.internal` → the bridge
> gateway on Linux, not loopback). groom has **no authentication** — it controls
> docker and answers operator gates — so only run it on a trusted machine; it
> prints a one-line warning on any non-loopback bind (`--allow-non-loopback`
> silences it). Use `--host 127.0.0.1` to bind loopback only.

## Telemetry collector (OTLP) + AFK alerting

`groom` is also the default local **OpenTelemetry collector** for `workhorse`
runs (see `docs/workhorse-otel.md` at the repo root). The same uvicorn process
and port expose standard OTLP/HTTP receivers — `POST /v1/traces`,
`POST /v1/metrics` and `POST /v1/logs` — so a run started with

```bash
pip install 'workhorse-agent[otel]'
WORKHORSE_OTEL=1 OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:8787 workhorse run coder
```

streams node/agent-turn spans, gas/heartbeat metrics, and the log records of the
engine and its in-process script nodes into `groom`. Because a
pushed span carries its own identity, **native (non-Docker) runs appear too** —
no discovery gate. Spans and metrics persist in an embedded SQLite file
(`groom.db` in the platform data dir; override with `GROOM_DB`), searchable
from the dashboard's *Telemetry* pane, via `GET /traces?run=…&node=…&status=…&
slower_than=…`, or with raw `sqlite3` queries. Rows older than
`GROOM_RETENTION_DAYS` (14) are pruned at startup.

Alert rules run on every ingest plus a periodic tick, and page you through
browser notifications **and** an away-from-keyboard push — configure
`GROOM_NTFY_TOPIC` (posts to `https://ntfy.sh/<topic>`; override the server
with `GROOM_NTFY_URL`) and/or `GROOM_WEBHOOK_URL` (JSON `{"title","message"}`):

| Rule | Fires when | Knob (default) |
|---|---|---|
| STALL | a live run emits **nothing** — no span, no heartbeat | `GROOM_STALL_MIN` (90) |
| STUCK | the run **is** heartbeating but has sat in one node too long | `GROOM_STUCK_MIN` (75) |
| BUDGET | a run still live past the wall-clock ceiling | `GROOM_MAX_HOURS` (24) |
| CHURN | the same node span repeats with no gas refuel | `GROOM_CHURN_REPEATS` (5) |
| WATCHDOG | a `watchdog_kill` span event arrives | — |
| GAVE-UP | a give-up node's span arrives | `GROOM_GIVEUP_NODES` (qa_give_up,fix_give_up) |

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
| `alive`, node age large, agent `idle` small | a long but **streaming** turn — healthy |
| `alive`, node age large, agent `idle` large | **wedged** inside the node (hung tool/API/script) |
| no heartbeat (`DEAD?`) | the process is gone — SIGKILL, OOM, crashed host |

## What was it saying? (`groom logs`)

`status` says *where* a run is; logs say what it was doing on the way there.

```bash
uv run groom logs --run <id>                 # everything, oldest-first
uv run groom logs --run <id> --node select_item
uv run groom logs --level WARNING            # a FLOOR: WARNING + ERROR + FATAL
uv run groom logs --contains "over budget"
```

Script nodes appear here only because workhorse now **runs them in-process** and
calls their `main(logger)`. As child processes their stdout was consumed whole as
the node's JSON and their stderr surfaced only on failure, so a script's account
of what it decided was unrecoverable after the fact — the gap that made a
script-heavy workflow (okf-builder) hard to debug live.

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

See `docs/features/groom.md` at the repo root for the full design.
