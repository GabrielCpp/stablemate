---
type: concept
slug: stream-subprocess
title: stream_subprocess — the supervised-spawn path
---
# stream_subprocess — the supervised-spawn path

The one supervised-spawn path every agent harness streams a CLI turn through — Claude via
[`_stream_events`](stream-events.md) and [`_compact_session`](compact-session.md),
Codex/Copilot/OpenCode via [`stream_jsonl`](stream-jsonl.md), and aider via
[`_run_text_turn`](run-text-turn.md). It owns process-group spawning, exec retry, line-by-line
streaming, the dual in-loop + out-of-band timeout, heartbeat telemetry, and group-kill cleanup, so
every backend gets identical per-node timeout and orphan-reaping behavior regardless of which CLI
it drives.

It lives in `runner/process.py` — the module holding "spawning an agent CLI and streaming its
output: the process group, the watchdog, and the one stream loop every backend goes through".
Nothing in it knows any CLI's event vocabulary; that is each adapter's job.

- code: `workhorse/workhorse/runner/process.py::stream_subprocess`
- verify: `workhorse/tests/test_stream_subprocess.py::test_clean_stream_completes_without_timeout`,
  `workhorse/tests/test_stream_subprocess.py::test_wedged_midline_is_killed_by_watchdog`,
  `workhorse/tests/test_stream_subprocess.py::test_group_children_are_reaped`

## Contract

- **Input:**
  - `cmd: list[str]` — the argv to spawn (the harness's CLI invocation).
  - `node_id: str` — exported to the child as `WORKHORSE_NODE_ID`, used in log lines
    (`[{node_id}] ...`) and the watchdog's fire message, and attached to the telemetry events
    below.
  - `timeout: float` — wall-clock budget in seconds for the whole call; `float("inf")` disables
    both the in-loop check and the watchdog (see [Timeout enforcement](#timeout-enforcement)).
  - `on_line` — invoked once per raw line (newline included) read from the merged stdout/stderr
    stream; the caller does its own parsing/accumulation. A **truthy** return is an early-abort
    request (e.g. a spending-cap marker was just seen) and is treated identically to a timeout:
    the loop breaks and the process group is killed. The parameter is annotated
    `Callable[[str], None]`, which understates this — the runtime contract is the truthy-return
    one, and [`stream_jsonl`](stream-jsonl.md#early-abort--stop-the-clis-own-retry-loop) depends
    on it.
  - `resilience: AgentResilience` (**keyword-only, required**) — the run's tuning knobs. Three are
    read here: `watchdog_grace_s` (the watchdog's headroom past `timeout`), `heartbeat_every_s`
    (the idle-telemetry interval), and the `exec_retry_max`/`exec_retry_base_s`/`exec_retry_cap_s`
    trio [`_spawn_streaming`](#_spawn_streaming) uses. It carries no default, so a turn can never
    be supervised under import-time constants instead of the run's own configuration.
  - `stdin_data: str | None` (keyword, default `None`) — when set, written to the child's stdin and
    closed immediately (a single-shot prompt, e.g. Claude's `/compact` trigger); when `None`, stdin
    is `subprocess.DEVNULL`.
  - `cwd: str | None` (keyword, default `None`) — subprocess working directory; `None` means the
    launching process's cwd.
  - `env_extra: dict[str, str] | None` (keyword, default `None`) — the backend's
    [`harness_env()`](agent-backend.md#harness_env-concrete) table. It is applied **last**, over
    both `os.environ` and `WORKHORSE_NODE_ID`, so a harness knob configured for a run wins over
    the same variable inherited from the launching shell.
- **Output:** `tuple[bool, int]` — `(timed_out, returncode)`. `timed_out` is `True` when the
  in-loop wall-clock check tripped, `on_line` requested an early abort, or the out-of-band
  watchdog fired (see below) — callers treat all three as "the turn didn't finish cleanly" and
  classify accordingly ([`finalize_turn`](finalize-turn.md) /
  [`classify_turn`](classify-turn.md#ladder-first-match-wins) map a watchdog-killed turn to a
  timeout, not a hard crash). `returncode` is the child's exit code (negative when killed by a
  signal).
- **Raises:** `BackendInvocationError` when the CLI cannot be launched at all — see
  [`_spawn_streaming`](#_spawn_streaming). A raw `OSError`/`FileNotFoundError` never escapes: the
  spawn path converts every exec failure into a classified, actionable error.

## Algorithm

1. **Build the environment.** `env = {**os.environ, "WORKHORSE_NODE_ID": node_id, **(env_extra or
   {})}` — inherited first, node id second, harness table last.
2. **Spawn** via [`_spawn_streaming`](#_spawn_streaming) with stdout piped, stderr redirected into
   stdout (`stderr=STDOUT` — a full stderr buffer can't deadlock the read since there's only one
   pipe to drain), `text=True`, `bufsize=1` (line-buffered), `cwd=cwd or None`, and
   `start_new_session=True` — the child becomes the leader of its own process group/session, which
   is what lets the group be killed as a unit later. If `stdin_data` is set, it's written and the
   stdin pipe is closed immediately.
3. **Register as the active process.** The `Popen` handle is stashed on the module-level
   [`ActiveProcess`](#process-group-management) registry so
   [`terminate_active`](#terminate_active) can reach it from a different thread/signal path;
   cleared in the `finally` block on the way out.
4. **Arm the watchdog.** [`_arm_watchdog`](#_arm_watchdog) schedules the out-of-band kill timer
   (`None` when `timeout == inf`), with `on_fire=fired.set` on a `threading.Event` the loop reads
   afterward.
5. **Stream loop.** Until EOF or a stop condition:
   - Recompute `elapsed`; if `elapsed > timeout`, set `timed_out = True` and break (the **in-loop**
     check — the primary, low-latency path for a stream that keeps producing lines).
   - **Heartbeat.** If `now - last_beat_at >= resilience.heartbeat_every_s`, emit
     [`otel.turn_heartbeat(node_id, idle_s, elapsed_s)`](#telemetry) where `idle_s` is the time
     since the last line arrived. This is emitted at the *top* of the loop body, before the read,
     so it keeps ticking while the stream is **silent** — the wedged case is exactly the one worth
     observing.
   - `select.select([stdout], [], [], min(1.0, timeout - elapsed))` — bounds each wait to at most
     1s so the wall-clock check re-runs at least once a second even on a quiet stream; if nothing
     is ready and the process has already exited (`proc.poll() is not None`), break; otherwise loop
     back to re-check elapsed.
   - On a ready fd, `readline()` once; an empty read means EOF → break. A non-empty read stamps
     `last_line_at`.
   - Call `on_line(raw)`; a truthy result sets `timed_out = True` and breaks (early abort).
6. **Reconcile the watchdog race.** After the loop, `timed_out = timed_out or fired.is_set()` — the
   watchdog runs on its own thread and may have fired concurrently with (or instead of) the in-loop
   detection; either signal counts.
7. **Graceful-then-hard kill.** If `timed_out` and the process hasn't exited, `SIGTERM` the group,
   wait up to 5s, then `SIGKILL` the group if it's still alive. Always `proc.wait()` afterward to
   reap and set `proc.returncode`.
8. **Cleanup (`finally`).** Cancel the watchdog timer (no-op if already fired/cancelled), clear the
   active-process registry, and as a last backstop, if the process is *still* alive at this point,
   `SIGKILL` the group and wait up to 5s (swallowing a `TimeoutExpired` — this is unconditional
   best-effort, not a hard failure).
9. Return `(timed_out, proc.returncode)`.

## Timeout enforcement

Two independent mechanisms enforce `timeout`, layered because either alone has a gap:

- **In-loop wall-clock check** — cheap and precise, but only re-evaluated between
  `select`/`readline` calls; if the child writes a partial line (no trailing newline) and then
  wedges — a stalled API response, a hung MCP server — `readline()` blocks *inside* the call and
  the elapsed check never runs again, hanging the turn indefinitely.
- **`_arm_watchdog`'s out-of-band timer** (see below) — runs on a separate `threading.Timer`
  thread and force-kills the process group after `timeout + resilience.watchdog_grace_s`
  regardless of what the reader thread is blocked on. This is the guarantee that no single wedged
  turn can freeze an unattended, week-long run; it is what fixed a prior incident where a QA node
  hung for ~12h on a stalled stream. Verified by `test_wedged_midline_is_killed_by_watchdog` /
  `test_group_children_are_reaped`.

[`AgentResilience.watchdog_grace_s`](agent-backend.md#run_turn-abstract) (env
`AGENT_WATCHDOG_GRACE_S`, default `120.0`) is the extra time given past `timeout` before the
watchdog fires — headroom so a stream that's merely slow (not wedged) isn't killed right at the
in-loop boundary. It reaches this module only as a field on the `resilience` argument; there is no
module-level constant to read instead, which is what makes a per-run override actually take
effect.

### `_arm_watchdog`

- **Input:** `proc: subprocess.Popen`, `node_id: str`, `timeout: float`, plus keyword-only
  `resilience: AgentResilience` and `on_fire: Callable[[], None] | None` (default `None`) —
  `on_fire` is invoked just before the kill so the caller can record that the death was
  watchdog-triggered (`stream_subprocess` passes `fired.set`).
- **Output:** the armed `threading.Timer` (daemon thread, so it can't block interpreter exit), or
  `None` when `timeout == float("inf")` (the node opted out of a deadline via
  [`timeout: infinity`](../workflow-format.md#timeout)).
- **Behavior:** starts a `threading.Timer(timeout + resilience.watchdog_grace_s, _fire)`. `_fire`
  is a no-op if the process already exited (`proc.poll() is not None`); otherwise it prints a
  `⏱ watchdog: turn exceeded {timeout}s + {grace}s grace — SIGKILLing process group` diagnostic,
  emits [`otel.turn_event("watchdog_kill", error=True, …)`](#telemetry), invokes `on_fire` (if
  given), then calls [`_kill_process_group`](#process-group-management) with `SIGKILL` directly (no
  graceful `SIGTERM` first — by the time the watchdog fires, the process has already been
  unresponsive for a full grace period).
- The caller (`stream_subprocess`) always cancels this timer in its `finally` block once the turn
  finishes normally, so it never fires spuriously after a clean exit.

### `_spawn_streaming`

The `Popen` call, wrapped in a bounded retry loop, and the only place an exec failure is
interpreted.

An agent CLI can be *transiently* un-launchable: a self-updating CLI replaces its own executable,
and for a moment the path either doesn't resolve (`ENOENT`) or resolves to something that can't be
exec'd (`ETXTBSY`, `ENOEXEC`, `ESTALE` — the `_EXEC_BUSY_ERRNOS` set). Failing a node for that
would be a false negative on a run that is otherwise healthy.

- **Retry:** up to `resilience.exec_retry_max` attempts, with the delay growing as
  `min(exec_retry_base_s * 2 ** (attempt - 1), exec_retry_cap_s)`. Each retry prints
  `⏳ agent CLI '{cmd[0]}' unavailable ({code}) — likely self-updating; retry {n}/{max} in {d}s`
  and emits [`otel.turn_event("exec_retry", …)`](#telemetry).
- **Terminal outcome:** the ambiguity in `ENOENT` — "mid-update" versus "not installed" — is
  resolved in **time**, not by a single probe: it is retried like a transient failure, and only
  once the budget is exhausted does `shutil.which(cmd[0])` decide which error to raise.
  - Retryable errno **and** the name still resolves → `BackendInvocationError(..., transient=True)`
    — the ladder may retry the whole turn.
  - Otherwise → `BackendInvocationError(..., transient=False)`. When the name does not resolve, the
    message carries a hint: *a non-interactive shell does not load nvm; install the CLI on a stable
    PATH or export it before launching workhorse* — by far the most common cause of a CLI that
    works in the operator's terminal and not under workhorse.

## Process-group management

- **`_kill_process_group(proc, sig=SIGKILL)`** — signals the whole process group
  (`os.killpg(os.getpgid(proc.pid), sig)`), reaping any grandchildren (MCP servers, headless
  browsers, JVMs) the agent spawned; falls back to signaling just the process if the group is
  already gone (`ProcessLookupError`/`PermissionError`), and never raises if the target already
  exited. Relies on the child having been spawned with `start_new_session=True` so it is a process
  group leader distinct from workhorse's own group.
- **`ActiveProcess`** — the agent subprocess currently being streamed, *and* the lock guarding it,
  as one object rather than two module globals two functions happen to share. `set`/`clear` swap
  the handle under the lock; `terminate` performs the graceful-then-hard kill. The module holds one
  instance, `_active`, because there is one interrupt handler per process — what is process-wide is
  that *reference*, not the state itself, which is why the class is instantiable rather than a pile
  of module-level state. The lock matters because `terminate_active` may be called from a different
  execution context (a signal-driven `KeyboardInterrupt`) than the streaming loop itself.

### `terminate_active`

- **Input:** none. **Output:** none. A module-level function delegating to `_active.terminate()`.
- **Behavior:** reads the handle under the lock; if `None` or already exited
  (`proc.poll() is not None`), returns immediately. Otherwise `SIGTERM`s the group, waits up to 5s,
  and `SIGKILL`s the group if it's still alive after that — the same graceful-then-hard pattern as
  the in-`stream_subprocess` timeout kill.
- Called from `pyflow/run.py`'s two abort paths — the `KeyboardInterrupt` handler and the
  `PyflowError` handler that back [`workhorse run`](../workhorse.md#run) — so an interrupted or
  fatally-failed run doesn't leave its in-flight agent CLI (and its process tree) orphaned when
  workhorse itself exits.

## Telemetry

Three `otel` emissions originate in this module, all through the same module-level facade every
other component uses (`workhorse/workhorse/otel.py`, whose functions delegate to whichever
telemetry adapter is active — a no-op one unless the run configured otherwise):

| Call | Where | Why |
|---|---|---|
| `otel.turn_heartbeat(node_id, idle_s, elapsed_s)` | top of the stream loop | a silent turn still reports; a run that stops heartbeating is distinguishable from one that is merely slow |
| `otel.turn_event("exec_retry", …)` | [`_spawn_streaming`](#_spawn_streaming) | a CLI that keeps self-updating mid-run is visible as a rate, not as folklore |
| `otel.turn_event("watchdog_kill", error=True, …)` | [`_arm_watchdog`](#_arm_watchdog)'s `_fire` | the wedge that the in-loop check structurally cannot see |

`turn_event` is called from the watchdog's daemon thread — it is the one instrumentation call that
must be, and is, thread-safe.

## Related pieces

- [`AgentRunner.run`](run-agent.md) drives [`AgentRunner.turn`](agent-turn.md), which reaches this
  function through whichever [`AgentBackend`](agent-backend.md) the run selected.
- [`_stream_events`](stream-events.md) — the Claude backend's own per-line callback, called
  directly (not through `stream_jsonl`) with the argv [`_run_cli`](run-claude-cli.md) builds.
- [`_compact_session`](compact-session.md) — streams the `/compact` turn through this same path, so
  compaction gets the same watchdog and group-kill guarantees as a normal turn.
- [`stream_jsonl`](stream-jsonl.md) (`runner/backends/jsonl.py`) /
  [`_run_text_turn`](run-text-turn.md) (`runner/backends/aider.py`) — the Codex/Copilot/OpenCode
  and aider adapters that stream their own event/text formats through this same path, so timeout
  and group-kill behavior is identical across every backend.
- [`AgentResilience`](agent-backend.md#run_turn-abstract) — the struct carrying every knob this
  module reads; threaded from the run's configuration rather than consulted from the environment
  here.
