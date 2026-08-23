"""Run one long command *outside* an agent turn, under a bounded, observed supervisor.

An agent turn is the wrong container for a measurement. Its budget is a budget for
*thinking*, and a command that runs past it is killed and re-entered from scratch with no
memory — so the longer an experiment runs, the less likely it is that anyone ever sees its
result. Worse, the same turn that ran it is the one asked to judge it, so a re-check
re-runs the whole thing.

This module is the other shape: a workflow **submits** a command, gets a handle back, and
the command runs detached, owned by a supervisor process that outlives the node that
started it. A later state **polls** it and **collects** two numbers nobody inside the
command could have written — how it exited, and what it cost.

It is an engine primitive. It is parameterised on a manifest dict and knows no workflow's
schema: the keys below are verbs (a command, a ceiling, an estimate), not nouns from one
workflow's vocabulary. `ostler.qa.stack` is the model — a manifest in, a plain dict out.

## The manifest

| key                       | meaning                                                        |
| ------------------------- | -------------------------------------------------------------- |
| `command` (required)      | argv list. Not a shell string: this is a measurement, not a recipe. |
| `cwd`                     | working directory for the command (default: the job dir)        |
| `env`                     | extra environment, merged over the supervisor's own             |
| `memory_mb`               | resident-memory ceiling. **Hard** where the tier allows it.     |
| `cpus`                    | CPU ceiling in whole cores. Advisory except on `premium`.       |
| `estimate_s`              | what the submitter predicted, from a calibration probe          |
| `overrun_first_multiple`  | first multiple of `estimate_s` that is worth waking someone for (default 10) |
| `min_containment`         | the weakest tier this job may run under (default `premium`)     |
| `result_file`             | the file the command itself writes, relative to the job dir     |
| `sample_s`                | how often the supervisor samples memory and beats (default 2s)  |
| `labels`                  | opaque dict recorded into the handle (a commit sha, a gate id)  |

## Containment is tiered, and the tier is recorded with every result

A number measured under a hard ceiling and a number measured under a polling loop are not
the same number, and a result that does not say which one it is cannot be compared with
the next one. So the tier is chosen, checked against the manifest's floor, and written
into the runner artifact:

* **`premium`** — Linux with a delegated systemd user manager. `MemoryMax` and `CPUQuota`
  are enforced by the kernel: the command cannot exceed them, and an OOM kill is the
  cgroup's, not a sampler's.
* **`best_effort`** — other Linux. No scope unit, so the ceiling is a sampled kill.
* **`advisory`** — macOS and anything else. Sampled kill; the CPU ceiling is a wish.

**Resources are bound; time is not.** A command that runs long is a *bug signal* — it is
information for whoever wrote it, and killing it destroys that information along with the
work. So a job is never killed for being slow. Instead the supervisor touches the wake
file at 10x, 20x, 40x … its estimate, and whoever is watching decides.

`RLIMIT_AS` is deliberately not used. It bounds *address space*, not residency, and every
arena-allocating numerical library reserves far more of it than it ever touches — so it
kills correct programs while letting a slow leak through.

## What is written where, and by whom

One writer per file, because two processes appending to one artifact is a race nobody
reads the loser of.

| file            | writer      | why                                                     |
| --------------- | ----------- | ------------------------------------------------------- |
| `manifest.json` | `submit`    | what was asked for                                       |
| `handle.json`   | `submit`    | pid, pgid, start time — **before the command launches**, so a crash between the two is still findable |
| `child.json`    | supervisor  | the command's own pgid, for a kill that doesn't take the supervisor with it |
| `heartbeat`     | supervisor  | mtime is liveness                                        |
| `wake`          | supervisor  | mtime moves when something happened                      |
| `runner.json`   | supervisor  | exit code, peak RSS, wall time, kill reason, tier        |
| `stdout.log` / `stderr.log` | the command | its own output                               |
| `result_file`   | the command | its own claims                                           |

The split between the last two rows is the point of the whole module. The command writes
what it *found*; the supervisor writes what it *cost*. A command cannot fake the second
one, so a classifier reading both can tell "measured and missed" from "produced no
measurement" without asking a model.

## Liveness is two facts, not one

`kill -0` on the pgid answers "is some process group by that number alive", which after a
reboot and pid reuse is a different question from the one being asked. So a job counts as
alive only when the pgid answers **and** the heartbeat is fresh.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

#: Tiers, weakest first. Index into this list is the ordering `min_containment` compares on.
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

#: How often the supervisor samples memory, touches the heartbeat, and re-reads its mail.
#: Two seconds is fine-grained enough that a memory spike is caught before the OOM killer
#: makes the decision for us, and coarse enough that `ps` is not the job's biggest cost.
SAMPLE_S = 2.0

#: A heartbeat older than this means the supervisor is gone even if the pgid still answers.
#: Generous against a loaded machine: a sampler that is merely late must not be read as dead.
HEARTBEAT_STALE_S = 60.0

#: How long the supervisor waits for `submit` to finish writing `handle.json`. It exists so
#: the handle is on disk before the command starts, never as a real synchronisation point.
HANDLE_WAIT_S = 60.0

#: Grace between SIGTERM and SIGKILL, and between asking the supervisor to kill and doing
#: it ourselves.
TERM_GRACE_S = 10.0
KILL_REQUEST_GRACE_S = 30.0

#: Default first overrun multiple. Doubling from there (10x, 20x, 40x, …) is self-limiting:
#: the wakeups get rarer exactly as fast as the job gets less likely to be worth waiting for.
OVERRUN_FIRST_MULTIPLE = 10.0


class JobError(RuntimeError):
    """A job could not be submitted or inspected. Callers decide what that means."""


class ContainmentUnavailable(JobError):
    """This machine cannot meet the manifest's `min_containment`.

    Deliberately its own class: a workflow routes a weak machine back to whoever picks
    machines, which is a different repair from a command that would not start.
    """


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

    state: str          # "running" | "finished" | "lost" | "missing"
    alive: bool
    elapsed_s: float
    estimate_s: float
    overrun_multiple: float   # 0.0 until the first threshold is crossed
    result_ready: bool
    tier: str


@dataclass(frozen=True)
class RunnerResult:
    """What it cost. Written by the supervisor, never by the command."""

    exit_code: int | None
    peak_rss_mb: float
    wall_s: float
    kill_reason: str      # "" | "memory" | "operator" | "lost"
    tier: str
    started_at: float
    finished_at: float


# --------------------------------------------------------------------------- tiers


def _cgroup_delegated() -> bool:
    """True when this user's systemd manager has memory and cpu delegated to it.

    Reading the delegated controller list is cheaper and more honest than probing with a
    throwaway scope: a `systemd-run` that succeeds proves the binary works, not that the
    controllers a MemoryMax needs are actually present in this user's subtree.
    """
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


# --------------------------------------------------------------------------- paths


def _paths(job_dir: Path | str) -> Path:
    return Path(job_dir)


def _read_json(path: Path) -> dict:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write_json(path: Path, payload: dict) -> None:
    """Write atomically. A reader polling this file must never see half of it."""
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


# --------------------------------------------------------------------------- sampling


def _rss_tree_mb(root_pid: int) -> float:
    """Resident memory of `root_pid` and every descendant, in MB.

    `ps -eo pid=,ppid=,rss=` is identical on Linux and macOS and is already installed
    everywhere this runs, which is why there is no `psutil` dependency here: one sample
    every two seconds does not justify a wheel that has to be present on every machine a
    result might be reproduced on.
    """
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


def _reap_group(pgid: int, grace: float = TERM_GRACE_S) -> None:
    """TERM the group, then KILL what is left. Used for the command, never for ourselves."""
    _signal_group(pgid, signal.SIGTERM)
    deadline = time.time() + grace
    while time.time() < deadline:
        if not _pgid_alive(pgid):
            return
        time.sleep(0.5)
    _signal_group(pgid, signal.SIGKILL)


# --------------------------------------------------------------------------- overrun


def overrun_multiple(elapsed_s: float, estimate_s: float, first: float) -> float:
    """The largest crossed threshold in `first`, 2x`first`, 4x`first`, … or 0.0.

    Derived from the clock and the estimate alone, so `poll` and the supervisor agree
    without either of them keeping a ledger the other has to trust.
    """
    if estimate_s <= 0 or first <= 0 or elapsed_s <= 0:
        return 0.0
    ratio = elapsed_s / estimate_s
    if ratio < first:
        return 0.0
    crossed = first
    while crossed * 2 <= ratio:
        crossed *= 2
    return crossed


# --------------------------------------------------------------------------- submit


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
    """Start `manifest["command"]` detached and return where it is.

    Idempotent in the sense a resume needs: a job directory whose handle is still alive is
    adopted rather than launched a second time. Re-entering the state that submitted a
    four-hour job must not start a fifth hour of it.
    """
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
    _launch_argv(manifest, tier)   # fail here, not in a detached process nobody is reading

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
    handle = Handle(
        job_dir=str(directory),
        pid=proc.pid,
        pgid=proc.pid,          # start_new_session makes the child its own group leader
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


# --------------------------------------------------------------------------- poll


def _alive(directory: Path, handle: dict) -> bool:
    """Both facts: the group answers, and the supervisor is still touching its heartbeat."""
    if (directory / RUNNER_NAME).exists():
        return False
    if not _pgid_alive(int(handle.get("pgid") or 0)):
        return False
    heartbeat = directory / HEARTBEAT_NAME
    if not heartbeat.exists():
        # The supervisor has not reached its first sample yet; the handle's own age is the
        # only clock there is, and it is allowed the same staleness window.
        return time.time() - float(handle.get("started_at") or 0) < HEARTBEAT_STALE_S
    return _age(heartbeat) < HEARTBEAT_STALE_S


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
    """What the job cost.

    A job whose supervisor died without writing anything still gets a result — `kill_reason`
    ``"lost"`` with no exit code. "We do not know" is a classification; silence is not.
    """
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


def kill(job_dir: Path | str, reason: str = "operator") -> RunnerResult:
    """Stop the job and return what it cost up to that point.

    Asks the supervisor first — it is the one writer of `runner.json`, so a kill it
    performs is a kill that leaves a readable artifact. Only when it does not answer do we
    reap the group ourselves and write the artifact in its place.
    """
    directory = _paths(job_dir)
    handle = _read_json(directory / HANDLE_NAME)
    if not handle:
        raise JobError(f"no job handle in {directory}")
    if (directory / RUNNER_NAME).exists():
        return collect(directory)

    (directory / KILL_REQUEST_NAME).write_text(f"{reason}\n", encoding="utf-8")
    deadline = time.time() + KILL_REQUEST_GRACE_S
    while time.time() < deadline:
        if (directory / RUNNER_NAME).exists():
            return collect(directory)
        time.sleep(0.5)

    child = _read_json(directory / CHILD_NAME)
    _reap_group(int(child.get("pgid") or 0))
    _reap_group(int(handle.get("pgid") or 0))
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


# --------------------------------------------------------------------------- supervisor


def supervise(job_dir: Path | str) -> int:
    """The detached half: launch the command, watch it, and write what it cost.

    Runs in its own session (`submit` spawns it with `start_new_session=True`), and gives
    the command a session of its own again, so killing the command is never an instruction
    that also kills the process holding the pen.
    """
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
        # Resolved while the command is alive: `/proc/<pid>/cgroup` is gone the moment it
        # exits, and a `--collect`ed scope takes its counters with it.
        peak_path = _cgroup_peak_path(proc.pid) if tier == "premium" else None

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
                # Only off the premium tier: there, the kernel already holds this ceiling,
                # and a sampler racing it would attribute the cgroup's kill to itself.
                kill_reason = "memory"
            if kill_reason:
                _reap_group(proc.pid)
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


def _cgroup_peak_path(pid: int) -> Path | None:
    """Where the kernel keeps `memory.peak` for the scope `pid` runs in, if it does."""
    try:
        line = Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    relative = line.split(":")[-1] if line else ""
    peak = Path("/sys/fs/cgroup") / relative.lstrip("/") / "memory.peak"
    return peak if peak.exists() else None


def _read_peak_mb(path: Path | None) -> float:
    """The cgroup's own high-water mark in MB, or 0.

    The sampler cannot see a spike between two samples; this counter can. Taking the larger
    of the two is the only reading that is never an under-report.
    """
    if path is None:
        return 0.0
    try:
        return int(path.read_text(encoding="utf-8").strip()) / (1024.0 * 1024.0)
    except (OSError, ValueError):
        return 0.0


def main(argv: list[str] | None = None) -> int:
    """`python -m workhorse.job supervise <job_dir>` — the detached half's entry point.

    Not a console script. Nothing but `submit` should ever run this, and a name on PATH is
    an invitation to run it by hand against a directory no `submit` prepared.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] != "supervise":
        sys.stderr.write("usage: python -m workhorse.job supervise <job_dir>\n")
        return 2
    return supervise(args[1])


if __name__ == "__main__":
    raise SystemExit(main())
