---
type: feature
slug: workhorse-otel
title: workhorse OpenTelemetry, collected by groom
status: implemented
---
# workhorse OpenTelemetry, collected by groom

> **Related:** [groom](groom.md) (the collector host) · [sidecar-protocol](groom/sidecar-protocol.md)
> (the push path this partly subsumes) · [operator-inbox](groom/operator-inbox.md) (the answer
> write-back OTel does *not* replace). This doc is a pre-implementation design brief.

Status: **implemented** (2026-07-13) — phases 1–3 plus the Plane-3 guards landed as designed:
`workhorse/otel.py` (+ the `otel` extra, node spans via the `_append_event` choke point, agent-turn
spans, cap-wait heartbeat, watchdog/ladder span events, gas metrics, `WORKHORSE_MAX_RUNTIME_S`);
`groom/{otlp,store,alerts,notify}.py` + `/v1/traces`, `/v1/metrics`, `/traces` and the dashboard
telemetry pane; the coder workflow's zero-diff guard + `make groom-serve`. The one deliberate
deviation: give-up detection is node-NAME based in groom (`GROOM_GIVEUP_NODES`, default
`qa_give_up,fix_give_up`) rather than a workhorse-emitted span event, keeping the engine
workflow-agnostic. Phase 4's sidecar retirement is still pending, as planned — OTel and the
sidecar coexist until the gate-over-OTel path is proven. Operator docs: `workhorse/docs/GUARDRAILS.md`
(producer env) and `groom/README.md` (collector + alert rules). The design brief below is preserved as
written.

**Amended 2026-07-17 — live-run visibility.** The design above is trace-first, and traces have a
structural blind spot it did not account for: OTel exports a span when it **ends**, so the node a run
is currently sitting in has no span anywhere, and the node that *hangs* never gets one at all. The
original telemetry could therefore say where a run had been, never where it was — the stalled node was
inferable only from the last completed span's `workhorse.next` plus silence. Worse, that silence was
indistinguishable from a healthy long agent turn, so groom's STALL rule false-fired on any turn longer
than `GROOM_STALL_MIN`.

The brief's own crux — *"a heartbeating run is provably alive; silence is provably a hang"* — was the
answer; it had just been scoped to cap-wait sleeps. Generalising it (metrics ride a periodic reader, so
they escape a process whose spans are all still open):

- `workhorse.node.active` / `workhorse.node.elapsed_s` — **where** the run is and for how long, direct
  rather than inferred;
- `workhorse.run.heartbeat` — a daemon-thread tick proving the *process* lives, for any node type. At the
  time this was the only liveness a `script:` node could emit: `SubprocessScriptRunner` captured a
  buffered child, so there was no stream to observe (and, for the same reason, in-script `run_tool` spans
  would have been inert — the child had no active telemetry). Superseded in part by amendment (b) below,
  which moves scripts in-process; the run heartbeat remains the liveness signal for a node that blocks
  the main thread, script or not;
- `workhorse.turn.heartbeat` / `workhorse.turn.idle_s` — emitted from the top of the `select` loop in
  `stream_subprocess` (the one path every backend shares, so opencode/codex/aider get it too), which
  separates *streaming* (idle low) from *wedged* (idle climbing);
- `run_dir` as a resource attribute — a span now leads back to its own `prompt.md` / `output.json`.

groom splits the old rule accordingly: **STALL** = emitting nothing at all (the process is gone),
**STUCK** = heartbeating but parked in one node. `groom status` reports the live picture the trace
cannot, over the same SQLite any agent can query.

**Amended 2026-07-17 (b) — script nodes in-process, and the third leg.** The amendment above named a
consequence it then lived with: a `script:` node ran as a buffered child, so it had no active telemetry
and its stdout was consumed whole as the node's JSON — the run heartbeat was "the only liveness a script
node can emit", and a script's own account of what it decided was unrecoverable after the fact. In a
script-heavy workflow (okf-builder is almost entirely script and branch nodes) that is most of the run
being observable only as "still alive".

Scripts are now **imported and their `main(logger)` called in the engine's process** (`runner/script.py`,
`InProcessScriptRunner`), so their log records ride the engine's own root logger — same handlers, same
`run_id`/`run_dir` resource, no per-script SDK init — and reach a new `POST /v1/logs` receiver in groom
(`groom logs --run --node --level`). Logs are the third OTLP leg the original design left out.

Design points worth keeping:

- **Compatibility is by signature, not decree.** Every script in the library (and in any private overlay
  this repo cannot see) declares `def main()`. `_wants_logger` inspects the signature, so both shapes
  coexist and migration is per-script rather than a flag day. A script with no `main()` still runs under
  `__main__`; one *with* main is executed under a sentinel module name so its own guard cannot call
  `main()` argument-less first.
- **stdout stays the data channel; logs bypass the capture.** The console handler binds the real stderr
  at setup, *before* the runner redirects streams to capture JSON — which is what keeps a script's logs
  on the terminal instead of swallowing them into the outputs parse.
- **Correlation is an explicit `node` attribute, not `trace_id`.** The engine opens node spans with
  `start_span`, never `start_as_current_span`, so nothing is in the ambient context and every record's
  trace_id is zeroes. Worth knowing before trying to join logs to spans by trace.
- **The SDK's own logs are excluded from the OTel handler**, or a down collector self-amplifies:
  export fails → logs → queued → export fails.
- **The cost is crash isolation, one-directionally.** A child could only return a bad exit code; an
  imported script that `os._exit`s or segfaults takes the run with it. Bounded by what was already true
  (a failing script node has always ended the run — the recovery ladder is agent-only), but the *clean*
  ending is lost. `WORKHORSE_SCRIPT_INPROCESS=0` restores the child-process path.

Not addressed: script nodes still have no timeout and no watchdog, and workhorse's engine output is
still `print()` rather than `logging`, so what flows to `/v1/logs` today is overwhelmingly the scripts'.

Proposed 2026-07-08. Instrument the `workhorse` engine with OpenTelemetry (opt-in,
no-op by default) and extend `groom` into a local OTLP collector + searchable store + alerter, so an
away-from-keyboard operator is paged when the `coder` workflow churns or hangs — instead of finding a
run that burned days.

## Context

The `coder`/`author` workflows run under `workhorse` unattended for days. The inner loops are already
well-guarded — the progress-metered gas tank (`main.py _GasTank`/`OutOfGasError`), per-loop `guard_*`
caps, `qa_give_up`/`fix_give_up` skip sets, backlog dedup, the per-node SIGKILL watchdog
(`runner/agent.py`), and the retry/rephrase/compact recovery ladder. What is missing is **external
observability and AFK alerting**: nothing pages the operator when a run goes wrong, and `groom` today
only sees Docker runs (via browser Notification needing an open tab).

An earlier sketch polled run artifacts (`events.jsonl`, `checkpoint.json`, `run.json`) and grepped the
log for cap-wait markers. Instrumenting with OpenTelemetry and making `groom` the collector is the
stronger architecture for three structural reasons:

- **The hang-vs-cap-wait ambiguity becomes provable.** A legitimate multi-day spending-cap sleep looks
  identical to a hang from artifacts alone (the run sits inside one node). The artifact-poller had to
  grep the log for `⏸ still paused`. With OTel, the cap-wait *emits a heartbeat metric each tick*
  (`runner/agent.py:1092-1104 _sleep_with_notice`) — a heartbeating run is provably alive; silence is
  provably a hang. No log-grepping.
- **`groom`'s native-run blindness is fixed.** Discovery is Docker-only —
  `discovery.py:46 is_workhorse_container` requires `/workflow /runs /workspace` mounts, so native
  `agent-native-bg` runs never appear. A pushed span carries its own identity in the payload (exactly
  like `push_blocked` does today), sidestepping the Docker gate — native runs finally show up.
- **Per-node latency + token/cost attribution comes for free.** `events.jsonl` is already span-shaped
  (`enter`/`done` per node); agent-turn spans can carry `duration_ms` + `usage.{input,output,cache}`
  tokens. The cost-per-node scorecard the codebase was designed for (`artifacts.py:143` docstring)
  finally has a consumer.

`groom` is already ~80% a collector: an async Litestar/uvicorn single process with three
`@post("/push/…")` JSON receivers, bounded in-memory stores (`state.py LOG = deque(maxlen=200)`), and a
`broadcast → browser-notify` path. Turning it into an OTLP collector is additive, not a rewrite.

## Architecture — three planes

```
workhorse run ──OTLP POST──▶ groom  ──▶ SQLite spans/metrics (durable, searchable)
 (producer, opt-in)  /v1/traces      │        │
                     /v1/metrics       ├─▶ alert-rule eval (stall / budget / churn)
                                       │        └─▶ ntfy/webhook (AFK)  +  browser notify
                                       └─▶ dashboard trace/fleet/search view
```

### Plane 1 — Instrument workhorse (producer; opt-in, no-op by default)

**New `workhorse/otel.py`** reads `WORKHORSE_OTEL` / `OTEL_EXPORTER_OTLP_ENDPOINT` once at import
(mirrors the `_configured_gas()` / `AGENT_*` module-constant pattern). Unset ⇒ a **no-op tracer/meter**
(zero overhead, the default). Set ⇒ configure an OTel SDK `TracerProvider`/`MeterProvider` with a
`BatchSpanProcessor` and the standard OTLP/HTTP exporter. Resource attrs: `service.name=workhorse`,
`run_id`, `workflow`, `repo`, `branch`.

Instrumentation sites (verified, `stablemate/workhorse/workhorse/`):

- **Root span** — `run()` around the `_step_loop` call (`main.py:176-186`); end at `writer.finish()`
  (`artifacts.py:223`); `status=ERROR` on `OutOfGasError` (`main.py:195`), `BackendInvocationError`
  (`:202`).
- **Node spans — one choke point.** Inject the tracer into `ArtifactWriter` (built `main.py:165`;
  nested-flow children via `.subscope`, `artifacts.py:85`) and emit from
  **`_append_event` (`artifacts.py:124-140`)** — every `enter`/`done`/`terminal` funnels here and it is
  already best-effort (swallows `OSError`), so spans never crash a run. `(node, seq)` uniquely IDs each
  node visit → clean start/end pairing even across loop re-visits; the `next` field → span link to the
  successor. Flow `depth` (`main.py:565`) → nested spans.
- **Gas gauge** — `_GasTank.burn/refuel` (`main.py:261-301`): `gas`/`capacity` gauge + refuel counter.
  Flat gas + high span rate on a small node set = churn.
- **Agent-turn spans** — thread a tracer into `run_agent` (called `main.py:350-356`). Span at
  `_invoke_claude` invoke (`agent.py:801-805`; attrs `model`/`effort`/`timeout`); on the `result` event
  (`agent.py:1224-1228`) attach `duration_ms` + token usage. Retry/rephrase/compact
  (`agent.py:634/645/675/751`) as span events.
- **Cap-wait heartbeat (the crux)** — a heartbeat metric each tick in `_sleep_with_notice`
  (`agent.py:1092-1104`). Distinguishes a legit multi-hour/day wait from a hang.
- **Watchdog / give-up events** — watchdog SIGKILL (`_fire`, `agent.py:141-151`, **runs on a daemon
  thread — emission must be thread-safe**) → span event `status=ERROR`; `qa_give_up`/`fix_give_up`
  nodes → span events for the "gave up" alert.
- **`pyproject.toml`** — new opt-in extra `otel = ["opentelemetry-sdk",
  "opentelemetry-exporter-otlp-proto-http"]`; no new *required* deps (`requires-python >=3.12`).

### Plane 2 — groom as OTLP collector (consumer)

- **Wire format: standard OTLP/HTTP protobuf.** `groom` adds `opentelemetry-proto` to decode —
  `ExportTraceServiceRequest.FromString(await request.body())`. Going fully standard means `workhorse`
  can *also* point at Jaeger / Grafana Tempo with zero code change; `groom` is simply the default local
  backend. (Alternative to avoid a protobuf dep on `groom`: a thin custom OTLP/**JSON** exporter on the
  `workhorse` side — still the real SDK, ~60 lines — leaving `groom` on stdlib JSON.)
- **New receivers** in `create_app()` route list (`app.py:301`): `@post("/v1/traces")`,
  `@post("/v1/metrics")` — mirror `push_blocked` (`app.py:164`): parse body → store → eval rules →
  broadcast. Inherits `groom`'s loopback-only, no-auth posture (`cli.py:30-36`) — fine for a local
  collector.
- **Storage — embedded SQLite (stdlib `sqlite3`, zero new dep).** `groom.db` in `groom`'s data dir: a
  `spans` table (`trace_id, span_id, parent_id, run_id, workflow, repo, node, name, start_ts, end_ts,
  status, attrs_json`) + a `metrics` table (gas, tokens, rework counters, cap-wait heartbeats). Durable
  across `groom serve` restarts and searchable. The in-memory ring (`state.py`) stays only as a hot
  cache for the live dashboard + rule state (`dict[run_id → RunTelemetry]`: open root span → budget;
  last-span-ts → stall; per-node counts + gas → churn; last heartbeat ts). Single event-loop ⇒ no locks
  (`state.py:20`). Each run's raw `events.jsonl` on disk remains the append-only record-of-truth;
  SQLite is the queryable fleet index. Prune spans older than N days to bound growth.
- **Alerts — new `groom/alerts.py`.** Evaluate on each ingest; dedupe per `(run_id, rule)`; thresholds
  via env:

  | Rule | Fires when |
  |---|---|
  | STALL | no span **and** no cap-wait heartbeat for a run in `GROOM_STALL_MIN` (90) |
  | BUDGET | open root span age > `GROOM_MAX_HOURS` (24) |
  | CHURN | same node span repeats ≥ `GROOM_CHURN_REPEATS` (5) with gas not refueling / no commit span |
  | WATCHDOG | a watchdog-kill span event arrives |
  | GAVE-UP | a `qa_give_up`/`fix_give_up` span event arrives |

- **Notify.** Browser: reuse `render.render_notify_script` + `state.broadcast` (`app.py:185-187`)
  exactly as blocked-gates do. **AFK: new `groom/notify.py`** outbound push (ntfy
  `POST https://ntfy.sh/<topic>` and/or a generic webhook), stdlib `urllib`, best-effort, modeled on
  `sidecar._push` (`sidecar.py:47`). This is the piece that reaches a phone (browser Notification needs
  an open tab).
- **Search (new capability).** Today `groom`'s `search` route (`app.py:65`) only filters the *live
  in-memory* worker list — there is no history search. Telemetry search is SQLite-backed: (a) a
  `/traces?run=…&node=…&status=…&slower_than=…` endpoint over the `spans` table, rendered as HTML
  fragments like the other regions; (b) raw SQL for ad-hoc digging —
  `sqlite3 groom.db 'SELECT node, avg(end_ts-start_ts) … GROUP BY node ORDER BY 2 DESC'` (slowest
  nodes), `… WHERE status='ERROR'` (watchdog/failures), `SELECT run_id, sum(output_tokens) … GROUP BY
  run_id` (cost per run), `… WHERE name='cap_wait'` (which runs slept, how long); (c) for one run, the
  on-disk `<run>/<node>/{prompt.md,output.json}` artifacts for transcript-level detail.
- **Dashboard (polish)** — a `traces`/`telemetry` mode on the activity bar
  (`templates/dashboard.html:16-29`): fleet timeline of node spans + gas + fired alerts, HTML fragments
  like the existing regions.
- **Run it continuously** — `groom serve` under nohup/systemd; add an `agents.mk` convenience target.

### Does OTel replace the sidecar?

Mostly. The `groom-sidecar` (in-container, inotify-watches `/workspace`+`/runs`, `sidecar.py:47 _push`)
does two separable things:

- **Telemetry OUT** — `push_progress` (current node), `push_blocked` (a `STATUS: AWAITING_OPERATOR`
  file appeared), `push_exited` (exit code). **All three are subsumed by OTel:** node spans (progress),
  an `awaiting_operator` span event (block), root-span end (exit).
- **Answer WRITE-BACK** — *not* telemetry; OTel does not cover it. Answering a gate writes
  `STATUS: ANSWERED` back into the run's files (`gates.answer_gate`, from `app.py:218-225`). That write
  is already `groom`'s job via its Docker volume access — independent of the sidecar. For native runs
  `groom` is on the same filesystem and writes directly (the sidecar was never involved).

So the sidecar can be **retired** once (1) `workhorse` emits the `awaiting_operator` span event and
(2) the answer-write path is confirmed working without the sidecar's `snapshot()`/`--query`. Treat this
as an explicit later phase — keep the sidecar and OTel coexisting (both best-effort pushes) until the
gate-over-OTel path is proven, then drop it.

### Plane 3 — self-defense guards (optional, complementary)

OTel/groom makes churn visible and paged; these make a run stop itself with nothing watching:

- **Engine wall-clock budget** `WORKHORSE_MAX_RUNTIME_S` in `main.py` (`RunBudgetExceeded` beside
  `OutOfGasError`, checked at `_step_loop` loop-top ~`:336`, counted from original `writer._started_at`
  so it survives `--resume`). Plus the missing `_GasTank` unit test.
- **Zero-diff churn guard** in `coder/workflow.yaml` — consume the `committed:"no"` that
  `commit-story.py` already emits; `incr_zero_diff`/`guard_zero_diff` after `commit_story` (~`:1087`),
  give up after K consecutive no-op commits.

## Operational — no new server / infra

- **Collector = groom itself.** The OTLP receiver is new endpoints on the *same* uvicorn process and
  port (`127.0.0.1:8787`) — no OTel Collector binary, no Jaeger, no Prometheus, no Grafana.
- **Storage = an embedded SQLite file.** No database server.
- **Producer = an in-process library.** The OTel SDK is imported by `workhorse`; no agent/daemon.
- **One operational change:** run `groom serve` continuously (nohup/systemd) as the always-on
  collector. Per-run setup is `pip install '.[otel]'` + `WORKHORSE_OTEL=1` +
  `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:8787`.
- **Resilience:** exports are best-effort — if `groom` is down, spans drop silently, the on-disk
  `events.jsonl` remains the durable record, and the Plane-3 guards still bound the run. A collector
  outage cannot wedge or slow a run.

## Phasing (each phase independently useful)

1. **Minimal end-to-end paging.** `otel.py` no-op scaffold + node/root spans via the `_append_event`
   choke point + `groom` `/v1/traces` receiver + SQLite store + STALL/BUDGET rules + `notify.py` ntfy.
   Native runs visible; phone-paged on stall/budget. *Smallest cut that solves the ask.*
2. **Hang-proof + churn.** Agent-turn spans + cap-wait **heartbeat** + watchdog/give-up events +
   CHURN rule + token/cost attributes.
3. **Metrics + dashboard + search.** Gas/rework gauges, `/v1/metrics`, `/traces` search, traces view.
4. **Self-defense (Plane 3)** + retire the sidecar.

## Files

**workhorse** (`stablemate/workhorse/`): **NEW** `workhorse/otel.py`; edit `workhorse/artifacts.py`
(`_append_event`/`__init__`/`subscope`), `workhorse/main.py` (root span, gas gauge, thread tracer into
`run_agent`; Plane-3 budget), `workhorse/runner/agent.py` (turn spans, cap-wait heartbeat, watchdog
event), `pyproject.toml` (`otel` extra). **NEW** `tests/test_gas_tank.py`.

**groom** (`stablemate/groom/`): edit `groom/app.py` (`/v1/traces`,`/v1/metrics` handlers + route list +
`/traces` search), **NEW** `groom/store.py` (SQLite spans/metrics + queries), `groom/state.py`
(hot-cache rule state), **NEW** `groom/alerts.py`, **NEW** `groom/notify.py`, `groom/render.py` +
`templates/dashboard.html` (traces/search view), `pyproject.toml` (`opentelemetry-proto`).

**workflow** (`vigilant-octo/`): `agents/workflows/coder/workflow.yaml` (zero-diff guard) + **NEW**
`tests/test_zero_diff_guard.py`; `.agents/agents.mk` (`groom serve` daemon target).

## Verification

- **Producer:** run a tiny workflow with `WORKHORSE_OTEL=1
  OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:8787` against a throwaway `nc -l`/echo server; assert
  well-formed OTLP POSTs (root + node spans, correct parent nesting). Unit-test the no-op path: unset ⇒
  no-op tracer, `_append_event` unchanged, near-zero overhead.
- **Collector:** POST a captured OTLP payload to `/v1/traces`; assert spans land in SQLite, a
  STALL/BUDGET/CHURN rule fires on crafted inputs, and `notify.py` is invoked (mock the outbound POST).
  Assert a cap-wait heartbeat **suppresses** STALL.
- **End-to-end:** `groom serve`; a mock node that sleeps past the stall window with **no** heartbeat ⇒
  ntfy on phone within `GROOM_STALL_MIN`; a run that cap-waits (heartbeating) ⇒ **no** false STALL.
  Confirm the **native** run appears in the fleet view (Docker-gate bypass).
- **Plane 3:** `pytest stablemate/workhorse/tests/test_gas_tank.py`; `WORKHORSE_MAX_RUNTIME_S` small on
  a slow loop ⇒ `RunBudgetExceeded` exit 1; `test_zero_diff_guard.py` via `WorkflowRun` with mocked
  zero-diff `git`.
