---
type: concept
slug: stream-subprocess
title: stream_subprocess — the supervised-spawn path
---
# stream_subprocess — the supervised-spawn path

The one supervised-spawn path every agent harness streams a CLI turn through — Claude
(`_invoke_claude`, via [run_agent](run-agent.md)'s ladder), Codex/Copilot/OpenCode
(`_stream_jsonl`), and aider (`_run_text_turn`), all in `workhorse/workhorse/runner/backends.py`.
It owns process-group spawning, line-by-line streaming, the dual in-loop + out-of-band timeout,
and group-kill cleanup, so every backend gets identical per-node timeout and orphan-reaping
behavior regardless of which CLI it drives. `main.py`'s top-level `KeyboardInterrupt`/fatal-error
handling calls the sibling [`terminate_active`](#terminate_active) to clean up the in-flight
process on the way out.

- code: `workhorse/workhorse/runner/agent.py::stream_subprocess`
- verify: `workhorse/tests/test_stream_subprocess.py::test_clean_stream_completes_without_timeout`,
  `workhorse/tests/test_stream_subprocess.py::test_wedged_midline_is_killed_by_watchdog`,
  `workhorse/tests/test_stream_subprocess.py::test_group_children_are_reaped`

## Contract

- **Input:**
  - `cmd: list[str]` — the argv to spawn (the harness's CLI invocation).
  - `node_id: str` — exported to the child as `WORKHORSE_NODE_ID` and used only in log lines
    (`[{node_id}] ...`) and the watchdog's fire message.
  - `timeout: float` — wall-clock budget in seconds for the whole call; `float("inf")` disables
    both the in-loop check and the watchdog (see [Timeout enforcement](#timeout-enforcement)).
  - `on_line: Callable[[str], bool | None]` — invoked once per raw line (newline included) read
    from the merged stdout/stderr stream; the caller does its own parsing/accumulation. A
    **truthy** return is an early-abort request (e.g. a spending-cap marker was just seen) and is
    treated identically to a timeout: the loop breaks and the process group is killed.
  - `stdin_data: str | None` (default `None`) — when set, written to the child's stdin and closed
    immediately (a single-shot prompt, e.g. Claude's `/compact` trigger); when `None`, stdin is
    `subprocess.DEVNULL`.
  - `cwd: str | None` (default `None`) — subprocess working directory; `None` means the launching
    process's cwd.
  - `env_extra: dict[str, str] | None` (default `None`) — merged over `os.environ` (and over
    `WORKHORSE_NODE_ID`) for the child's environment.
- **Output:** `tuple[bool, int]` — `(timed_out, returncode)`. `timed_out` is `True` when the
  in-loop wall-clock check tripped, `on_line` requested an early abort, or the out-of-band
  watchdog fired (see below) — callers treat all three as "the turn didn't finish cleanly" and
  classify accordingly (`_finalize_turn`/`_invoke_claude` map a watchdog-killed turn to a timeout,
  not a hard crash). `returncode` is the child's exit code (negative when killed by a signal).
- **Raises:** nothing turn-specific — a `Popen` failure (bad argv, missing executable) propagates
  as its normal `OSError`/`FileNotFoundError`.

## Algorithm

1. **Spawn.** `subprocess.Popen(cmd, ...)` with stdout piped, stderr redirected into stdout
   (`stderr=STDOUT` — a full stderr buffer can't deadlock the read since there's only one pipe to
   drain), `text=True`, `bufsize=1` (line-buffered), and `start_new_session=True` — the child
   becomes the leader of its own process group/session, which is what lets the group be killed as
   a unit later. If `stdin_data` is set, it's written and the stdin pipe is closed immediately.
2. **Register as the active process.** The `Popen` handle is stashed in the module-level
   `_active_proc` (guarded by `_active_proc_lock`) so [`terminate_active`](#terminate_active) can
   reach it from a different thread/signal path; cleared in the `finally` block on the way out.
3. **Arm the watchdog.** [`_arm_watchdog`](#_arm_watchdog) schedules the out-of-band kill timer
   (`None` when `timeout == inf`).
4. **Stream loop.** Until EOF or a stop condition:
   - Recompute `elapsed`; if `elapsed > timeout`, set `timed_out = True` and break (the **in-loop**
     check — the primary, low-latency path for a stream that keeps producing lines).
   - `select.select([stdout], [], [], min(1.0, timeout - elapsed))` — bounds each wait to at most
     1s so the wall-clock check re-runs at least once a second even on a quiet stream; if nothing
     is ready and the process has already exited (`proc.poll() is not None`), break; otherwise loop
     back to re-check elapsed.
   - On a ready fd, `readline()` once; empty read means EOF → break.
   - Call `on_line(raw)`; a truthy result sets `timed_out = True` and breaks (early abort).
5. **Reconcile the watchdog race.** After the loop, `timed_out = timed_out or fired["v"]` — the
   watchdog runs on its own thread and may have fired concurrently with (or instead of) the in-loop
   detection; either signal counts.
6. **Graceful-then-hard kill.** If `timed_out` and the process hasn't exited, `SIGTERM` the group,
   wait up to 5s, then `SIGKILL` the group if it's still alive. Always `proc.wait()` afterward to
   reap and set `proc.returncode`.
7. **Cleanup (`finally`).** Cancel the watchdog timer (no-op if already fired/cancelled), clear
   `_active_proc`, and as a last backstop, if the process is *still* alive at this point, `SIGKILL`
   the group and wait up to 5s (swallowing a `TimeoutExpired` — this is unconditional best-effort,
   not a hard failure).
8. Return `(timed_out, proc.returncode)`.

## Timeout enforcement

Two independent mechanisms enforce `timeout`, layered because either alone has a gap:

- **In-loop wall-clock check** — cheap and precise, but only re-evaluated between
  `select`/`readline` calls; if the child writes a partial line (no trailing newline) and then
  wedges — a stalled API response, a hung MCP server — `readline()` blocks *inside* the call and
  the elapsed check never runs again, hanging the turn indefinitely.
- **`_arm_watchdog`'s out-of-band timer** (see below) — runs on a separate `threading.Timer`
  thread and force-kills the process group after `timeout + _WATCHDOG_GRACE_S` regardless of what
  the reader thread is blocked on. This is the guarantee that no single wedged turn can freeze an
  unattended, week-long run; it is what fixed a prior incident where a QA node hung for ~12h on a
  stalled stream. Verified by `test_wedged_midline_is_killed_by_watchdog`/
  `test_group_children_are_reaped`.

`_WATCHDOG_GRACE_S` (env `AGENT_WATCHDOG_GRACE_S`, default `120`) is the extra time given past
`timeout` before the watchdog fires — headroom so a stream that's merely slow (not wedged) isn't
killed right at the in-loop boundary.

### `_arm_watchdog`

- **Input:** `proc: subprocess.Popen`, `node_id: str`, `timeout: float`, `on_fire: Callable[[], None]
  | None` (default `None`) — invoked just before the kill so the caller can record that the death
  was watchdog-triggered (`stream_subprocess` uses this to set `fired["v"] = True`).
- **Output:** the armed `threading.Timer` (daemon thread, so it can't block interpreter exit), or
  `None` when `timeout == float("inf")` (the node opted out of a deadline via
  [`timeout: infinity`](../workflow-format.md#agent)).
- **Behavior:** starts a `threading.Timer(timeout + _WATCHDOG_GRACE_S, _fire)`. `_fire` is a no-op
  if the process already exited (`proc.poll() is not None`); otherwise it prints a `⏱ watchdog: …
  SIGKILLing process group` diagnostic, invokes `on_fire` (if given), then
  [`_kill_process_group`](#_kill_process_group) with `SIGKILL` directly (no graceful `SIGTERM`
  first — by the time the watchdog fires, the process has already been unresponsive for a full
  grace period).
- The caller (`stream_subprocess`) always cancels this timer in its `finally` block once the turn
  finishes normally, so it never fires spuriously after a clean exit.

## Process-group management

- **`_kill_process_group(proc, sig=SIGKILL)`** — signals the whole process group
  (`os.killpg(os.getpgid(proc.pid), sig)`), reaping any grandchildren (MCP servers, headless
  browsers, JVMs) the agent spawned; falls back to signaling just the process if the group is
  already gone (`ProcessLookupError`/`PermissionError`), and never raises if the target already
  exited. Relies on the child having been spawned with `start_new_session=True` so it is a process
  group leader distinct from workhorse's own group.
- **`_active_proc` / `_active_proc_lock`** — a module-level registry of the one currently-streaming
  subprocess (workhorse runs agent nodes serially, so at most one is ever in flight), guarded by a
  `threading.Lock` since `terminate_active` may be called from a different execution context
  (a signal-driven `KeyboardInterrupt`) than the streaming loop itself.

### `terminate_active`

- **Input:** none. **Output:** none.
- **Behavior:** reads `_active_proc` under the lock; if `None` or already exited
  (`proc.poll() is not None`), returns immediately. Otherwise `SIGTERM`s the group, waits up to 5s,
  and `SIGKILL`s the group if it's still alive after that — the same graceful-then-hard pattern as
  the in-`stream_subprocess` timeout kill.
- Called by `main.py`'s top-level `KeyboardInterrupt`, `OutOfGasError`, and `BackendInvocationError`
  handlers so an interrupted or fatally-failed run doesn't leave its in-flight agent CLI (and its
  process tree) orphaned when workhorse itself exits.

## Related pieces

- [run_agent](run-agent.md) drives `_invoke_claude`, which streams a Claude turn through
  `stream_subprocess` (see run_agent's "Related pieces").
- [`_stream_events`](stream-events.md) — the Claude backend's own per-line callback, called
  directly (not through `_stream_jsonl`) with the argv [`_run_claude_cli`](run-claude-cli.md)
  builds.
- [`_stream_jsonl`](stream-jsonl.md) / [`_run_text_turn`](run-text-turn.md)
  (`workhorse/workhorse/runner/backends.py`) — the Codex/Copilot/OpenCode and aider adapters that
  stream their own event/text formats through this same path, so timeout and group-kill behavior
  is identical across every backend.
