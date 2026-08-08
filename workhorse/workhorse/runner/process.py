"""Spawning an agent CLI and streaming its output: the process group, the watchdog,
and the one stream loop every backend goes through."""

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

from workhorse import otel
from workhorse.config_run import AgentResilience
from workhorse.runner.clock import SYSTEM_CLOCK, Clock
from workhorse.runner.failure import BackendInvocationError
from workhorse.runner.waits import RecoveryWaitBudget, active_recovery_wait_budget
from workhorse.runner.redact import SecretRedactor


def _align_pwd(popen_kwargs: dict[str, Any]) -> None:
    """Make the child's ``$PWD`` agree with the working directory it is spawned in.

    ``Popen(cwd=…)`` changes the child's working directory but leaves the inherited
    ``PWD`` pointing at the *launcher's* directory — only a shell's ``cd`` maintains
    that variable. A CLI that trusts ``PWD`` over ``getcwd()`` therefore works in the
    wrong repository whenever the two disagree, and OpenCode does exactly that: it
    resolves its project root from ``PWD``, so a node handed ``cwd=<target repo>``
    read and wrote the repo *workhorse itself* was launched from. The benchmark
    harness launches every phase from its own checkout, so every author run there
    decomposed that checkout's backlog no matter which repo it was pointed at.

    Corrected here rather than in the OpenCode adapter because the disagreement is a
    property of ``Popen``, not of one CLI: any agent CLI may read ``PWD``, and every
    one of them is spawned through this method.
    """
    cwd = popen_kwargs.get("cwd")
    if not cwd:
        return
    env = popen_kwargs.get("env")
    if env is None:
        # No explicit env means "inherit", and what would be inherited is exactly the
        # stale PWD this exists to correct — so materialise the environment to fix it.
        env = dict(os.environ)
        popen_kwargs["env"] = env
    env["PWD"] = str(Path(cwd).resolve())
    # OLDPWD describes a `cd` this process never made; leaving the launcher's value
    # would send `cd -` in an agent's shell somewhere arbitrary.
    env.pop("OLDPWD", None)


def _kill_process_group(proc: subprocess.Popen, sig: int = signal.SIGKILL) -> None:
    """Signal the subprocess AND its entire process group, reaping any grandchildren
    (MCP servers, headless browsers, JVMs) the agent spawned.

    The agent is launched with ``start_new_session=True``, so it is the leader of its
    own process group; killing the group is what stops an unattended run from
    accumulating orphaned Playwright/Maestro/Chrome processes when a turn is force-
    terminated. Falls back to signalling just the process if the group is already
    gone, and never raises if the target has already exited.
    """
    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except (ProcessLookupError, PermissionError):
        try:
            proc.send_signal(sig)
        except (ProcessLookupError, ValueError):
            pass


class ActiveProcess:
    """The agent subprocess currently being streamed, and the lock guarding it.

    Registering the live process is what lets the top-level interrupt handler
    terminate it (and its group) cleanly instead of leaving it orphaned. The
    handler runs on a different thread from the stream loop, so the handle and its
    lock are one object rather than two module globals two functions happen to
    share.
    """

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


def _arm_watchdog(
    proc: subprocess.Popen,
    node_id: str,
    timeout: float,
    *,
    resilience: AgentResilience,
    on_fire: "Callable[[], None] | None" = None,
) -> threading.Timer | None:
    """Arm an out-of-band timer that force-kills ``proc``'s process group after
    ``timeout + grace``. Returns the Timer (cancel it once the turn completes) or
    None when the node opts out of a deadline (``timeout: infinity``). ``on_fire`` is
    invoked just before the kill so the reader can record that the turn was watchdog-
    killed (and treat the resulting EOF as a timeout rather than a hard error)."""
    if timeout == float("inf"):
        return None

    def _fire() -> None:
        if proc.poll() is not None:
            return
        print(
            f"[{node_id}] ⏱ watchdog: turn exceeded {int(timeout)}s + "
            f"{int(resilience.watchdog_grace_s)}s grace — SIGKILLing process group",
            flush=True,
        )
        # Runs on the watchdog's daemon thread — otel.turn_event is the one
        # instrumentation call that must be (and is) thread-safe.
        otel.turn_event(
            "watchdog_kill", error=True, node=node_id, timeout_s=int(timeout)
        )
        if on_fire is not None:
            on_fire()
        _kill_process_group(proc, signal.SIGKILL)

    timer = threading.Timer(timeout + resilience.watchdog_grace_s, _fire)
    timer.daemon = True
    timer.start()
    return timer


# The agent CLI can be replaced ON DISK mid-run — see ``AgentResilience.exec_retry_max``
# for why exec of the very same path fails for a sub-second window and why that is NOT a
# missing tool. It is deliberately distinguished from a genuinely absent CLI (a
# non-interactive PATH with no nvm shim, the classic launch-context bug): there ENOENT
# persists and shutil.which() returns None, so we fail FAST rather than burn the retry
# budget on a binary that will never appear.
# errnos that mean "the executable is momentarily un-exec'able", not "absent":
# ETXTBSY = native binary being overwritten; ENOEXEC = binary present but half-written
# (invalid header) mid-update; ESTALE = NFS handle gone stale (flaky home mount). All three
# are the SAME self-update window seen at a different instant — the file is there but not yet
# runnable — so all retry the same way. ENOENT (the rename gap) is handled alongside them in
# the retry test below; it is only *conditional* at terminal classification (see `resolves`).
_EXEC_BUSY_ERRNOS = frozenset({errno.ETXTBSY, errno.ENOEXEC, errno.ESTALE})


@dataclass(frozen=True, slots=True)
class ProcessSupervisor:
    """The agent subprocess a run is currently streaming, and the clock timing it.

    Two fields, and each is a reason this is an object rather than the module-level
    state and free functions it replaces. ``active`` is state with an invariant: the
    live handle and the lock guarding it are written by the stream loop and read by
    the interrupt handler on a *different thread*, so they are one object or they
    are a race. ``clock`` is the seam: the streaming path waits in exactly two
    places — a turn's deadline and the exec-retry backoff — and a test that wants to
    watch a timeout fire should not have to wait out a real one.

    ``resilience`` is not a field, deliberately. It is a parameter of the
    ``AgentBackend`` port, so it arrives with each turn from the ladder that owns it;
    making it state here would mean two copies of one run's settings, and the port
    would still carry the other.
    """

    clock: Clock = SYSTEM_CLOCK
    active: ActiveProcess = field(default_factory=ActiveProcess)

    def terminate_active(self) -> None:
        """Terminate the currently-streaming agent subprocess (and its group), if any.

        Called by the main loop's KeyboardInterrupt handler so the child process tree
        is cleaned up before workhorse exits, rather than being left as an orphan.
        """
        self.active.terminate()

    def spawn(
        self,
        cmd: list[str],
        node_id: str,
        *,
        resilience: AgentResilience,
        **popen_kwargs: Any,
    ) -> subprocess.Popen:
        """``subprocess.Popen(cmd)`` with bounded retry across a self-update exec window.

        A transient exec failure (the CLI binary being rewritten in place by its own
        auto-updater) is retried briefly so a healthy turn is not interrupted; a
        permanently-missing CLI fails fast with an actionable ``BackendInvocationError``.
        Both terminal cases raise ``BackendInvocationError`` (never a bare ``OSError``) so
        they flow through the caller's existing ladder rather than crashing the run: a slow
        update escalates as ``transient=True`` (the outer backoff gives it more time); an
        absent CLI is ``transient=False`` (fail fast, resumable).
        """
        _align_pwd(popen_kwargs)
        wait_budget = active_recovery_wait_budget() or RecoveryWaitBudget.from_resilience(
            resilience
        )
        attempt = 0
        while True:
            try:
                return subprocess.Popen(cmd, **popen_kwargs)
            except OSError as exc:
                # ETXTBSY/ENOEXEC/ESTALE mean the binary is momentarily busy / half-written /
                # stale — present but not runnable this instant. ENOENT is
                # AMBIGUOUS at a single instant: a self-updater's rename makes the binary
                # briefly *absent*, and shutil.which() is exactly as blind as exec() during
                # that window — so one probe cannot tell "mid-update" from "never installed".
                # We therefore resolve ENOENT in TIME, not by probing once: retry it briefly.
                # A self-update reappears within a second or two; a genuinely absent CLI never
                # does, and only then (after the retries) do we fail. Other OSErrors — e.g.
                # EACCES (permission) — are permanent, so they go terminal immediately.
                retryable = exc.errno in _EXEC_BUSY_ERRNOS or exc.errno == errno.ENOENT
                attempt += 1
                if retryable and attempt <= resilience.exec_retry_max:
                    delay = min(
                        resilience.exec_retry_base_s * (2 ** (attempt - 1)),
                        resilience.exec_retry_cap_s,
                    )
                    code = errno.errorcode.get(exc.errno, str(exc.errno))
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
                # Terminal — decide permanent-vs-transient only NOW, after a rewrite window
                # has had time to close. A CLI that resolves but still won't exec means the
                # update outlasted our budget → hand to the outer transient ladder (more
                # time). One that STILL does not resolve is genuinely absent (the classic
                # non-interactive-PATH / missing-nvm launch bug) → fail fast, non-transient.
                resolves = shutil.which(cmd[0]) is not None
                if retryable and resolves:
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
        """Spawn ``cmd`` in its own process group, stream its merged stdout line by line to
        ``on_line``, and enforce ``timeout`` with BOTH an in-loop wall-clock check and an
        out-of-band watchdog that SIGKILLs the whole process group once a turn overruns
        ``timeout + grace`` — even when the reader is blocked mid-readline on a wedged
        stream (a stalled API response or a hung MCP server), which the in-loop check alone
        can never catch.

        Every harness — Claude, Codex, Copilot, OpenCode, Cline — streams through this one
        path, so the per-node timeout, the process-group kill (which reaps orphaned MCP /
        browser / JVM grandchildren), and the active-process registration behave identically
        regardless of backend. ``on_line`` receives each raw line (newline included) and does
        its own parsing/accumulation; its answer is only ever tested for truthiness — a
        truthy one asks for an early abort — which is why it is typed as returning
        ``object``: a callback with nothing to say returns ``None`` and stays in shape.
        Returns ``(timed_out, returncode)``.

        ``env_extra`` layers over the inherited environment — the operator's
        ``[harness.<backend>].env`` table, resolved by the backend that knows its own
        name. It is applied last, so a harness knob configured for a run wins over the
        same variable inherited from the launching shell.

        Every line is passed through a ``SecretRedactor`` before ``on_line`` ever sees
        it, so a leaked key never reaches the transcript, the checkpoint, or telemetry —
        this is the one choke point every backend streams through, and the realistic
        leak is a CLI echoing a key in an error body, not a clever agent. ``secrets`` are
        the caller's known values to redact verbatim, on top of the built-in prefix
        heuristics that run unconditionally; workhorse itself never decides what counts
        as a secret, the same way it never assembles ``env_extra``.
        """
        redactor = SecretRedactor(secrets or ())

        def redacted_on_line(raw: str) -> object:
            return on_line(redactor.redact(raw))

        env = {**os.environ, "WORKHORSE_NODE_ID": node_id, **(env_extra or {})}
        proc = self.spawn(
            cmd,
            node_id,
            resilience=resilience,
            stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge so a full stderr buffer can't deadlock the read
            text=True,
            bufsize=1,
            cwd=cwd or None,
            env=env,
            # Own process group/session so the watchdog can reap the agent AND every MCP
            # server / browser / JVM it spawns, instead of orphaning grandchildren.
            start_new_session=True,
        )
        if stdin_data is not None:
            assert proc.stdin is not None
            proc.stdin.write(stdin_data)
            proc.stdin.close()

        self.active.set(proc)

        fired = threading.Event()
        watchdog = _arm_watchdog(
            proc,
            node_id,
            timeout,
            resilience=resilience,
            on_fire=fired.set,
        )
        timed_out = False
        assert proc.stdout is not None
        try:
            start = self.clock.monotonic()
            last_line_at = start
            last_beat_at = start
            while True:
                now = self.clock.monotonic()
                elapsed = now - start
                if elapsed > timeout:
                    timed_out = True
                    break
                # Liveness telemetry, emitted here at the top so it also ticks while the
                # stream is SILENT — the wedged case, and the only one worth paging on.
                # The turn's own span cannot report this: it does not export until it ends.
                if now - last_beat_at >= resilience.heartbeat_every_s:
                    otel.turn_heartbeat(node_id, now - last_line_at, elapsed)
                    last_beat_at = now
                # Short select slices keep the in-loop wall-clock check live for a cleanly
                # arriving stream; the watchdog is the backstop for a stream that wedges
                # mid-line (where readline() below would otherwise block past the deadline).
                ready, _, _ = select.select([proc.stdout], [], [], min(1.0, timeout - elapsed))
                if not ready:
                    if proc.poll() is not None:
                        break
                    continue
                raw = proc.stdout.readline()
                if not raw:  # EOF
                    break
                last_line_at = self.clock.monotonic()
                if redacted_on_line(raw):  # truthy = caller requests early abort (e.g. cap detected)
                    timed_out = True
                    break
            # A watchdog SIGKILL unblocks readline() with EOF; surface it as a timeout so the
            # caller retries the turn rather than misreading the -SIGKILL exit as a hard fail.
            timed_out = timed_out or fired.is_set()
            if timed_out and proc.poll() is None:
                _kill_process_group(proc, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _kill_process_group(proc, signal.SIGKILL)
            proc.wait()
        finally:
            if watchdog is not None:
                watchdog.cancel()
            self.active.clear()
            # Backstop orphan reap: if the agent is somehow still alive on exit, take its
            # whole group down so no MCP server / browser lingers into the next node.
            if proc.poll() is None:
                _kill_process_group(proc, signal.SIGKILL)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        return timed_out, proc.returncode


#: The process's supervisor. There is one interrupt handler per process, and it must
#: reach the very subprocess the stream loop registered, so what is process-wide is
#: this *reference* — held here and only here. Built from the real clock, because the
#: production answer needs no configuration; a test swaps the whole supervisor through
#: ``install`` rather than assigning over the name.
_supervisor = ProcessSupervisor()


def install(supervisor: ProcessSupervisor) -> ProcessSupervisor:
    """Make ``supervisor`` the one the two functions below delegate to, and return the
    previous one so a caller can put it back.

    The injection point for the streaming path: a test installs a supervisor on a
    ``FakeClock`` and gets the deadline logic without waiting out a real deadline.
    """
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
    """Stream a turn on the installed supervisor — see :meth:`ProcessSupervisor.stream`.

    Kept as a function because it is what the ``AgentBackend`` adapters call, and an
    adapter has no supervisor to be handed one: the port's turn signature is the
    ladder's, and widening it to carry a collaborator every adapter would only pass
    straight through is the parameter-threading this refactor removes elsewhere.
    """
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
    """Terminate the currently-streaming agent subprocess (and its group), if any.

    Called by the main loop's KeyboardInterrupt handler so the child process tree is
    cleaned up before workhorse exits, rather than being left as an orphan.
    """
    _supervisor.terminate_active()
