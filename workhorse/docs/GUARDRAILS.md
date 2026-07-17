# Agent Worker Guardrails and Error Recovery

This document describes the guardrails and error recovery mechanisms implemented in the agent worker to handle failures like missing Claude result events.

## Problem Addressed

The original error:
```
workhorse.runner.agent.BackendInvocationError: No result text from claude for node 'review_implementation'
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
`workhorse/runner/agent.py::run_agent`):

1. **Transient retries** — rate limits, overloads, network blips, timeouts, and
   *empty results* (the `No 'result' event received` case above) are retried with
   exponential backoff. For JSONL backends, a matching provider error event or
   error log (for example OpenCode's `ProviderHeaderTimeoutError`) immediately
   stops the CLI's internal retry loop so Workhorse owns the bounded retry and
   backoff. **Scheduled-reset caps** — spending cap, usage/weekly
   limit, *session limit*, quota — are instead *waited out* until the window
   reopens and then retried; the run pauses rather than reframing or defaulting,
   since re-asking a capped subscription can't help (`_invoke_claude`). The wait
   time prefers the CLI's **structured** `rate_limit_event.resetsAt` epoch (exact,
   timezone-correct, bounded by `AGENT_CAP_MAX_WAIT_S`), falling back to parsing
   the reset time from the message text (e.g. `session limit · resets 11:30am`),
   then a default. A cap is detected from text markers (`_CAP_MARKERS`) or a
   blocked `rate_limit_event` status (`_LIMIT_STATUS_MARKERS`).
2. **Compact & continue** — if a node exhausts the model's **context window**
   (the headless CLI returns instead of auto-compacting — markers like
   `prompt is too long`, `context window`, `conversation is too long`), the
   runner runs `/compact` on the node's session to summarize the conversation so
   far, then retries the *same* prompt on that compacted session. This preserves
   the node's progress, unlike a reframe. Bounded by `AGENT_MAX_COMPACT_ATTEMPTS`
   (`_compact_session`). Verified on Claude Code 2.1.x: `/compact` is honored over
   `--resume -p` and reports `compact_result` ("success"/"failed") via `system`
   status events, with the session id preserved. If compaction fails or still
   overflows, it falls through to the reframe below.
3. **Reframe the prompt** — if invocation or output parsing still fails, the
   prompt is rephrased from scratch in a *fresh session* and the node is retried,
   up to `AGENT_MAX_REPHRASE_ATTEMPTS` times. Each attempt simplifies the ask
   further (`_rephrase_prompt`).
4. **Default to the next node** — when every reframing fails, the node emits the
   fallback outputs **declared by the workflow** (`OutputSpec.default` per output,
   defaulting to `null`) so the controller moves on to `node.next` instead of
   aborting the whole run. The runner is generic and does **not** guess values
   from output names — the safe fallback is workflow-specific, so it is declared
   in `workflow.yaml` (see the README's "Unattended resilience" section). Set
   `AGENT_USE_DEFAULT_OUTPUTS=false` to hard-fail (and resume manually) instead.

## Implemented Solutions

### 1. Enhanced Retry Mechanism

The agent includes sophisticated retry logic with:
- **Transient error detection**: Automatically identifies recoverable errors (rate limits, timeouts, network issues, empty results)
- **Exponential backoff**: Prevents overwhelming the service with rapid retries
- **Spending cap handling**: Waits until the subscription window resets instead of failing

### 2. Timeout Handling

- **Result timeout**: Operations that don't produce a result within `AGENT_RESULT_TIMEOUT_S` (default: 600s) are terminated gracefully
- **Process cleanup**: Hung Claude processes are properly terminated/killed
- **Always transient**: Timeouts are always treated as recoverable errors

### 3. Improved Error Classification

Errors are now classified as:
- **Transient**: Temporary issues that can be resolved by retrying (network, rate limits, timeouts, empty results)
- **Persistent**: Permanent issues that won't resolve with retries (invalid model, syntax errors)
- **Scheduled-reset caps** (spending cap, usage/weekly/**session** limit, quota): waited out until the named reset time, then retried — never reframed or defaulted

### 4. Prompt Reframing & Default Outputs

- **Reframe**: A node Claude can't answer as-phrased is re-asked from scratch in a fresh session, simplifying each time.
- **Default to next**: After reframing is exhausted, the node emits the workflow-declared `OutputSpec.default` for each output (null if unset) so an unattended run advances rather than crashing.

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

The following environment variables control the guardrail behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_MAX_OUTPUT_RETRIES` | 2 | Additional same-session attempts when Claude's response can't be parsed |
| `AGENT_MAX_INVOKE_RETRIES` | 4 | Additional attempts for transient agent CLI failures |
| `AGENT_MAX_COMPACT_ATTEMPTS` | 2 | `/compact`-and-continue tries on context overflow before reframing (0 disables) |
| `AGENT_MAX_REPHRASE_ATTEMPTS` | 3 | Fresh-session reframings before defaulting the node |
| `AGENT_USE_DEFAULT_OUTPUTS` | true | Default a failed node's outputs and advance to `next` instead of crashing |
| `AGENT_RESULT_TIMEOUT_S` | 600 | Maximum seconds to wait for a result event |
| `AGENT_INVOKE_BACKOFF_BASE_S` | 15 | Base seconds for exponential backoff |
| `AGENT_INVOKE_BACKOFF_CAP_S` | 300 | Maximum backoff delay in seconds |
| `AGENT_CAP_DEFAULT_WAIT_S` | 3600 | Default wait when cap reset time can't be parsed |
| `AGENT_CAP_WAIT_MARGIN_S` | 120 | Extra seconds added after parsed reset time |
| `AGENT_CAP_TICK_S` | 600 | Interval for "still paused" messages during long waits |
| `AGENT_MAX_CAP_WAITS` | 48 | Maximum consecutive cap waits before giving up |
| `AGENT_CAP_MAX_WAIT_S` | 691200 (8 days) | Upper bound on a single `resetsAt`-derived cap sleep (guards against a bogus far-future epoch) |

### Engine-level guards (workhorse/main.py)

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKHORSE_SCRIPT_INPROCESS` | 1 | Run `script:` nodes **in the engine's own process** (import the module, call `main(logger)`). Set `0` to spawn them as child processes as before — see the trade-off below. |
| `WORKHORSE_LOG_LEVEL` | INFO | Root log level for workhorse and its in-process script nodes. |
| `WORKHORSE_GAS` | 5000 | Progress-metered loop guard: units burned per node step, refilled on real forward progress (a refuel node's value changing). 0 disables. A cycle that never progresses burns one tank and fails loudly (`OutOfGasError`). |
| `WORKHORSE_MAX_RUNTIME_S` | unset (disabled) | Absolute wall-clock ceiling for the whole run, counted from the run's ORIGINAL start so it survives `--resume`. Checked between nodes; trips as `RunBudgetExceeded` (exit 1, run dir left resumable). Complements the gas tank: gas catches a loop that never progresses, this catches a run that progresses (or crawls) forever. |

### Script nodes run in-process (and what that costs)

A `script:` node is imported and its `main(logger)` called inside the engine's own
process, rather than spawned as `python <script.py> <args>`. The reason is
observability: a child process has no `otel._active`, so its spans were inert, and
its stdout was consumed whole as the node's JSON — meaning a script's diagnostics
were, by construction, unrecoverable after the fact. In-process, a script's log
records ride the engine's own root logger: same handlers, same `run_id`, same
collector, no per-script SDK init.

A script cannot tell the difference — `sys.argv`, the cwd, `os.environ` and
`sys.path[0]` are all set the way CPython sets them for `python script.py`, and
restored afterwards, and `SystemExit` still becomes the node's return code (so
`await_operator`'s exit 2 still means "operator input required").

**The trade-off is real and one-directional: a script now shares the engine's
fate.** A child process could only ever return a bad exit code; an imported one
that calls `os._exit`, segfaults a C extension, or exhausts memory takes the run
down with it — losing the checkpoint write and the telemetry flush that a raised
`ScriptExitError` would have gone through. Note the blast radius is bounded by
what was already true: a failing script node has always ended the run (the
retry → reframe → default ladder covers *agent* nodes only). What is new is
losing the *clean* ending. `WORKHORSE_SCRIPT_INPROCESS=0` restores isolation at
the cost of the logs and telemetry this exists to provide.

Script nodes still have **no timeout and no watchdog** — a wedged script hangs
forever. This is unchanged, not introduced here; the run heartbeat below makes it
*visible* (groom's STUCK rule) but nothing kills it.

### Logs (opt-in OpenTelemetry)

With `WORKHORSE_OTEL=1`, the root logger also ships to the collector's `/v1/logs`,
carrying the same `run_id`/`workflow`/`run_dir` resource as the spans. Console
output is unaffected — the console handler binds the real stderr at setup, so log
records reach the terminal even while a script node's stdout/stderr are redirected
for JSON capture.

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

Note that workhorse's own engine output is still mostly `print()`, so it reaches
the console but not the collector. The records that flow to `/v1/logs` today are
overwhelmingly the **script nodes'** — which is the gap this closed.

### Observability (opt-in OpenTelemetry)

Install the extra and set two env vars to stream spans/metrics to a local
collector (`groom` by default — it pages you on stall/budget/churn; see
`docs/workhorse-otel.md` in the repo root):

```bash
pip install 'workhorse-agent[otel]'
export WORKHORSE_OTEL=1
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:8787   # the default
```

Unset (the default), telemetry is a complete no-op with zero added
dependencies. When enabled, workhorse emits a root span per run, a span per
node visit, a span per agent-CLI turn (with duration + token usage),
retry/reframe/compact/watchdog span events, and the gas gauge.
Exports are best-effort: a down collector never slows or crashes a run
(`events.jsonl` on disk remains the durable record).

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
main thread is blocked in a buffered script node or a multi-hour cap sleep — the
cases with no stream to observe.

Each run's root/node spans also carry a `run_dir` resource attribute, so a span
leads straight back to that run's `prompt.md` / `output.json` on disk. Each
agent-turn span additionally carries `session.id` — the backend CLI's session id —
so a node span leads on to that session's full transcript (`opencode export <id>`
and equivalents), the reasoning/tool trace that `prompt.md`/`output.json` omit. The
same map is written durably to `sessions.jsonl` in the run dir (see the README's Run
artifacts section), so it survives even with telemetry off.

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKHORSE_OTEL_HEARTBEAT_S` | 10 | Seconds between liveness ticks (run + agent turn) |
| `OTEL_METRIC_EXPORT_INTERVAL` | 60000 | SDK knob: ms between metric exports. This — not the heartbeat interval — bounds how fresh a collector's view is; lower it (e.g. `15000`) when actively debugging a stall |

## Usage Examples

### Setting Custom Timeouts

For workflows with long-running operations:
```bash
export AGENT_RESULT_TIMEOUT_S=1200  # 20 minutes
workhorse --workflow ./workflows/epic-coder/workflow.yaml
```

### Aggressive Retries for Unstable Networks

```bash
export AGENT_MAX_INVOKE_RETRIES=10
export AGENT_INVOKE_BACKOFF_BASE_S=30
workhorse --workflow ./workflows/story-coder/workflow.yaml
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
   workhorse --workflow ./workflows/<name>/workflow.yaml --resume-run runs/workflow-name-default
   ```

## Testing

Run the test suite (each file is standalone, no pytest required):
```bash
cd /mnt/data/workspace/stablemate/workhorse
.venv/bin/python tests/test_agent_cap.py
.venv/bin/python tests/test_agent_recovery.py
.venv/bin/python tests/test_guardrails.py
```

## Best Practices

1. **Set appropriate timeouts**: Adjust `AGENT_RESULT_TIMEOUT_S` based on your workflow's complexity
2. **Monitor long runs**: Watch the run log for ⏭ default-to-next markers — they flag nodes Claude couldn't answer
3. **Handle caps gracefully**: The system automatically waits for spending caps to reset
4. **Keep defaulting on for unattended runs**: It is what lets a week-long run survive a single bad node
