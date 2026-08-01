# Agent Worker Guardrails and Error Recovery

This document describes the guardrails and error recovery mechanisms implemented in the agent worker to handle failures like missing Claude result events.

## Problem Addressed

The original error:
```
workhorse.runner.failure.BackendInvocationError: No result text from claude for node 'review_implementation'
```

This occurs when Claude's CLI doesn't return a (non-empty) result event within the expected timeframe, which can happen due to:
- Network interruptions
- Claude service issues
- Long-running operations exceeding timeouts
- Resource constraints
- Claude emitting a `result` event whose text is empty

## Recovery Ladder (always on)

The worker is built to run unattended for days, so resilience is the single,
default behavior — there is no mode flag to enable. Every agent node escalates
through three layers before it can ever crash the run (see
`workhorse/runner/ladder.py::AgentRunner.run`):

0. **Exec-retry (spawn-time, before a turn even starts)** — the agent CLI can be
   replaced on disk *mid-run* by its own auto-updater (Claude Code ships a native
   binary and self-updates by default) or a manual `npm i -g`. While that in-place
   rewrite is in flight, `exec` of the same path fails for a sub-second window —
   `ETXTBSY` (a running native binary being overwritten) or `ENOENT` during the
   updater's rename. That must not interrupt an otherwise-healthy turn, so
   `process.ProcessSupervisor.spawn` retries the spawn a few times with short backoff
   (`AGENT_EXEC_RETRY_*`). The subtle part is telling this apart from a *genuinely
   absent* CLI (the classic launch-context bug: a non-interactive shell never loaded
   the nvm `PATH`). You **cannot** do it by probing once — during an `ENOENT` rename
   window `shutil.which()` is exactly as blind as `exec`, so the file looks missing
   to both. So the ambiguity is resolved **in time, not by a probe**: `ENOENT` is
   retried like `ETXTBSY`, and only *after* the bounded retries is the verdict made —
   if the CLI now resolves but still won't exec, the update outlasted the budget and
   it escalates as a normal transient (the ladder below gives it more time); if it
   *still* does not resolve, it is genuinely absent and fails with an actionable
   non-transient `BackendInvocationError`. (A single-probe check here is what let
   okf-builder's `web-bf3` run misread a self-update as an absent CLI and fail its
   last item.)
1. **Transient retries** — rate limits, overloads, network blips, timeouts, and
   *empty results* (the `No 'result' event received` case above) are retried with
   exponential backoff. For JSONL backends, a matching provider error event or
   error log (for example OpenCode's `ProviderHeaderTimeoutError`) immediately
   stops the CLI's internal retry loop so Workhorse owns the bounded retry and
   backoff. **Scheduled-reset caps** — spending cap, usage/weekly
   limit, *session limit*, quota — are instead *waited out* until the window
   reopens and then retried; the run pauses rather than reframing or defaulting,
   since re-asking a capped subscription can't help
   (`ladder.AgentRunner.turn`). The wait time prefers the CLI's
   **structured** `rate_limit_event.resetsAt` epoch (exact,
   timezone-correct, bounded by `AGENT_CAP_MAX_WAIT_S`), falling back to parsing
   the reset time from the message text (e.g. `session limit · resets 11:30am`),
   then a default. A cap is detected from text markers (`failure._CAP_MARKERS`) or a
   blocked `rate_limit_event` status (`failure._LIMIT_STATUS_MARKERS`).
2. **Compact & continue** — if a node exhausts the model's **context window**
   (the headless CLI returns instead of auto-compacting — markers like
   `prompt is too long`, `context window`, `conversation is too long`), the
   runner runs `/compact` on the node's session to summarize the conversation so
   far, then retries the *same* prompt on that compacted session. This preserves
   the node's progress, unlike a reframe. Bounded by `AGENT_MAX_COMPACT_ATTEMPTS`
   (`backends.claude._compact_session`). Verified on Claude Code 2.1.x: `/compact` is honored
   over `--resume -p` and reports `compact_result` ("success"/"failed") via `system`
   status events, with the session id preserved. If compaction fails or still
   overflows, it falls through to the reframe below.
3. **Reframe the prompt** — if invocation or output parsing still fails, the
   prompt is rephrased from scratch in a *fresh session* and the node is retried,
   up to `AGENT_MAX_REPHRASE_ATTEMPTS` times. Each attempt simplifies the ask
   further (`reframe.rephrase_prompt`).
4. **Default the turn's outputs** — when every reframing fails, the node emits its
   declared output keys as nulls so the state that asked for the turn gets a reply
   object and the run advances instead of aborting. The keys come from the model the
   state declared in `self.agent(..., returns=…)`; the runner is generic and does
   **not** guess values from their names. Set `AGENT_USE_DEFAULT_OUTPUTS=false` to
   hard-fail (and resume manually) instead.

## Implemented Solutions

### 1. Enhanced Retry Mechanism

The agent includes sophisticated retry logic with:
- **Transient error detection**: Automatically identifies recoverable errors (rate limits, timeouts, network issues, empty results)
- **Exponential backoff**: Prevents overwhelming the service with rapid retries
- **Spending cap handling**: Waits until the subscription window resets instead of failing

### 2. Timeout Handling

- **Result timeout**: Operations that don't produce a result within `AGENT_RESULT_TIMEOUT_S` (default: 3600s) are terminated gracefully
- **Process cleanup**: Hung Claude processes are properly terminated/killed
- **Always transient**: Timeouts are always treated as recoverable errors

### 3. Improved Error Classification

Errors are now classified as:
- **Transient**: Temporary issues that can be resolved by retrying (network, rate limits, timeouts, empty results)
- **Persistent**: Permanent issues that won't resolve with retries (invalid model, syntax errors)
- **Scheduled-reset caps** (spending cap, usage/weekly/**session** limit, quota): waited out until the named reset time, then retried — never reframed or defaulted

### 4. Prompt Reframing & Default Outputs

- **Reframe**: A node Claude can't answer as-phrased is re-asked from scratch in a fresh session, simplifying each time.
- **Default the outputs**: After reframing is exhausted, the node emits each declared output key as null so an unattended run advances rather than crashing.

### 5. Enhanced Logging

Each operation logs:
- the path to the rendered `prompt.md` before each agent invocation
- 🚀 When Claude is invoked
- 🔄 When resuming a session / reframing a prompt
- ⚠️ When errors occur with diagnostics
- ⏰ When timeouts are reached
- ⏭ When a node defaults to the next node

### 6. Workflow-Level Recovery

The main controller:
- Catches and logs errors with context
- Provides clear resume instructions (when defaulting is disabled)
- Preserves workflow state for resumption

## Configuration

The following environment variables control the guardrail behavior. They are read by
**workhorse itself**; to set variables read by the *agent CLI* — knobs that exist only
as environment and have no flag — use `[harness.<backend>].env` in the shared config
(see the README's "Per-harness environment"). Those are exported into that harness's
subprocess only, including the `/compact` turn in layer 2, so compaction runs under the
same CLI configuration as the conversation it is compacting.

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_MAX_OUTPUT_RETRIES` | 2 | Additional same-session attempts when Claude's response can't be parsed |
| `AGENT_MAX_INVOKE_RETRIES` | 4 | Additional attempts for transient agent CLI failures |
| `AGENT_MAX_COMPACT_ATTEMPTS` | 2 | `/compact`-and-continue tries on context overflow before reframing (0 disables) |
| `AGENT_MAX_REPHRASE_ATTEMPTS` | 3 | Fresh-session reframings before defaulting the node |
| `AGENT_USE_DEFAULT_OUTPUTS` | true | Default a failed node's outputs and advance to `next` instead of crashing |
| `AGENT_RESULT_TIMEOUT_S` | 3600 | Maximum seconds to wait for a result event |
| `AGENT_INVOKE_BACKOFF_BASE_S` | 15 | Base seconds for exponential backoff |
| `AGENT_INVOKE_BACKOFF_CAP_S` | 300 | Maximum backoff delay in seconds |
| `AGENT_CAP_DEFAULT_WAIT_S` | 3600 | Default wait when cap reset time can't be parsed |
| `AGENT_CAP_WAIT_MARGIN_S` | 120 | Extra seconds added after parsed reset time |
| `AGENT_CAP_TICK_S` | 600 | Interval for "still paused" messages during long waits |
| `AGENT_MAX_CAP_WAITS` | 48 | Maximum consecutive cap waits before giving up |
| `AGENT_EXEC_RETRY_MAX` | 5 | Short spawn retries when the agent-CLI binary is momentarily un-exec'able (self-update in flight: `ETXTBSY`/`ENOENT` with the shim still resolving) before escalating to the transient ladder. A permanently-absent CLI (`which` → `None`) is not retried. |
| `AGENT_EXEC_RETRY_BASE_S` | 1 | Base seconds for the exec-retry exponential backoff |
| `AGENT_EXEC_RETRY_CAP_S` | 8 | Upper bound on a single exec-retry delay |
| `AGENT_CAP_MAX_WAIT_S` | 691200 (8 days) | Upper bound on a single `resetsAt`-derived cap sleep (guards against a bogus far-future epoch) |
| `AGENT_WATCHDOG_GRACE_S` | 120 | Grace beyond `AGENT_RESULT_TIMEOUT_S` after which a separate watchdog thread SIGKILLs the turn's process group. The in-loop timeout can only fire *between* stream reads, so a socket that wedges mid-line would otherwise block forever; this is the always-on backstop. |

### Driver-level guards (workhorse/pyflow)

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKHORSE_FRESH_IMPORT` | 1 | Whether `scriptutil.fresh_import` really purges `sys.modules` and re-imports from disk, so a fix landed mid-run reaches the nodes still ahead of it. Set `0` to return the cached module instead — the re-import builds a *new module object*, which discards every `monkeypatch` a test applied to the old one. Nothing rewrites a package on disk under test, so the behavior it exists for cannot occur there. |
| `WORKHORSE_LOG_LEVEL` | INFO | Root log level for workhorse and the node functions it calls. |
| `WORKHORSE_AWAIT_POLL_S` | 15 | How often an `Await` re-checks the file it is waiting on. A portable polling loop rather than an inotify watch, so it behaves the same in a container, over NFS, and on a laptop that sleeps. |
| `WORKHORSE_MAX_TRANSITIONS` | 1000 | How many state transitions a run may make before it is declared stuck. The gas tank bounds node *work*; this bounds the state machine itself, so a two-state ping-pong that burns no gas still ends. A workflow class that sets `max_transitions` knows its own shape and overrides this for its runs. A zero or negative setting is read as a typo and falls back to the default — a budget of zero is not "no budget", it is a run that ends before its first transition. |
| `WORKHORSE_MAX_RUNTIME_S` | unset (disabled) | Absolute wall-clock ceiling for the whole run, counted from the run's ORIGINAL start so it survives `--resume`. Checked between states, *after* the checkpoint for the state it is about to run — so the transition that finished last is on disk and the resume picks up from it, rather than replaying an already-run state with the arguments it held on entry. Trips as `RunBudgetExceeded` (exit 1, run dir left resumable). Complements the transition budget: that catches a loop that never progresses, this catches a run that progresses (or crawls) forever. |

### Node functions run in the driver's own process (and what that costs)

`self.call(node, ...)` invokes an ordinary Python function inside the driver's own
process. The reason is observability: a child process has no installed telemetry, so its
spans would be inert and its stdout consumed whole as the node's JSON — meaning a
node's diagnostics would be, by construction, unrecoverable after the fact.
In-process, a node's log records ride the driver's own root logger: same handlers,
same `run_id`, same collector, no per-node SDK init.

**The trade-off is real and one-directional: a node shares the driver's fate.** A
node that calls `os._exit`, segfaults a C extension, or exhausts memory takes the run
down with it — losing the checkpoint write and the telemetry flush a raised exception
would have gone through. The blast radius is bounded by what was already true: a
failing node ends the run (the retry → reframe → default ladder covers *agent* turns
only). What is lost is the *clean* ending.

Node calls have **no timeout and no watchdog** — a wedged node hangs forever. The run
heartbeat below makes it *visible* (groom's STUCK rule) but nothing kills it.

#### Long-lived processes must be owned, not backgrounded

The engine owns a node for the duration of that node only. A process a node
**backgrounds** — a dev server, a stack, an emulator left running in the node's
shell so a *later* node can use it — is not owned by anything: the engine tears the
node's process tree down when the node ends, and an agent turn reaps its own
grandchildren between turns. Such a process is killed mid-flight, which has cost
real runs a stack that vanished between "bring it up" and "use it".

A process that must **outlive the node that starts it** has to be started detached
(`start_new_session=True`, its own process group) and owned explicitly — brought up,
health-gated, and later reaped (or deliberately left up) by a step outside any agent
turn. `workhorse.stack` is the parameterised primitive for this: `ensure_stack`
brings a stack up from a manifest (or adopts one already serving) and
`teardown_stack` reaps it or leaves an expensive shared stack running. It knows no
workflow's schema — a workflow hands it a manifest dict — so any workflow that must
own a long-lived stack across nodes uses the same lifecycle. (This is what
okf-builder's walkthrough launcher and the coder QA flow both call; a workflow's own
node function is where the manifest is read.) The manifest keys and the return shape
are in [AUTHORING.md](AUTHORING.md#a-stack-that-outlives-the-turn-workhorsestack).

### Logs (OpenTelemetry)

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

### Observability (automatic when a collector is reachable)

Install the extra and start a local collector (`groom` by default — it pages you
on stall/budget/churn; see `docs/workhorse-otel.md` in the repo root). Nothing
else is required: at run start workhorse probes the OTLP endpoint and, if
something is listening, streams spans/metrics/logs to it.

```bash
pip install 'workhorse-agent[otel]'
groom serve                                                # now runs export
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:8787   # the default
export WORKHORSE_OTEL=0                                    # …unless you opt out
```

Auto-on is deliberate: the runs most worth observing are the unattended
week-long ones, and those are exactly the runs where nobody remembers to export a
variable first. Auto declines in one case beyond an unreachable collector: a
**test process** (`PYTEST_CURRENT_TEST`, `pytest` imported, or an `argv[0]` of
`test_*.py`), whose short repeated runs would otherwise dominate the collector.
`WORKHORSE_OTEL` remains as an override — truthy forces telemetry
on, skips the probe and ignores the test-process guard; falsy forces it off. The probe is one TCP connect with a
`WORKHORSE_OTEL_PROBE_S` timeout, so a machine with no collector pays microseconds
on loopback and stays a complete no-op.

With no collector reachable, telemetry adds zero dependencies and does
nothing. When enabled, workhorse emits a root span per run, a span per
node visit, a span per agent-CLI turn (with duration + token usage + cost),
and retry/reframe/compact/watchdog span events.
Exports are best-effort: a down collector never slows or crashes a run
(`events.jsonl` on disk remains the durable record).

#### Turn cost and tokens, normalized across harnesses

Each backend reports a turn's consumption in its own vocabulary — claude's `result`
event, codex's `turn.completed`, opencode's per-step `step_finish`, aider's plain-text
`Tokens:` line — and until `runner/usage.py` existed only claude's was parsed. That is
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
  attribute — never an exception on the hot path of every streamed event. (copilot's
  shape could not be verified against a live run, which is why.)

`duration_ms` is guaranteed on every turn span: when the CLI reports it, that value is
used; when it doesn't, `turn_end` stamps the engine's own wall clock. Latency is
therefore comparable across harnesses even where tokens are not.

#### `labels()` — the workflow's own dimensions

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

For the "what is it doing *now*" dimension there is a flagged log record instead
(`logger.info(msg, extra={"activity": True})`) — the rendered message *is* the activity,
so it is never written twice. Both ride the live gauges below. Keys are **not**
`wf.`-prefixed; a collector reads them raw. The `wf.`-prefixed spelling still appears on
spans already in a store, written by the YAML front-end this replaced, and the gauges
promote both. See the README's "Labels, and saying what the run is doing".

#### Watching a run that has not finished

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
| `workhorse.turn.idle_s` {node} | seconds since the agent last wrote a line — **small = streaming, climbing = wedged** |
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
artifacts section), so it survives even with telemetry off.

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKHORSE_OTEL` | _unset_ | Tri-state override. Unset = auto (probe the endpoint, and stay off in a test process); truthy forces telemetry on without probing; `0`/`false`/`no` forces it off |
| `WORKHORSE_OTEL_PROBE_S` | 0.25 | Seconds the auto-mode probe waits for the collector to accept a connection. Only a remote or firewalled endpoint ever pays it in full, once per run |
| `WORKHORSE_OTEL_HEARTBEAT_S` | 10 | Seconds between liveness ticks (run + agent turn) |
| `WORKHORSE_OTEL_METRIC_EXPORT_S` | = `WORKHORSE_OTEL_HEARTBEAT_S` (10) | Seconds between metric **exports**. Recording a beat is not sending one, and this is the interval that actually bounds a collector's freshness — so it defaults to the heartbeat rather than to the SDK's 60s, which would have meant beating six times per shipment |
| `OTEL_METRIC_EXPORT_INTERVAL` | _unset_ | The SDK's own knob (milliseconds). Still honored, and still overridden by the workhorse-specific one above; set it to widen the interval on a collector you'd rather not talk to every 10s |

## Usage Examples

### Setting Custom Timeouts

For workflows with long-running operations:
```bash
export AGENT_RESULT_TIMEOUT_S=1200  # 20 minutes
workhorse-coder run
```

### Aggressive Retries for Unstable Networks

```bash
export AGENT_MAX_INVOKE_RETRIES=10
export AGENT_INVOKE_BACKOFF_BASE_S=30
workhorse-coder run story
```

### Hard-Stop Instead of Defaulting

To make a persistently failing node abort the run (so it can be inspected and
resumed) rather than defaulting past it:
```bash
export AGENT_USE_DEFAULT_OUTPUTS=false
```

## Recovery from Failures

When defaulting is disabled and a workflow fails with a transient error:

1. **Check the error message**: The enhanced logging will indicate if it's transient
2. **Resume the workflow**: Use the provided resume command
   ```bash
   workhorse-<name> run --resume-run runs/<name>-default
   ```

## Testing

Run the test suite (each file is standalone, no pytest required):
```bash
cd workhorse
uv run python tests/test_agent_cap.py
uv run python tests/test_agent_recovery.py
uv run python tests/test_guardrails.py
```

## Best Practices

1. **Set appropriate timeouts**: Adjust `AGENT_RESULT_TIMEOUT_S` based on your workflow's complexity
2. **Monitor long runs**: Watch the run log for ⏭ default-to-next markers — they flag nodes Claude couldn't answer
3. **Handle caps gracefully**: The system automatically waits for spending caps to reset
4. **Keep defaulting on for unattended runs**: It is what lets a week-long run survive a single bad node
