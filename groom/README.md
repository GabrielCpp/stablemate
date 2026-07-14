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
and port expose standard OTLP/HTTP receivers — `POST /v1/traces` and
`POST /v1/metrics` — so a run started with

```bash
pip install 'workhorse-agent[otel]'
WORKHORSE_OTEL=1 OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:8787 workhorse run coder
```

streams node/agent-turn spans and gas/heartbeat metrics into `groom`. Because a
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
| STALL | no span AND no cap-wait heartbeat from a live run | `GROOM_STALL_MIN` (90) |
| BUDGET | a run still live past the wall-clock ceiling | `GROOM_MAX_HOURS` (24) |
| CHURN | the same node span repeats with no gas refuel | `GROOM_CHURN_REPEATS` (5) |
| WATCHDOG | a `watchdog_kill` span event arrives | — |
| GAVE-UP | a give-up node's span arrives | `GROOM_GIVEUP_NODES` (qa_give_up,fix_give_up) |

The crux: a legitimate multi-day spending-cap sleep **heartbeats** (the
`workhorse.cap_wait.heartbeat` metric), so it never false-STALLs — silence is
provably a hang. Alerts dedupe per `(run, rule)`. Run `groom serve` under
nohup/systemd as the always-on collector (the consuming repo's
`make groom-serve` target does exactly that).

See `docs/features/groom.md` at the repo root for the full design.
