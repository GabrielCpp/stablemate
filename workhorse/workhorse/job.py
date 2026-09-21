"""Run one long command *outside* an agent turn, under a bounded, observed supervisor."""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

TIERS = ("advisory", "best_effort", "premium")

MANIFEST_NAME = "manifest.json"
HANDLE_NAME = "handle.json"
CHILD_NAME = "child.json"
RUNNER_NAME = "runner.json"
HEARTBEAT_NAME = "heartbeat"
WAKE_NAME = "wake"
KILL_REQUEST_NAME = "kill-request"
STDOUT_NAME = "stdout.log"
STDERR_NAME = "stderr.log"

SAMPLE_S = 2.0

HEARTBEAT_STALE_S = 60.0

HANDLE_WAIT_S = 60.0

TERM_GRACE_S = 10.0
KILL_REQUEST_GRACE_S = 30.0

OVERRUN_FIRST_MULTIPLE = 10.0


class JobError(RuntimeError):
    """A job could not be submitted or inspected."""


class ContainmentUnavailable(JobError):
    """This machine cannot meet the manifest's `min_containment`."""


@dataclass(frozen=True)
class Handle:
    """Where the job is, written before it starts."""

    job_dir: str
    pid: int
    pgid: int
    started_at: float
    tier: str
    labels: dict = field(default_factory=dict)


def _handle_of(payload: dict) -> Handle:
    """A `Handle` from a recorded one, ignoring keys a later version added."""
    return Handle(
        job_dir=str(payload.get("job_dir") or ""),
        pid=int(payload.get("pid") or 0),
        pgid=int(payload.get("pgid") or 0),
        started_at=float(payload.get("started_at") or 0.0),
        tier=str(payload.get("tier") or ""),
        labels=dict(payload.get("labels") or {}),
    )


@dataclass(frozen=True)
class JobStatus:
    """What `poll` can tell without a model call."""

    state: str
    alive: bool
    elapsed_s: float
    estimate_s: float
    overrun_multiple: float
    result_ready: bool
    tier: str


@dataclass(frozen=True)
class RunnerResult:
    """What it cost."""

    exit_code: int | None
    peak_rss_mb: float
    wall_s: float
    kill_reason: str
    tier: str
    started_at: float
    finished_at: float




def _cgroup_delegated() -> bool:
    """True when this user's systemd manager has memory and cpu delegated to it."""
    uid = os.getuid()
    candidates = (
        Path(f"/sys/fs/cgroup/user.slice/user-{uid}.slice/user@{uid}.service/cgroup.controllers"),
        Path("/sys/fs/cgroup/cgroup.controllers"),
    )
    for path in candidates:
        try:
            controllers = path.read_text(encoding="utf-8").split()
        except OSError:
            continue
        if "memory" in controllers and "cpu" in controllers:
            return True
    return False


def containment_tier() -> str:
    """The strongest containment this machine can actually deliver."""
    if sys.platform != "linux":
        return "advisory"
    if shutil.which("systemd-run") and _cgroup_delegated():
        return "premium"
    return "best_effort"


def meets(tier: str, floor: str) -> bool:
    """True when `tier` is at least as strong as `floor`."""
    try:
        return TIERS.index(tier) >= TIERS.index(floor)
    except ValueError as exc:
        raise JobError(f"unknown containment tier: {tier!r} / {floor!r}") from exc




def _paths(job_dir: Path | str) -> Path:
    return Path(job_dir)


def _read_json(path: Path) -> dict:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_json(path: Path, payload: dict) -> None:
    """Write atomically."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _touch(path: Path) -> None:
    path.write_text(f"{time.time()}\n", encoding="utf-8")


def _age(path: Path) -> float:
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return float("inf")




def _rss_tree_mb(root_pid: int) -> float:
    """Resident memory of `root_pid` and every descendant, in MB."""
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,rss="],
            capture_output=True, text=True, timeout=10, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return 0.0

    children: dict[int, list[int]] = {}
    rss: dict[int, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        try:
            pid, ppid, kb = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            continue
        rss[pid] = kb
        children.setdefault(ppid, []).append(pid)

    total = 0
    seen: set[int] = set()
    stack = [root_pid]
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        total += rss.get(pid, 0)
        stack.extend(children.get(pid, ()))
    return total / 1024.0


def _pgid_alive(pgid: int) -> bool:
    if pgid <= 0:
        return False
    try:
        os.killpg(pgid, 0)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    return True


def _signal_group(pgid: int, sig: int) -> None:
    if pgid <= 0:
        return
    try:
        os.killpg(pgid, sig)
    except OSError:
        pass


def _reap_group(
    pgid: int,
    grace: float = TERM_GRACE_S,
    *,
    leader: subprocess.Popen[bytes] | None = None,
) -> None:
    """TERM the group, reap its owned leader, then KILL surviving descendants."""
    _signal_group(pgid, signal.SIGTERM)
    deadline = time.time() + grace
    while time.time() < deadline:
        if leader is not None:
            leader.poll()
        if not _pgid_alive(pgid):
            return
        time.sleep(0.5)
    _signal_group(pgid, signal.SIGKILL)




def overrun_multiple(elapsed_s: float, estimate_s: float, first: float) -> float:
    """The largest crossed threshold in `first`, 2x`first`, 4x`first`, … or 0.0."""
    if estimate_s <= 0 or first <= 0 or elapsed_s <= 0:
        return 0.0
    ratio = elapsed_s / estimate_s
    if ratio < first:
        return 0.0
    crossed = first
    while crossed * 2 <= ratio:
        crossed *= 2
    return crossed




_supervisor_procs: dict[str, subprocess.Popen[bytes]] = {}


def _launch_argv(manifest: dict, tier: str) -> list[str]:
    """The argv the supervisor spawns — the command itself, or the command inside a scope."""
    command = [str(part) for part in manifest.get("command") or []]
    if not command:
        raise JobError("manifest has no command")
    if tier != "premium":
        return command

    scope = ["systemd-run", "--user", "--scope", "--quiet", "--collect"]
    memory_mb = manifest.get("memory_mb")
    if memory_mb:
        scope += ["-p", f"MemoryMax={int(memory_mb)}M", "-p", "MemorySwapMax=0"]
    cpus = manifest.get("cpus")
    if cpus:
        scope += ["-p", f"CPUQuota={int(float(cpus) * 100)}%"]
    return [*scope, "--", *command]


def submit(manifest: dict, *, job_dir: Path | str, logger: logging.Logger | None = None) -> Handle:
    """Start `manifest["command"]` detached and return where it is."""
    log = logger or logging.getLogger(__name__)
    directory = _paths(job_dir)
    directory.mkdir(parents=True, exist_ok=True)

    existing = _read_json(directory / HANDLE_NAME)
    if existing and _alive(directory, existing):
        log.info("adopting live job in %s (pid %s)", directory, existing.get("pid"))
        return _handle_of(existing)

    floor = str(manifest.get("min_containment") or "premium")
    tier = containment_tier()
    if not meets(tier, floor):
        raise ContainmentUnavailable(
            f"this machine offers {tier!r} containment; the job requires at least {floor!r}"
        )
    _launch_argv(manifest, tier)

    for stale in (RUNNER_NAME, WAKE_NAME, KILL_REQUEST_NAME, CHILD_NAME, HEARTBEAT_NAME):
        (directory / stale).unlink(missing_ok=True)
    result_name = str(manifest.get("result_file") or "result.json")
    (directory / result_name).unlink(missing_ok=True)

    _write_json(directory / MANIFEST_NAME, {**manifest, "min_containment": floor})

    proc = subprocess.Popen(
        [sys.executable, "-m", "workhorse.job", "supervise", str(directory)],
        cwd=str(directory),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    _supervisor_procs[str(directory)] = proc
    handle = Handle(
        job_dir=str(directory),
        pid=proc.pid,
        pgid=proc.pid,
        started_at=time.time(),
        tier=tier,
        labels=dict(manifest.get("labels") or {}),
    )
    _write_json(directory / HANDLE_NAME, asdict(handle))
    log.info(
        "submitted job in %s under %s containment (supervisor pid %s)",
        directory, tier, proc.pid, extra={"activity": True},
    )
    return handle




def _alive(directory: Path, handle: dict) -> bool:
    """Both facts: the group answers, and the supervisor is still touching its heartbeat."""
    if (directory / RUNNER_NAME).exists():
        return False
    if not _pgid_alive(int(handle.get("pgid") or 0)):
        return False
    heartbeat = directory / HEARTBEAT_NAME
    if not heartbeat.exists():
        return time.time() - float(handle.get("started_at") or 0) < HEARTBEAT_STALE_S
    return _age(heartbeat) < HEARTBEAT_STALE_S


def arm(job_dir: Path | str) -> Path:
    """Clear the wake file, so the supervisor's next event is a fresh edge."""
    directory = _paths(job_dir)
    directory.mkdir(parents=True, exist_ok=True)
    wake = directory / WAKE_NAME
    wake.unlink(missing_ok=True)
    return wake


def poll(job_dir: Path | str) -> JobStatus:
    """Where the job is now — from the filesystem and the clock, with no model call."""
    directory = _paths(job_dir)
    handle = _read_json(directory / HANDLE_NAME)
    manifest = _read_json(directory / MANIFEST_NAME)
    if not handle:
        return JobStatus("missing", False, 0.0, 0.0, 0.0, False, "")

    started_at = float(handle.get("started_at") or 0.0)
    estimate_s = float(manifest.get("estimate_s") or 0.0)
    first = float(manifest.get("overrun_first_multiple") or OVERRUN_FIRST_MULTIPLE)
    runner = _read_json(directory / RUNNER_NAME)
    alive = _alive(directory, handle)

    if runner:
        elapsed = float(runner.get("wall_s") or 0.0)
        state = "finished"
    else:
        elapsed = max(0.0, time.time() - started_at)
        state = "running" if alive else "lost"

    result_name = str(manifest.get("result_file") or "result.json")
    return JobStatus(
        state=state,
        alive=alive,
        elapsed_s=elapsed,
        estimate_s=estimate_s,
        overrun_multiple=overrun_multiple(elapsed, estimate_s, first) if state == "running" else 0.0,
        result_ready=(directory / result_name).exists(),
        tier=str(handle.get("tier") or ""),
    )


def collect(job_dir: Path | str) -> RunnerResult:
    """What the job cost."""
    directory = _paths(job_dir)
    runner = _read_json(directory / RUNNER_NAME)
    handle = _read_json(directory / HANDLE_NAME)
    started_at = float(handle.get("started_at") or 0.0)
    if runner:
        return RunnerResult(
            exit_code=runner.get("exit_code"),
            peak_rss_mb=float(runner.get("peak_rss_mb") or 0.0),
            wall_s=float(runner.get("wall_s") or 0.0),
            kill_reason=str(runner.get("kill_reason") or ""),
            tier=str(runner.get("tier") or handle.get("tier") or ""),
            started_at=float(runner.get("started_at") or started_at),
            finished_at=float(runner.get("finished_at") or 0.0),
        )
    now = time.time()
    return RunnerResult(
        exit_code=None,
        peak_rss_mb=0.0,
        wall_s=max(0.0, now - started_at) if started_at else 0.0,
        kill_reason="lost",
        tier=str(handle.get("tier") or ""),
        started_at=started_at,
        finished_at=now,
    )


def wait_submitted(job_dir: Path | str, timeout: float = 30.0) -> int | None:
    """Reap the supervisor of `job_dir` if one is still alive."""
    directory = str(_paths(job_dir))
    proc = _supervisor_procs.pop(directory, None)
    if proc is None:
        return None
    try:
        if proc.poll() is None:
            try:
                return proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                _signal_group(proc.pid, signal.SIGTERM)
                try:
                    return proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _signal_group(proc.pid, signal.SIGKILL)
                    try:
                        return proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        return None
        return proc.returncode
    finally:
        for stream in (proc.stdout, proc.stderr, proc.stdin):
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass


def kill(job_dir: Path | str, reason: str = "operator") -> RunnerResult:
    """Stop the job and return what it cost up to that point."""
    directory = _paths(job_dir)
    handle = _read_json(directory / HANDLE_NAME)
    if not handle:
        raise JobError(f"no job handle in {directory}")
    if (directory / RUNNER_NAME).exists():
        result = collect(directory)
        wait_submitted(directory)
        return result

    (directory / KILL_REQUEST_NAME).write_text(f"{reason}\n", encoding="utf-8")
    deadline = time.time() + KILL_REQUEST_GRACE_S
    while time.time() < deadline:
        if (directory / RUNNER_NAME).exists():
            result = collect(directory)
            wait_submitted(directory)
            return result
        time.sleep(0.5)

    child = _read_json(directory / CHILD_NAME)
    _reap_group(int(child.get("pgid") or 0))
    _reap_group(int(handle.get("pgid") or 0))
    wait_submitted(directory)
    started_at = float(handle.get("started_at") or 0.0)
    now = time.time()
    result = RunnerResult(
        exit_code=None,
        peak_rss_mb=float(child.get("peak_rss_mb") or 0.0),
        wall_s=max(0.0, now - started_at),
        kill_reason=reason,
        tier=str(handle.get("tier") or ""),
        started_at=started_at,
        finished_at=now,
    )
    _write_json(directory / RUNNER_NAME, asdict(result))
    _touch(directory / WAKE_NAME)
    return result




def supervise(job_dir: Path | str) -> int:
    """The detached half: launch the command, watch it, and write what it cost."""
    directory = _paths(job_dir)
    manifest = _read_json(directory / MANIFEST_NAME)
    heartbeat = directory / HEARTBEAT_NAME
    wake = directory / WAKE_NAME
    _touch(heartbeat)

    deadline = time.time() + HANDLE_WAIT_S
    while not (directory / HANDLE_NAME).exists() and time.time() < deadline:
        time.sleep(0.2)
    handle = _read_json(directory / HANDLE_NAME)
    tier = str(handle.get("tier") or containment_tier())
    started_at = float(handle.get("started_at") or time.time())

    memory_mb = float(manifest.get("memory_mb") or 0.0)
    estimate_s = float(manifest.get("estimate_s") or 0.0)
    first = float(manifest.get("overrun_first_multiple") or OVERRUN_FIRST_MULTIPLE)
    sample_s = float(manifest.get("sample_s") or SAMPLE_S)
    env = {**os.environ, **{str(k): str(v) for k, v in (manifest.get("env") or {}).items()}}
    cwd = str(manifest.get("cwd") or directory)

    peak_rss_mb = 0.0
    kill_reason = ""
    with (directory / STDOUT_NAME).open("wb") as out, (directory / STDERR_NAME).open("wb") as err:
        proc = subprocess.Popen(
            _launch_argv(manifest, tier),
            cwd=cwd, env=env,
            stdin=subprocess.DEVNULL, stdout=out, stderr=err,
            start_new_session=True,
        )
        _write_json(directory / CHILD_NAME, {"pid": proc.pid, "pgid": proc.pid})
        peak_path = _wait_for_scope_cgroup(proc.pid) if tier == "premium" else None

        announced = 0.0
        while proc.poll() is None:
            _touch(heartbeat)
            peak_rss_mb = max(peak_rss_mb, _rss_tree_mb(proc.pid), _read_peak_mb(peak_path))
            _write_json(
                directory / CHILD_NAME,
                {"pid": proc.pid, "pgid": proc.pid, "peak_rss_mb": round(peak_rss_mb, 1)},
            )

            requested = _kill_request(directory)
            if requested:
                kill_reason = requested
            elif memory_mb and tier != "premium" and peak_rss_mb > memory_mb:
                kill_reason = "memory"
            if kill_reason:
                _reap_group(proc.pid, leader=proc)
                break

            crossed = overrun_multiple(time.time() - started_at, estimate_s, first)
            if crossed > announced:
                announced = crossed
                _touch(wake)

            time.sleep(sample_s)

        exit_code = proc.poll()
        if exit_code is None:
            try:
                exit_code = proc.wait(timeout=TERM_GRACE_S)
            except subprocess.TimeoutExpired:
                exit_code = None

    finished_at = time.time()
    _write_json(directory / RUNNER_NAME, asdict(RunnerResult(
        exit_code=exit_code,
        peak_rss_mb=round(peak_rss_mb, 1),
        wall_s=round(max(0.0, finished_at - started_at), 3),
        kill_reason=kill_reason,
        tier=tier,
        started_at=started_at,
        finished_at=finished_at,
    )))
    _touch(heartbeat)
    _touch(wake)
    return 0


def _kill_request(directory: Path) -> str:
    try:
        return (directory / KILL_REQUEST_NAME).read_text(encoding="utf-8").strip() or "operator"
    except OSError:
        return ""


def _current_cgroup(pid: int) -> str:
    """The `pid`'s current cgroup line from `/proc`, or `""` if it cannot be read."""
    try:
        return Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _cgroup_peak_path_for(cgroup_line: str) -> Path | None:
    """Where the kernel keeps `memory.peak` for the cgroup named by `cgroup_line`, if any."""
    relative = cgroup_line.split(":")[-1] if cgroup_line else ""
    peak = Path("/sys/fs/cgroup") / relative.lstrip("/") / "memory.peak"
    return peak if peak.exists() else None


def _cgroup_peak_path(pid: int) -> Path | None:
    """Where the kernel keeps `memory.peak` for the scope `pid` runs in, if it does."""
    return _cgroup_peak_path_for(_current_cgroup(pid))


def _wait_for_scope_cgroup(
    pid: int,
    *,
    is_alive: Callable[[int], bool] = lambda pid: _pgid_alive(pid),
    read_cgroup: Callable[[int], str] = _current_cgroup,
    timeout: float = 5.0,
    poll_s: float = 0.02,
) -> Path | None:
    """Wait for `pid` to be moved into its own `systemd-run --scope`, then return its `memory.peak`."""
    before = read_cgroup(pid)
    deadline = time.time() + timeout
    while time.time() < deadline:
        current = read_cgroup(pid)
        if current and current != before:
            return _cgroup_peak_path_for(current)
        if not is_alive(pid):
            return None
        time.sleep(poll_s)
    return None


def _read_peak_mb(path: Path | None) -> float:
    """The cgroup's own high-water mark in MB, or 0."""
    if path is None:
        return 0.0
    try:
        return int(path.read_text(encoding="utf-8").strip()) / (1024.0 * 1024.0)
    except (OSError, ValueError):
        return 0.0


def main(argv: list[str] | None = None) -> int:
    """`python -m workhorse.job supervise <job_dir>` — the detached half's entry point."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "supervise":
        sys.stderr.write("usage: python -m workhorse.job supervise <job_dir>\n")
        return 2
    return supervise(args[1])


if __name__ == "__main__":
    raise SystemExit(main())
