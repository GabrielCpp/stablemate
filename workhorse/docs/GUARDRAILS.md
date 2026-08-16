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
   an okf-builder run misread a self-update as an absent CLI and fail its
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

The attempt counters above are not the elapsed-time boundary. One mutable ledger spans the
entire agent-node visit, including output retries, compaction, and reframes, so nested recovery
cannot renew sleep allowances. Cap, transient retry, reframe, and exec-retry waits each have a
separate cumulative budget. Exceeding one raises without taking the next sleep; the checkpoint
remains resumable and no output is fabricated. A resumed node gets fresh recovery allowances,
while `WORKHORSE_MAX_RUNTIME_S`, when set, still counts from the original run start.

**There is no fourth layer.** When all three are spent the node raises and the run
stops at its checkpoint, for an operator to look at and resume. The ladder never
answers *for* a node: a null `decision` from a review node or a null plan from a dev
node is not a degraded answer but a fabricated one, and every node downstream then
does real work on it while the run reports success. A run that stops is recoverable
by resuming it; a run that continued on invented outputs is not recoverable at all,
because nothing records that the answer was never given. The unattended-run promise
is kept by layer 1 instead — its budget is measured in days, so the outage a run
used to die inside is now slept through.

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
- **Scheduled-reset caps** (spending cap, usage/weekly/**session** limit, quota): waited out until the named reset time, then retried — never reframed

### 4. Prompt Reframing, Then a Clean Stop

- **Reframe**: A node Claude can't answer as-phrased is re-asked from scratch in a fresh session, simplifying each time.
- **Then stop**: After reframing is exhausted the run ends at its checkpoint. Nothing invents the node's answer.

### 5. Enhanced Logging

Each operation logs:
- the path to the rendered `prompt.md` before each agent invocation
- 🚀 When Claude is invoked
- 🔄 When resuming a session / reframing a prompt
- ⚠️ When errors occur with diagnostics
- ⏰ When timeouts are reached
- ✖ When a node exhausts the ladder and the run stops

### 6. Workflow-Level Recovery

The main controller:
- Catches and logs errors with context
- Provides clear resume instructions
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
| `AGENT_MAX_INVOKE_RETRIES` | 60 | Additional attempts for transient agent CLI failures. Sized in days, not minutes: with the backoff below the ladder spans ~27h, so a link down for a working day is slept through rather than died inside |
| `AGENT_MAX_COMPACT_ATTEMPTS` | 2 | `/compact`-and-continue tries on context overflow before reframing (0 disables) |
| `AGENT_MAX_REPHRASE_ATTEMPTS` | 3 | Fresh-session reframings before the run stops. A node may override it for itself with `self.agent(..., retries=N)` — notably `retries=0` for a node whose deliverable is a file its caller can read back partially, where a reframe re-asks at full price for nothing (see [AUTHORING.md](AUTHORING.md#where-an-agent-turn-runs-cwd--add_dirs)) |
| `AGENT_RESULT_TIMEOUT_S` | 3600 | Maximum seconds to wait for a result event. A turn cut at its budget reaches the calling state as `workhorse.pyflow.AgentTimeout` once the ladder is spent, so a state whose deliverable is a file can land the partial draft instead of ending the run |
| `AGENT_INVOKE_BACKOFF_BASE_S` | 15 | Base seconds for exponential backoff |
| `AGENT_INVOKE_BACKOFF_CAP_S` | 1800 | Maximum backoff delay in seconds — the coarsest useful poll for "is the network back" |
| `AGENT_RETRY_WAIT_BUDGET_S` | 97305 (~27h) | Cumulative transient-backoff sleep for one agent-node visit; shared by output retries and reframes |
| `AGENT_CAP_DEFAULT_WAIT_S` | 3600 | Default wait when cap reset time can't be parsed |
| `AGENT_CAP_WAIT_MARGIN_S` | 120 | Extra seconds added after parsed reset time |
| `AGENT_CAP_TICK_S` | 600 | Interval for "still paused" messages during long waits |
| `AGENT_MAX_CAP_WAITS` | 48 | Maximum consecutive cap waits before giving up |
| `AGENT_CAP_WAIT_BUDGET_S` | 691320 (8 days + 120s) | Cumulative cap sleep for one agent-node visit; a reset beyond the remaining allowance stops immediately rather than sleeping partway |
| `AGENT_EXEC_RETRY_MAX` | 5 | Short spawn retries when the agent-CLI binary is momentarily un-exec'able (self-update in flight: `ETXTBSY`/`ENOENT` with the shim still resolving) before escalating to the transient ladder. A permanently-absent CLI (`which` → `None`) is not retried. |
| `AGENT_EXEC_RETRY_BASE_S` | 1 | Base seconds for the exec-retry exponential backoff |
| `AGENT_EXEC_RETRY_CAP_S` | 8 | Upper bound on a single exec-retry delay |
| `AGENT_EXEC_RETRY_WAIT_BUDGET_S` | 23 | Cumulative spawn-time self-update backoff for one agent-node visit |
| `AGENT_CAP_MAX_WAIT_S` | 691200 (8 days) | Upper bound on a single `resetsAt`-derived cap sleep (guards against a bogus far-future epoch) |
| `AGENT_REFRAME_WAIT_BUDGET_S` | 60 | Cumulative pause before fresh-session reframes for one agent-node visit |
| `AGENT_WATCHDOG_GRACE_S` | 120 | Grace beyond `AGENT_RESULT_TIMEOUT_S` after which a separate watchdog thread SIGKILLs the turn's process group. The in-loop timeout can only fire *between* stream reads, so a socket that wedges mid-line would otherwise block forever; this is the always-on backstop. |

### Driver-level guards (workhorse/pyflow)

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKHORSE_LOG_LEVEL` | INFO | Root log level for workhorse and the node functions it calls. |
| `WORKHORSE_AWAIT_POLL_S` | 15 | How often an `Await` re-checks the file it is waiting on. A portable polling loop rather than an inotify watch, so it behaves the same in a container, over NFS, and on a laptop that sleeps. |
| `WORKHORSE_MAX_TRANSITIONS` | 1000 | How many state transitions a run may make before it is declared stuck. The gas tank bounds node *work*; this bounds the state machine itself, so a two-state ping-pong that burns no gas still ends. A workflow class that sets `max_transitions` knows its own shape and overrides this for its runs. A zero or negative setting is read as a typo and falls back to the default — a budget of zero is not "no budget", it is a run that ends before its first transition. |
| `WORKHORSE_ON_FAIL` | unset (disabled) | Shell command run when a run ends **failed** (`--on-fail` overrides it). See "Being told the run died" below. |
| `WORKHORSE_ON_FAIL_PID` | unset (disabled) | PID of a process whose terminal the failure is printed on (`--on-fail-pid` overrides it). |
| `WORKHORSE_MAX_RUNTIME_S` | unset (disabled) | Absolute wall-clock ceiling for the whole run, counted from the run's ORIGINAL start so it survives `--resume`. Checked between states, *after* the checkpoint for the state it is about to run — so the transition that finished last is on disk and the resume picks up from it, rather than replaying an already-run state with the arguments it held on entry. Trips as `RunBudgetExceeded` (exit 1, run dir left resumable). Complements the transition budget: that catches a loop that never progresses, this catches a run that progresses (or crawls) forever. |

### Being told the run died

A run that stops is recoverable; a run that stopped six hours ago and nobody noticed has
still cost six hours. Nothing announces it on its own — `groom status` lists only *live*
runs, so an ended run is simply absent from it, and the evidence that it ended badly
(`workhorse.terminal="fail"`, `error.class` on the root span) is only found by a poller
that already suspected something. Two flags close that gap. Either may be used, or both:

```bash
# Print it on a terminal you already have open. `echo $$` in that shell gives the PID.
workhorse-coder run --on-fail-pid 40213

# Or run something. Anything: a desktop notification, a webhook, a repair run.
workhorse-coder run --on-fail 'notify-send "workhorse: $WORKHORSE_RUN_ID failed"'
```

**`--on-fail-pid` writes to that terminal; it does not type into what is running there.**
The ioctl that pushed characters into another terminal's input queue is refused by any
current kernel (`dev.tty.legacy_tiocsti=0` since Linux 6.2), so a shell or an agent
sitting at that terminal sees the text appear and is *not* prompted by it. That makes it
the right channel for waking a human, or an agent whose loop already reads that pane —
and the wrong one for expecting an answer. Its advantage over spawning a window is that
the terminal is the operator's rather than the run's: it survives over SSH, and it does
not die with a desktop session.

`--on-fail` is spawned detached, in its own session, with its stdio closed and the failure
in its environment:

| Variable | |
|---|---|
| `WORKHORSE_RUN_ID` / `WORKHORSE_RUN_DIR` | which run, and where its checkpoint is |
| `WORKHORSE_WORKFLOW` / `WORKHORSE_REPO` | which workflow, on which working tree |
| `WORKHORSE_NODE` | the state it stopped in |
| `WORKHORSE_ERROR` / `WORKHORSE_ERROR_CLASS` | the message, and `WorkflowFailed` vs `RunBudgetExceeded` vs `BackendInvocationError` |
| `WORKHORSE_RESUME_CMD` | what to type next |

Three things hold regardless of what the command is, because in each case the alternative
is worse than not being notified: it **cannot fail the run** (a broken hook would replace
the workflow's diagnosis with a diagnosis of the hook), it **cannot delay the exit** (the
process is finalizing telemetry), and it **cannot recurse** — `WORKHORSE_ON_FAIL` is
stripped from the child, so a hook that starts another run cannot arm the same hook again.

Both fire on the three endings that mean *a person has to do something*: a workflow that
raised `WorkflowFailed`, a `RunBudgetExceeded` wall-clock stop, and a
`BackendInvocationError` the ladder could not get past. Neither fires under `--dry-run`,
where reaching a fail terminal is a check reporting its result — waking somebody for that
teaches them to ignore the channel.

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

### Telemetry

Whenever a collector is reachable, the recovery ladder above is observable rather than
inferred: the root logger ships to the collector alongside the spans, each retry, reframe,
compaction and watchdog kill lands as a span event, and live gauges separate the three
states a long-running node can be in that a trace alone cannot — *streaming*, *wedged*, and
*dead*. Telemetry turns itself on when something is listening and is a complete no-op when
nothing is.

What is emitted, how it is enabled, why one failure is exactly one ERROR span, how turn
cost is normalized across harnesses, and the live gauges to watch a run that has not
finished are in [TELEMETRY.md](TELEMETRY.md).

## Usage Examples

### Setting Custom Timeouts

For workflows with long-running operations:
```bash
export AGENT_RESULT_TIMEOUT_S=1200  # 20 minutes
workhorse-coder run
```

### Shortening the Wait on a Link You Know Is Gone

The defaults ride out a day-long outage. On a machine you are watching, and would
rather see fail than wait on:

```bash
export AGENT_MAX_INVOKE_RETRIES=4
export AGENT_INVOKE_BACKOFF_CAP_S=60
workhorse-coder run story
```

## Recovery from Failures

When a workflow stops after exhausting the ladder:

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
2. **Monitor long runs**: Watch the run log for ✖ markers — they flag the node the run stopped on
3. **Handle caps gracefully**: The system automatically waits for spending caps to reset
4. **Expect long transient waits**: A backoff at its 30-minute cap is the ladder riding out an outage, not a hang — the ⏸ tick lines and the cap-wait heartbeat prove it
