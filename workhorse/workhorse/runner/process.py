"""Spawning an agent CLI and streaming its output: the process group, the watchdog, and the one stream loop every backend goes through."""

from __future__ import annotations

import errno
import os
import select
import shutil
import signal
import subprocess
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from workhorse import control, otel, reload
from workhorse.config_run import AgentResilience
from workhorse._vendor.stablemate_core.clock import SYSTEM_CLOCK, Clock
from workhorse.runner.failure import BackendInvocationError
from workhorse.runner.waits import RecoveryWaitBudget, active_recovery_wait_budget
from workhorse.runner.redact import SecretRedactor
from workhorse.runner import transcript, worktree_guard


def _align_pwd(popen_kwargs: dict[str, Any]) -> None:
    """Make the child's ``$PWD`` agree with the working directory it is spawned in."""
    cwd = popen_kwargs.get("cwd")
    if not cwd:
        return
    env = popen_kwargs.get("env")
    if env is None:
        env = dict(os.environ)
        popen_kwargs["env"] = env
    env["PWD"] = str(Path(cwd).resolve())
    env.pop("OLDPWD", None)


def _kill_process_group(proc: subprocess.Popen, sig: int = signal.SIGKILL) -> None:
    """Signal the subprocess AND its entire process group, reaping any grandchildren (MCP servers, headless browsers, JVMs) the agent spawned."""
    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except (ProcessLookupError, PermissionError):
        try:
            proc.send_signal(sig)
        except (ProcessLookupError, ValueError):
            pass


class ActiveProcess:
    """The agent subprocess currently being streamed, and the lock guarding it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None

    def set(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._proc = proc

    def clear(self) -> None:
        with self._lock:
            self._proc = None

    def terminate(self) -> None:
        """Terminate the currently-streaming subprocess (and its group), if any."""
        with self._lock:
            proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        _kill_process_group(proc, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc, signal.SIGKILL)
            proc.wait()


_WATCHDOG_TICK_S = 0.25


class _Silence:
    """How long the streamed process has said nothing, on the supervisor's own clock.

    Silence is the signal a hang actually produces. A turn that is working says so
    continuously, however long the work takes, so the stream loop and the watchdog
    both ask this rather than how long the turn has been running.
    """

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._spoke_at = clock.monotonic()

    def spoke(self) -> None:
        """Record that the process just produced a line."""
        self._spoke_at = self._clock.monotonic()

    def elapsed(self, now: float | None = None) -> float:
        """Seconds since the process last produced a line."""
        return (self._clock.monotonic() if now is None else now) - self._spoke_at


class _Watchdog:
    """A running silence watchdog, cancellable by the stream loop that armed it."""

    def __init__(self, stop: threading.Event) -> None:
        self._stop = stop

    def cancel(self) -> None:
        """Stop watching; the thread exits at its next tick."""
        self._stop.set()


def _arm_watchdog(
    proc: subprocess.Popen,
    node_id: str,
    timeout: float,
    *,
    resilience: AgentResilience,
    silence: _Silence,
    on_fire: "Callable[[], None] | None" = None,
) -> _Watchdog | None:
    """Arm an out-of-band watchdog that force-kills ``proc``'s process group once it has gone quiet for ``timeout + grace``.

    The in-loop check cannot see that case on its own: a process that wedges mid-line
    leaves the reader blocked inside ``readline`` with no way back to the top of the
    loop, so nothing in the loop runs again to notice.
    """
    if timeout == float("inf"):
        return None
    limit = timeout + resilience.watchdog_grace_s
    stop = threading.Event()

    def _watch() -> None:
        while not stop.wait(_WATCHDOG_TICK_S):
            if proc.poll() is not None:
                return
            quiet = silence.elapsed()
            if quiet < limit:
                continue
            print(
                f"[{node_id}] ⏱ watchdog: turn said nothing for {int(quiet)}s "
                f"({int(timeout)}s + {int(resilience.watchdog_grace_s)}s grace) — "
                "SIGKILLing process group",
                flush=True,
            )
            otel.turn_event(
                "watchdog_kill", error=True, node=node_id, timeout_s=int(timeout)
            )
            if on_fire is not None:
                on_fire()
            _kill_process_group(proc, signal.SIGKILL)
            return

    threading.Thread(target=_watch, daemon=True).start()
    return _Watchdog(stop)


_EXEC_BUSY_ERRNOS = frozenset({errno.ETXTBSY, errno.ENOEXEC, errno.ESTALE})


@dataclass(frozen=True, slots=True)
class ProcessSupervisor:
    """The agent subprocess a run is currently streaming, and the clock timing it."""

    clock: Clock = SYSTEM_CLOCK
    active: ActiveProcess = field(default_factory=ActiveProcess)
    successful_executables: set[str] = field(default_factory=set, repr=False)

    def terminate_active(self) -> None:
        """Terminate the currently-streaming agent subprocess (and its group), if any."""
        self.active.terminate()

    def spawn(
        self,
        cmd: list[str],
        node_id: str,
        *,
        resilience: AgentResilience,
        **popen_kwargs: Any,
    ) -> subprocess.Popen:
        """``subprocess.Popen(cmd)`` with bounded retry across a self-update exec window."""
        _align_pwd(popen_kwargs)
        wait_budget = active_recovery_wait_budget() or RecoveryWaitBudget.from_resilience(
            resilience
        )
        attempt = 0
        while True:
            try:
                proc = subprocess.Popen(cmd, **popen_kwargs)
                self.successful_executables.add(cmd[0])
                return proc
            except OSError as exc:
                retryable = exc.errno in _EXEC_BUSY_ERRNOS or exc.errno == errno.ENOENT
                attempt += 1
                if retryable and attempt <= resilience.exec_retry_max:
                    delay = min(
                        resilience.exec_retry_base_s * (2 ** (attempt - 1)),
                        resilience.exec_retry_cap_s,
                    )
                    code = errno.errorcode.get(exc.errno or 0, str(exc.errno))
                    print(
                        f"[{node_id}] ⏳ agent CLI '{cmd[0]}' unavailable ({code}) — likely "
                        f"self-updating; retry {attempt}/{resilience.exec_retry_max} "
                        f"in {int(delay)}s",
                        flush=True,
                    )
                    otel.turn_event(
                        "exec_retry", node=node_id, attempt=attempt, code=code, delay_s=int(delay)
                    )
                    wait_budget.consume("exec-retry", delay)
                    with otel.wait("exec-retry", node_id):
                        self.clock.sleep(delay)
                    continue
                resolves = shutil.which(cmd[0]) is not None
                if retryable and (resolves or cmd[0] in self.successful_executables):
                    raise BackendInvocationError(
                        f"agent CLI '{cmd[0]}' still not exec'able after "
                        f"{resilience.exec_retry_max} retries ({exc}); likely a slow self-update",
                        transient=True,
                    ) from exc
                hint = (
                    " — a non-interactive shell does not load nvm; install the CLI on a "
                    "stable PATH or export it before launching workhorse"
                    if not resolves else ""
                )
                raise BackendInvocationError(
                    f"agent CLI '{cmd[0]}' could not be launched: {exc}{hint}.",
                    transient=False,
                ) from exc


    def stream(
        self,
        cmd: list[str],
        node_id: str,
        timeout: float,
        on_line: "Callable[[str], object]",
        *,
        resilience: AgentResilience,
        stdin_data: str | None = None,
        cwd: str | None = None,
        env_extra: dict[str, str] | None = None,
        secrets: Iterable[str] | None = None,
    ) -> tuple[bool, int]:
        """Spawn ``cmd`` in its own process group, stream its merged stdout line by line to ``on_line``, and stop it once it has been SILENT for ``timeout``.

        ``timeout`` bounds how long the turn may say nothing, not how long it may work.
        A turn that streams keeps going however long it takes, because a long turn and a
        hung one look nothing alike from here: the hung one stops talking. Both an
        in-loop check and an out-of-band watchdog enforce it, because a stream wedged
        mid-line (a stalled API response, a hung MCP server) blocks the reader inside
        ``readline`` where the in-loop check can never run again.
        """
        redactor = SecretRedactor(secrets or ())
        tee = transcript.tee_begin(node_id)

        def redacted_on_line(raw: str) -> object:
            line = redactor.redact(raw)
            if tee is not None:
                tee.write(line)
            return on_line(line)

        env = {**os.environ, "WORKHORSE_NODE_ID": node_id, **(env_extra or {})}
        env["PATH"] = worktree_guard.guarded_path(env.get("PATH", ""))
        proc = self.spawn(
            cmd,
            node_id,
            resilience=resilience,
            stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=cwd or None,
            env=env,
            start_new_session=True,
        )
        if stdin_data is not None:
            assert proc.stdin is not None
            proc.stdin.write(stdin_data)
            proc.stdin.close()

        self.active.set(proc)

        fired = threading.Event()
        silence = _Silence(self.clock)
        watchdog = _arm_watchdog(
            proc,
            node_id,
            timeout,
            resilience=resilience,
            silence=silence,
            on_fire=fired.set,
        )
        timed_out = False
        reloading: control.Request | None = None
        assert proc.stdout is not None
        try:
            start = self.clock.monotonic()
            last_beat_at = start
            while True:
                now = self.clock.monotonic()
                elapsed = now - start
                quiet = silence.elapsed(now)
                if quiet > timeout:
                    timed_out = True
                    break
                if now - last_beat_at >= resilience.heartbeat_every_s:
                    otel.turn_heartbeat(node_id, quiet, elapsed)
                    last_beat_at = now
                watched: list[Any] = [proc.stdout]
                control_fd = control.armed().fileno()
                if control_fd is not None:
                    watched.append(control_fd)
                ready, _, _ = select.select(watched, [], [], min(1.0, timeout - quiet))
                requested = reload.cut_requested()
                if requested is not None:
                    print(
                        f"[{node_id}] ⟳ reload requested — cutting this turn and "
                        "re-entering the state on the pushed code",
                        flush=True,
                    )
                    otel.turn_event(
                        "reload_kill", node=node_id, core=requested.core, elapsed_s=int(elapsed)
                    )
                    reloading = requested
                    break
                if proc.stdout not in ready:
                    if proc.poll() is not None:
                        break
                    continue
                raw = proc.stdout.readline()
                if not raw:
                    break
                silence.spoke()
                if redacted_on_line(raw):
                    timed_out = True
                    break
            timed_out = timed_out or fired.is_set()
            if (timed_out or reloading is not None) and proc.poll() is None:
                _kill_process_group(proc, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _kill_process_group(proc, signal.SIGKILL)
            proc.wait()
        finally:
            if tee is not None:
                tee.close()
            if watchdog is not None:
                watchdog.cancel()
            self.active.clear()
            if proc.poll() is None:
                _kill_process_group(proc, signal.SIGKILL)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            if proc.stdout is not None:
                proc.stdout.close()
        if reloading is not None:
            raise reload.ReloadRequested(
                f"reload requested during {node_id}", core=reloading.core, cli=reloading.cli
            )
        return timed_out, proc.returncode


_supervisor = ProcessSupervisor()


def install(supervisor: ProcessSupervisor) -> ProcessSupervisor:
    """Make ``supervisor`` the one the two functions below delegate to, and return the previous one so a caller can put it back."""
    global _supervisor
    previous, _supervisor = _supervisor, supervisor
    return previous


def stream_subprocess(
    cmd: list[str],
    node_id: str,
    timeout: float,
    on_line: "Callable[[str], object]",
    *,
    resilience: AgentResilience,
    stdin_data: str | None = None,
    cwd: str | None = None,
    env_extra: dict[str, str] | None = None,
    secrets: Iterable[str] | None = None,
) -> tuple[bool, int]:
    """Stream a turn on the installed supervisor — see :meth:`ProcessSupervisor.stream`."""
    return _supervisor.stream(
        cmd,
        node_id,
        timeout,
        on_line,
        resilience=resilience,
        stdin_data=stdin_data,
        cwd=cwd,
        env_extra=env_extra,
        secrets=secrets,
    )


def terminate_active() -> None:
    """Terminate the currently-streaming agent subprocess (and its group), if any."""
    _supervisor.terminate_active()
