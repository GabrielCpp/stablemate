---
type: concept
slug: stream-subprocess
title: stream_subprocess — the supervised-spawn path
---
# stream_subprocess — the supervised-spawn path

The one supervised-spawn path every agent harness streams a CLI turn through — Claude via
[`_stream_events`](stream-events.md) and [`_compact_session`](compact-session.md), and
Codex/Copilot/Cline/OpenCode via [`stream_jsonl`](stream-jsonl.md). It owns process-group spawning,
exec retry, line-by-line
streaming, the dual in-loop + out-of-band timeout, heartbeat telemetry, and group-kill cleanup, so
every backend gets identical per-node timeout and orphan-reaping behavior regardless of which CLI
it drives.

It lives in `runner/process.py` — the module holding "spawning an agent CLI and streaming its
output: the process group, the watchdog, and the one stream loop every backend goes through".
`ProcessSupervisor` owns the active-process registry, injected clock, spawn retries, and stream
loop; the module-level functions delegate to its installed singleton. Nothing in it knows any
CLI's event vocabulary; that is each adapter's job.

- code: `workhorse/workhorse/runner/process.py::stream_subprocess`
- code: `workhorse/workhorse/runner/process.py::ProcessSupervisor`
- code: `workhorse/workhorse/runner/process.py::ActiveProcess`
- code: `workhorse/tests/test_config_harness_env.py::test_harness_env_wins_over_the_inherited_shell`
- The implementation is covered by `workhorse/tests/test_stream_subprocess.py::test_clean_stream_completes_without_timeout`,
  `workhorse/tests/test_stream_subprocess.py::test_wedged_midline_is_killed_by_watchdog`, and
  `workhorse/tests/test_stream_subprocess.py::test_group_children_are_reaped`.

A truthy `on_line` result terminates the child process group and reports `timed_out=True`.
Reload is different: a default reload request terminates the group, raises `ReloadRequested`,
and leaves `timed_out=False` so the recovery ladder does not treat it as a failed turn. An
`--at-boundary` request is acknowledged and retained for the state boundary instead of cutting
the stream. The live reload path is covered by
`workhorse/tests/test_stream_subprocess.py::test_a_reload_request_cuts_the_streaming_turn_within_a_slice`
and `workhorse/tests/test_stream_subprocess.py::test_an_at_boundary_request_does_not_touch_the_streaming_turn`.

## Contract

- **Input:**
  - `cmd: list[str]` — the argv to spawn (the harness's CLI invocation).
  - `node_id: str` — exported to the child as `WORKHORSE_NODE_ID`, used in log lines
    (`[{node_id}] ...`) and the watchdog's fire message, and attached to the telemetry events
    below.
  - `timeout: float` — wall-clock budget in seconds for the whole call; `float("inf")` disables
    both the in-loop check and the watchdog (see [Timeout enforcement](#timeout-enforcement)).
  - `on_line` — invoked once per raw line (newline included) read from the merged stdout/stderr
    stream; the caller does its own parsing/accumulation. A truthy callback result requests an
    early abort, while a falsey result continues streaming.
  - `resilience: AgentResilience` (**keyword-only, required**) — the run's tuning knobs. Three are
    read here: `watchdog_grace_s` (the watchdog's headroom past `timeout`), `heartbeat_every_s`
    (the idle-telemetry interval), and the `exec_retry_max`/`exec_retry_base_s`/`exec_retry_cap_s`
    trio [`ProcessSupervisor.spawn`](#processsupervisorspawn) uses.
  - `stdin_data: str | None` (keyword, default `None`) — when set, written to the child's stdin and
    closed immediately (a single-shot prompt, e.g. Claude's `/compact` trigger); when `None`, stdin
    is `subprocess.DEVNULL`.
  - `cwd: str | None` (keyword, default `None`) — subprocess working directory; `None` means the
    launching process's cwd.
  - `env_extra: dict[str, str] | None` (keyword, default `None`) — the backend's
    [`harness_env()`](agent-backend.md#harness_env-concrete) table. It is applied **last**, over
    both `os.environ` and `WORKHORSE_NODE_ID`, so a harness knob configured for a run wins over
    the same variable inherited from the launching shell.
  - `secrets: Iterable[str] | None` (keyword, default `None`) — known secret values redacted from
    every line before the callback, transcript, checkpoint, or telemetry receives it; built-in
    secret-prefix redaction also runs.
- **Output:** `tuple[bool, int]` — `(timed_out, returncode)`. `timed_out` is `True` when the
  in-loop wall-clock check tripped, `on_line` requested an early abort, or the out-of-band
  watchdog fired (see below) — callers treat all three as "the turn didn't finish cleanly" and
  classify accordingly ([`finalize_turn`](finalize-turn.md) /
  [`classify_turn`](classify-turn.md#ladder-first-match-wins) map a watchdog-killed turn to a
  timeout, not a hard crash). `returncode` is the child's exit code (negative when killed by a
  signal).
- **Raises:** `BackendInvocationError` when the CLI cannot be launched at all — see
  [`ProcessSupervisor.spawn`](#processsupervisorspawn).
- consistency: exec-failure — Every exec failure surfaced by the process supervisor is a classified,
   actionable `BackendInvocationError`.
- verify: json_path(path="$.error.type", equals="BackendInvocationError")
- consistency: exec-failure — A missing executable never escapes the process supervisor as a raw
   `FileNotFoundError`.
- verify: json_path(path="$.error.type", equals="BackendInvocationError")
- consistency: exec-failure — Any other launch failure never escapes the process supervisor as a
   raw `OSError`.
- verify: json_path(path="$.error.type", equals="BackendInvocationError")
- consistency: agent-resilience — Every streamed turn receives its required `AgentResilience` from the run, rather
   than using import-time supervision constants.
- verify: count(subject="streamed turns receiving the run's AgentResilience", equals=1)

## Methods

### ActiveProcess
- sig: `ActiveProcess() -> ActiveProcess`
- does: creates an empty registry with no active subprocess
- verify: count(subject="active subprocess handles in a new registry", equals=0)
- verify: created(subject="active-process registry")
- returns: an active-process registry whose handle is protected for access from the streaming and interrupt execution contexts
- code: `workhorse/workhorse/runner/process.py::ActiveProcess`

### set
- sig: `ActiveProcess.set(proc: subprocess.Popen) -> None`
- does: registers the supplied subprocess as the currently streaming process
- verify: created(subject="registered active subprocess handle")
- returns: `None`
- verify: json_path(path="return", matches="^None$")
- code: `workhorse/workhorse/runner/process.py::ActiveProcess.set`

### clear
- sig: `ActiveProcess.clear() -> None`
- does: removes the currently registered subprocess
- verify: removed(subject="registered active subprocess handle")
- returns: `None`
- verify: json_path(path="return", matches="^None$")
- code: `workhorse/workhorse/runner/process.py::ActiveProcess.clear`

### terminate
- sig: `ActiveProcess.terminate() -> None`
- does: returns without signalling when no subprocess is registered
- verify: count(subject="termination signals for an empty active-process registry", equals=0)
- does: returns without signalling when the registered subprocess has already exited
- verify: count(subject="termination signals for an exited active subprocess", equals=0)
- does: sends `SIGTERM` to a live subprocess process group
- verify: emitted(event="active process group termination", count=1)
- does: sends `SIGKILL` after five seconds when graceful termination does not reap the process
- verify: emitted(event="forced active process group termination", count=1)
- returns: `None` after the live subprocess is reaped
- verify: removed(subject="live active subprocess and its process group")
- code: `workhorse/workhorse/runner/process.py::ActiveProcess.terminate`

### ProcessSupervisor.stream
- sig: `ProcessSupervisor.stream(cmd, node_id, timeout, on_line, *, resilience, stdin_data=None, cwd=None, env_extra=None, secrets=None) -> tuple[bool, int]`
- does: spawns the command in a dedicated process group and streams merged output to `on_line`
- verify: count(subject="lines delivered to on_line", equals=2)
- does: cuts the active group on an accepted reload request and raises `ReloadRequested` instead of returning a turn verdict
- verify: emitted(event="reload_kill", count=1)
- does: terminates the group gracefully and then forcefully when the turn times out or the caller requests an early abort
- verify: removed(subject="active process group and descendants")
- raises: `BackendInvocationError` when the command cannot be launched
- returns: `(timed_out, returncode)` after the child has been reaped
- code: `workhorse/workhorse/runner/process.py::ProcessSupervisor.stream`
- tests: `workhorse/tests/test_stream_subprocess.py::test_a_reload_request_cuts_the_streaming_turn_within_a_slice`, `workhorse/tests/test_stream_subprocess.py::test_wedged_midline_is_killed_by_watchdog`, `workhorse/tests/test_stream_subprocess.py::test_the_child_pwd_matches_the_cwd_it_was_spawned_in`

### ProcessSupervisor.spawn
- sig: `ProcessSupervisor.spawn(cmd, node_id, *, resilience, **popen_kwargs) -> subprocess.Popen`
- does: aligns the child working directory environment before launching
- verify: json_path(path="child.environment.PWD", equals="/requested/workdir")
- does: retries executable replacement failures with bounded backoff
- verify: emitted(event="exec_retry", count=1)
- raises: `BackendInvocationError(transient=True)` when a retryable executable remains unavailable but resolves or was previously launched
- verify: json_path(path="$.error.transient", equals=true)
- raises: `BackendInvocationError(transient=False)` when the executable is absent or a non-retryable launch error occurs
- verify: json_path(path="$.error.transient", equals=false)
- returns: the launched subprocess handle and records its executable as successfully launched
- verify: created(subject="launched subprocess handle and successful executable registry entry")
- code: `workhorse/workhorse/runner/process.py::ProcessSupervisor.spawn`
- tests: `workhorse/tests/test_agent_exec_retry.py::test_self_update_etxtbsy_is_retried_then_succeeds`, `workhorse/tests/test_agent_exec_retry.py::test_absent_cli_fails_nontransient_after_bounded_retries`, `workhorse/tests/test_agent_exec_retry.py::test_exhausted_retries_escalate_as_transient`

### install
- sig: `install(supervisor: ProcessSupervisor) -> ProcessSupervisor`
- does: replaces the module-level supervisor used by the streaming and termination delegates
- verify: count(subject="installed supervisors after one install", equals=1)
- returns: the previous supervisor so callers can restore it
- verify: count(subject="supervisors returned by one install", equals=1)
- code: `workhorse/workhorse/runner/process.py::install`
- tests: `workhorse/tests/test_agent_exec_retry.py::test_install_swaps_the_supervisor_and_hands_back_the_old_one`

### stream_subprocess
- sig: `stream_subprocess(cmd, node_id, timeout, on_line, *, resilience, stdin_data=None, cwd=None, env_extra=None, secrets=None) -> tuple[bool, int]`
- does: delegates the complete streaming call to the installed `ProcessSupervisor`
- verify: count(subject="calls to the installed ProcessSupervisor.stream", equals=1)
- raises: `ReloadRequested` when the active stream accepts a reload cut
- verify: json_path(path="exception.type", equals="ReloadRequested")
- returns: the supervisor's `(timed_out, returncode)` result
- verify: json_path(path="return.returncode", equals=17)
- code: `workhorse/workhorse/runner/process.py::stream_subprocess`

### terminate_active
- sig: `terminate_active() -> None`
- does: terminates the currently streaming child process group when one is registered
- verify: removed(subject="currently streaming child process group and descendants")
- returns: `None` without action when no active child exists or it has already exited
- verify: count(subject="termination signals for an absent or exited active child", equals=0)
- code: `workhorse/workhorse/runner/process.py::terminate_active`

## Algorithm

1. **Build the environment.** `env = {**os.environ, "WORKHORSE_NODE_ID": node_id, **(env_extra or
   {})}` — inherited first, node id second, harness table last.
2. **Spawn** via [`ProcessSupervisor.spawn`](#processsupervisorspawn) with stdout piped, stderr redirected into
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
    - Read the armed control channel after each select slice. A request accepted by
      `reload.cut_requested()` is recorded as `reload_kill` with `error=False`, then the loop
      exits for a reload; a deferred or unrelated request is acknowledged without interrupting
      the turn.
    - On a ready fd, `readline()` once; an empty read means EOF → break. A non-empty read stamps
      `last_line_at`.
   - Call `on_line(raw)`; a truthy result sets `timed_out = True` and breaks (early abort).
6. **Reconcile the watchdog race.** After the loop, `timed_out = timed_out or fired.is_set()` — the
   watchdog runs on its own thread and may have fired concurrently with (or instead of) the in-loop
   detection; either signal counts.
7. **Graceful-then-hard kill.** If `timed_out` or a reload was requested and the process hasn't
   exited, `SIGTERM` the group, wait up to 5s, then `SIGKILL` the group if it's still alive.
   Always `proc.wait()` afterward to
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

### `ProcessSupervisor.spawn`

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
- consistency: exec-failure — A retryable exec failure whose command still resolves, or which succeeded earlier
  in this process, raises `BackendInvocationError(..., transient=True)` so the ladder may retry the
  whole turn.
- consistency: exec-failure — Any other terminal exec failure raises `BackendInvocationError(..., transient=False)`.
  When the command does not resolve, the message advises installing the CLI on a stable `PATH` or
  exporting it before launching workhorse, because a non-interactive shell does not load nvm.

## Process-group management

- **`_align_pwd(popen_kwargs)`** — when a child `cwd` is supplied, materializes or updates the
  environment so `PWD` is the resolved child directory and removes inherited `OLDPWD`; without
  this, a CLI that trusts `PWD` can operate on the launcher's repository instead of the target.
- **`_kill_process_group(proc, sig=SIGKILL)`** — signals the whole process group
  (`os.killpg(os.getpgid(proc.pid), sig)`), reaping any grandchildren (MCP servers, headless
  browsers, JVMs) the agent spawned; falls back to signaling just the process if the group is
  already gone (`ProcessLookupError`/`PermissionError`), and never raises if the target already
  exited. Relies on the child having been spawned with `start_new_session=True` so it is a process
  group leader distinct from workhorse's own group.
- **`ActiveProcess`** — the agent subprocess currently being streamed, *and* the lock guarding it,
  as one object rather than two module globals two functions happen to share. `set`/`clear` swap
  the handle under the lock; `terminate` performs the graceful-then-hard kill. The module holds one
  instance inside `_supervisor`, because there is one interrupt handler per process — what is process-wide is
  that *reference*, not the state itself, which is why the class is instantiable rather than a pile
  of module-level state. The lock matters because `terminate_active` may be called from a different
  execution context (a signal-driven `KeyboardInterrupt`) than the streaming loop itself.

### `terminate_active`

Takes no input and returns no output. This module-level function delegates to
`_supervisor.terminate_active()`, which reads the handle under the lock. With no active handle or one whose
process has already exited (`proc.poll() is not None`), it returns immediately. For a live process,
it sends `SIGTERM` to the group, waits up to five seconds, then sends `SIGKILL` if the group remains
alive, following the graceful-then-hard pattern used for an in-`stream_subprocess` timeout kill.
- Called from `pyflow/run.py`'s two abort paths — the `KeyboardInterrupt` handler and the
  `PyflowError` handler that back [`workhorse-<name> run`](../workhorse.md#run) — so an interrupted or
  fatally-failed run doesn't leave its in-flight agent CLI (and its process tree) orphaned when
  workhorse itself exits.

## Telemetry

Three `otel` emissions originate in this module, all through the same module-level facade every
other component uses (`workhorse/workhorse/otel.py`, whose functions delegate to whichever
telemetry adapter is active — a no-op one unless the run configured otherwise):

| Call | Where | Why |
|---|---|---|
| `otel.turn_heartbeat(node_id, idle_s, elapsed_s)` | top of the stream loop | a silent turn still reports; a run that stops heartbeating is distinguishable from one that is merely slow |
| `otel.turn_event("exec_retry", …)` | [`ProcessSupervisor.spawn`](#processsupervisorspawn) | a CLI that keeps self-updating mid-run is visible as a rate, not as folklore |
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
- [`stream_jsonl`](stream-jsonl.md) (`runner/backends/jsonl.py`) — the shared loop the
  Codex/Copilot/Cline/OpenCode adapters stream their own event formats through on this same path,
  so timeout and group-kill behavior is identical across every backend.
- [`AgentResilience`](agent-backend.md#run_turn-abstract) — the struct carrying every knob this
  module reads; threaded from the run's configuration rather than consulted from the environment
  here.
