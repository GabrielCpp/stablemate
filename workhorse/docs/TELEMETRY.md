# Telemetry — observing an unattended run

A run meant to survive a week is a run nobody is watching. workhorse streams
OpenTelemetry spans, metrics and log records to a local OTLP collector so something else
can watch it: what state it is in, what each agent turn cost, when the recovery ladder
fired, and — crucially — whether a long silence is a legitimate spending-cap sleep or a
hang.

It is off unless a collector is actually there, and a complete no-op when it isn't. This
document covers turning it on (and off), what is emitted, how turn spans are normalized
across harnesses so costs are comparable, and how to tag spans with your own unit of
work.

For the resilience ladder those span events come from, see
[docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md).
For `labels()`, see
[docs/AUTHORING.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/AUTHORING.md#labels-and-saying-what-the-run-is-doing).

## Turning it on (and off)

Start a local collector — `groom` by default, which stores spans in SQLite and pages you
(ntfy/webhook + browser) on stall/stuck/churn. Nothing else is required: the OTel SDK is a
dependency of workhorse, so at run start it probes the OTLP endpoint and, if something is
listening, streams spans/metrics/logs to it.

```bash
groom serve                                                # now every run is observed
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:8787   # the default
export WORKHORSE_OTEL=0                                    # …unless you opt out
```

**Enablement is a tri-state.**

| `WORKHORSE_OTEL` | Behavior |
|---|---|
| _unset_ (default) | **Auto** — probe the endpoint; enable only if it answers *and* this is not a test process |
| `1` / `true` / `yes` | Force on — no probe, and the test-process guard is ignored (for a collector that comes up later, or one a TCP connect can't see) |
| `0` / `false` / `no` | Force off — no probe, never enabled |

The probe is one TCP connect bounded by `WORKHORSE_OTEL_PROBE_S`, so a machine with no
collector pays microseconds on loopback and stays a complete no-op. Auto-on is the default
because the runs most worth observing are the unattended week-long ones — exactly the runs
nobody remembers to export a variable before launching.

**Auto also declines inside a test process.** A suite run on a machine with `groom serve`
up is otherwise the collector's single largest producer — one `make test` of the workflows
suite wrote a six-figure number of spans — and none of it is a run anyone will come back
to. `start_run` recognizes a test process three ways, because the suites here run three
ways: `PYTEST_CURRENT_TEST` in the environment, `pytest` already imported (collection, and
xdist workers), or an `argv[0]` of `test_*.py` / `conftest.py` (the repo's standalone-test
convention). An explicit `WORKHORSE_OTEL=1` still exports, which is what the telemetry
tests themselves rely on; groom independently drops and can purge test-run telemetry from
older producers (`groom purge-tests`).

## What is emitted

A root span per run, a span per node visit (nested through flows), a span per agent-CLI
turn with duration + token usage + cost (and a `session.id` attribute linking it to the CLI
session transcript), span events for the recovery ladder (retry/reframe/compact/
watchdog-kill), **log records** from the driver and the node functions it calls
(`groom logs`), and the live gauges below. Exports are best-effort, so a collector that
dies mid-run can never slow or wedge a run; `events.jsonl` on disk remains the durable
record. Any standard OTLP/HTTP backend (Jaeger, Grafana Tempo) works unchanged.

There is also a wall-clock ceiling, `WORKHORSE_MAX_RUNTIME_S` — see
[GUARDRAILS.md](GUARDRAILS.md).

## Logs — the run's own narrative

Whenever telemetry is on, the root logger also ships to the collector's `/v1/logs`,
carrying the same `run_id`/`workflow`/`run_dir` resource as the spans. Console
output is unaffected — the console handler binds the real stderr at setup, so log
records reach the terminal even while a node's stdout/stderr are redirected for JSON
capture.

Two details worth knowing when reading them:

- **Correlation is by a `node` attribute, not `trace_id`.** The engine opens node
  spans with `start_span`, never `start_as_current_span`, so nothing is in the
  ambient OTel context and every log record's `trace_id` is zeroes. The node is
  stamped explicitly instead; `groom logs --node <id>` reads that.
- **The SDK's own diagnostics are excluded from the OTel handler** (they still
  print). Otherwise a down collector is self-amplifying: the exporter fails, logs
  the failure, that log is queued, its export fails, and so on.
- The logs SDK still lives under private module paths (`opentelemetry.sdk._logs`);
  if an upgrade moves them, logs degrade to console-only and traces/metrics are
  unaffected.

The engine's own **narrative** — the per-transition dispatch lines (`state →`, `call →`,
`agent →`, `flow →`, `await →`, `resume →`) and per-node error/resume messages — goes through the
root logger too (`workhorse.engine`), so it ships to `/v1/logs` alongside the script
nodes' records whenever telemetry is on, and a run's own progress is visible in
`groom logs` / the dashboard, not just on the local console. What remains on `print()`
is deliberately console-only: the pre-run banner (emitted before the logger is set up)
and the final terminal summary (emitted after `end_run` has already flushed and shut
telemetry down), plus the CLI-wrapper's exit messages on the crash paths, where
telemetry is being torn down.

## One failure is one ERROR span

A span is opened by an `enter` event and closed by the matching `done`, so a body that
raises never emits its own close. Each frame that can raise — a `self.call`, a
`self.agent`, a `self.handoff`, a state body — is therefore bracketed by
`otel.scope()`, a context manager (and, being a `@contextmanager`, a decorator too)
that closes in its own `finally` every span the body left open, at the depth that
opened it. A node span's duration then runs to the moment its work stopped, not to the
moment the process gave up.

The error is recorded **once**, on the innermost frame — the one whose body actually
raised:

| Attribute / status | Means |
|---|---|
| `status = ERROR` + `error.class` | this span is the one that broke — exactly one per run |
| `workhorse.outcome = error` | an outer frame the failure propagated through |
| `workhorse.outcome = abandoned` | still open at `end_run`; closed by the backstop, not by its own scope |
| `workhorse.outcome = control` + `workhorse.control` | a frame a **control unwind** left — the run moved, it did not break |
| `workhorse.terminal` (root) | the run-level verdict, on every run, failed or not |

Nesting depth is not a count of failures. Before this, one `AttributeError` three
frames down closed as three ERROR spans, so a dashboard summing `status = 'ERROR'`
(groom's per-run error badge) reported "3 errors" for one defect — and the number moved
when the *shape* of a workflow changed rather than when anything broke. The root only
takes the ERROR status when nothing below it already carried the failure.

Neither is every raise a failure. `ReloadRequested` travels as an exception because it
has to leave an arbitrarily deep stack of re-entrant `drive` frames, but the operator got
what they asked for: those frames close here, cleanly, with no ERROR status and without
spending the once-per-run error slot a genuine failure needs. An exception class opts in
by setting `workhorse_control_unwind = True` on itself — read off the instance, so
`otel.py` stays the leaf that imports nothing from the rest of workhorse. `AgentRunner.turn`
applies the same rule to the *turn* span it closes for a cut turn; without the node/state
half, a successful `control reload` badged the run with its one and only error.

## Turn cost and tokens, normalized across harnesses

Each backend reports a turn's consumption in its own vocabulary — claude's `result`
event, codex's `turn.completed`, opencode's per-step `step_finish`, cline's terminal
`run_result` — and until `runner/usage.py` existed only claude's was parsed. That is
not a cosmetic gap: it meant 21% of recorded turns carried no usage at all, all of them
non-claude, which is precisely the comparison ("does this model class cost less per unit
of work") the store exists to answer.

All backends now funnel through one normalizer and land on claude's key names
(`input_tokens`, `output_tokens`, `cache_read_input_tokens`,
`cache_creation_input_tokens`, `reasoning_output_tokens`, `total_cost_usd`), so the
spans already in the store stay queryable alongside the new ones. Three decisions in
there are deliberate and worth not undoing:

- **Absent ≠ zero.** A harness that doesn't report money yields no `total_cost_usd`
  attribute rather than `0.0`. Averaging a real zero together with an unknown
  understates spend.
- **Per-step reports are summed.** opencode emits one event per step, so a turn that
  calls three tools reports three times; only the sum is the turn's cost.
- **Extraction is tolerant, not a per-backend switch.** An unrecognized shape falls
  back to a bounded search for a token-shaped dict, and finding nothing costs a missing
  attribute — never an exception on the hot path of every streamed event.

**Coverage is not uniform, and the unit is harness × _provider_, not harness.** All
verified against live turns:

| harness | provider | tokens | cost |
| --- | --- | --- | --- |
| claude | Anthropic | yes | yes |
| opencode | OpenRouter | yes | yes — real money |
| opencode | subscription OAuth | yes | **a literal `0`** |
| cline | OpenRouter | yes | yes — real money |
| codex | subscription auth | yes | **none reported** |
| copilot | — | **none** | **none** — bills in *premium requests* |

The two ways of not pricing a turn are not equally visible, and the second is the
dangerous one:

- **Nothing reported** yields **absent, not zero** — a fabricated `0.0` would average
  into "this turn was free". A NULL is excluded from a `SUM` and shows up as a gap.
- **A reported `0`** is summed. So an opencode run on a subscription provider totals
  `$0.00` over turns that really spent tokens and wall-clock, and the total *looks*
  complete. Nothing here corrects it — a genuinely free model reports identically — so
  `groom cost` counts turns that priced themselves at exactly zero *while emitting
  output tokens* and says so.

A total over `total_cost_usd` is therefore a total over the turns that priced
themselves, which on a mixed run is a subset. `groom cost` reports how much of itself
is real rather than presenting a partial sum as a complete one.

`duration_ms` is guaranteed on every turn span: when the CLI reports it, that value is
used; when it doesn't, `turn_end` stamps the engine's own wall clock. That keeps latency
coverage total, but the two are not quite the same measurement — the engine's includes
process spawn, the CLI's does not — so it is sound for spotting an outlier and not for
comparing harnesses at the margin.

## `labels()` — the workflow's own dimensions

Spans carry run, state, backend and model automatically. What the driver cannot know is
what the run is *working on* — workhorse is workflow-agnostic by design, so "a story"
and "an epic" are vocabulary it must never learn. A workflow declares those dimensions
itself, by overriding `labels()`:

```python
    def labels(self) -> dict[str, str]:
        return {"work_id": self.story_id}
```

It is re-read **before every transition**, so it sees whatever the instance can already
see — inputs, `self.ctx`, and `self.output(node)` for anything a node recorded. A value
that renders empty is dropped rather than stamped blank, and a `labels()` that raises
costs the labels for that transition and nothing else — never the run. A sub-flow gets
its own class's `labels()`.

For a dimension that depends on the arguments the *next state* was bound with, override
`state_labels(params)` instead — which is how a bounded retry budget becomes a span
dimension. It defaults to `labels()`:

```python
    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        loop = params.get("loop")
        return self.labels() | (
            {"plan_rework": str(loop.plan_rework)} if loop else {}
        )
```

A budget is almost always already a state parameter (state parameters *are* the
checkpoint), so no state has to stash a copy of it for instrumentation to find. The
label then lands on every span opened while it is current, so cost groups by attempt
number without a join. See [AUTHORING.md](AUTHORING.md#reporting-which-attempt-this-is).

For the "what is it doing *now*" dimension there is a flagged log record instead
(`logger.info(msg, extra={"activity": True})`) — the rendered message *is* the activity,
so it is never written twice. Both ride the live gauges below. Keys are **not**
`wf.`-prefixed; a collector reads them raw. The `wf.`-prefixed spelling still appears on
spans already in a store, written by the YAML front-end this replaced, and the gauges
promote both. See the README's "Labels, and saying what the run is doing".

## Watching a run that has not finished

Spans export **when they end**, so the node a run is currently sitting in — the
one that matters when it hangs — is precisely the one no trace can show. The
live signals are therefore metrics, which ship on a periodic timer regardless of
span state:

| Metric | Answers |
|---|---|
| `workhorse.node.active` {node} | 1 while a node visit is open, 0 when it completes — **where** the run is |
| `workhorse.node.elapsed_s` {node} | how long it has been there |
| `workhorse.run.heartbeat` {node} | the process is alive, whatever node type it is in |
| `workhorse.turn.heartbeat` {node} | the agent CLI turn is alive |
| `workhorse.turn.active` {node} | whether an agent turn is open; closing it clears stale idle and elapsed values |
| `workhorse.turn.idle_s` {node} | seconds since the agent last wrote a line — **small = streaming, climbing = wedged** |
| `workhorse.wait.active` {node, wait_kind} | whether an explicit operator/cap/retry/reframe wait is open |
| `workhorse.wait.elapsed_s` {node, wait_kind} | seconds spent in that still-open explicit wait |
| `workhorse.cap_wait.heartbeat` {node} | a spending-cap sleep is alive, not hung |

Together they separate the three states a long-running node can be in, which are
indistinguishable from the trace alone: *streaming* (heartbeat + low idle),
*wedged* (heartbeat + climbing idle), and *dead* (no heartbeat at all). The run
heartbeat comes from a daemon thread, so it keeps proving liveness even while the
main thread is blocked in a long node call or a multi-hour cap sleep — the cases
with no stream to observe.

Each run's root/node spans also carry a `run_dir` resource attribute, so a span
leads straight back to that run's `prompt.md` / `output.json` on disk. Each
agent-turn span additionally carries `session.id` — the backend CLI's session id —
so a node span leads on to that session's full transcript (`opencode export <id>`
and equivalents), the reasoning/tool trace that `prompt.md`/`output.json` omit. The
same map is written durably to `sessions.jsonl` in the run dir (see the README's Run
artifacts section), so it survives even with telemetry off. Each of its lines also
carries the visit key (`generation`, `seq`), the epoch `ts`, the `backend` whose
vocabulary the session id is in, and the `head` the tree was on — so a node visited five
times in a loop yields five addressable rows rather than five rows that only say *this
node, some session*. That same key names the visit's directory under the run's `turns/`,
where its rendered prompt and its output are kept — `<node-id>/` holds only the latest
visit, and the prompt that produced lap 2 is otherwise gone by the time lap 5 is the one
in trouble.

And because the CLI's own session store is on a single host and prunable, the turn's
transcript is copied into the run's `transcripts/` under that same key — from the store
where workhorse can resolve one, from a tee taken at the redaction seam where it cannot,
and always saying in its `.meta.json` which of the two it was.

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKHORSE_CAPTURE_TRANSCRIPTS` | 1 (on) | Keep each agent turn's transcript under the run's `transcripts/`. On by default because what it buys is only available after the fact: a run that has to be told to record is a run that did not record the turn anyone ends up asking about |
| `WORKHORSE_TRANSCRIPT_MAX_BYTES` | 33554432 (32 MiB) | Per-turn ceiling on a capture. A turn runs 0.5–1.1 MB, so this is sized for the pathological one. A capture that hits it is truncated with a final `{"truncated": true, "bytes": N}` line rather than dropped — a transcript that says where it stopped is evidence, one that just ends looks like a turn that died |

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKHORSE_OTEL` | _unset_ | Tri-state override. Unset = auto (probe the endpoint, and stay off in a test process); truthy forces telemetry on without probing; `0`/`false`/`no` forces it off |
| `WORKHORSE_OTEL_PROBE_S` | 0.25 | Seconds the auto-mode probe waits for the collector to accept a connection. Only a remote or firewalled endpoint ever pays it in full, once per run |
| `WORKHORSE_OTEL_HEARTBEAT_S` | 10 | Seconds between liveness ticks (run + agent turn) |
| `WORKHORSE_OTEL_METRIC_EXPORT_S` | = `WORKHORSE_OTEL_HEARTBEAT_S` (10) | Seconds between metric **exports**. Recording a beat is not sending one, and this is the interval that actually bounds a collector's freshness — so it defaults to the heartbeat rather than to the SDK's 60s, which would have meant beating six times per shipment |
| `OTEL_METRIC_EXPORT_INTERVAL` | _unset_ | The SDK's own knob (milliseconds). Still honored, and still overridden by the workhorse-specific one above; set it to widen the interval on a collector you'd rather not talk to every 10s |
