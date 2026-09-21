"""Running the experiment outside the agent turn, and classifying what came back."""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from workhorse import job
from workhorse_workflows.research.nodes._blueprint import blueprint
from workhorse_workflows.research.schemas import (
    Collected,
    DryRun,
    EnvelopeCheck,
    Job,
    JobWatch,
)

JOBS_DIR = "jobs"

JOBS_GITIGNORE = "*.log\n"

DRY_RUN_TIMEOUT_S = 900.0

DRY_RUN_POLL_S = 1.0

STDERR_TAIL_CHARS = 4000

RESULT_CORE = ("status", "metrics")

FRAME_RE = re.compile(r'^\s*File "([^"]+)", line \d+', re.MULTILINE)

TOOLING_PACKAGES = ("workhorse", "ostler")




def classify_fault(stderr_text: str, repo_dir: str) -> str:
    """`repo`, `tooling`, or `unknown` — from the stack, not from an opinion."""
    frames = FRAME_RE.findall(stderr_text or "")
    root = str(Path(repo_dir).resolve()) if repo_dir else ""
    for path in reversed(frames):
        parts = Path(path).parts
        if "site-packages" in parts:
            tail = parts[parts.index("site-packages") + 1 :]
            if tail and tail[0].split(".")[0] in TOOLING_PACKAGES:
                return "tooling"
            continue
        if root and str(Path(path).resolve()).startswith(root + "/"):
            return "repo"
    return "unknown"


def _tail(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-STDERR_TAIL_CHARS:]




@blueprint.node
def check_envelope(
    logger: logging.Logger,
    memory_mb: int = 0,
    cpus: int = 0,
    gpu: str = "none",
    disk_gb: int = 0,
    envelope_ram_gb: int = 0,
    envelope_cpus: int = 0,
    envelope_gpu: str = "none",
    envelope_disk_gb: int = 0,
) -> EnvelopeCheck:
    """Does the design fit the machine the program declared it has?"""
    over: list[str] = []
    if envelope_ram_gb and memory_mb > envelope_ram_gb * 1000:
        over.append(f"memory {memory_mb}MB > envelope {envelope_ram_gb}GB")
    if envelope_cpus and cpus > envelope_cpus:
        over.append(f"cpus {cpus} > envelope {envelope_cpus}")
    if envelope_disk_gb and disk_gb > envelope_disk_gb:
        over.append(f"disk {disk_gb}GB > envelope {envelope_disk_gb}GB")
    wanted = (gpu or "none").strip().lower()
    if wanted not in ("", "none") and (envelope_gpu or "none").strip().lower() == "none":
        over.append(f"gpu {gpu!r} but the program declares none")
    if over:
        logger.warning("design does not fit the machine envelope: %s", "; ".join(over))
        return EnvelopeCheck(fits=False, reason="; ".join(over))
    return EnvelopeCheck(fits=True)




def job_dir_for(repo_dir: str, program_dir: str, gate_id: str, suffix: str = "") -> str:
    """`<repo>/<program>/jobs/<gate>` — one directory per gate, inside the repo."""
    name = f"{gate_id or 'gate'}{suffix}"
    return str(Path(repo_dir) / program_dir / JOBS_DIR / name)


def _manifest(
    *,
    command: list[str],
    cwd: str,
    memory_mb: int,
    cpus: int,
    estimate_s: float,
    result_file: str,
    min_containment: str,
    labels: dict[str, str],
) -> dict:
    return {
        "command": list(command),
        "cwd": cwd,
        "memory_mb": memory_mb,
        "cpus": cpus,
        "estimate_s": estimate_s,
        "result_file": result_file or "result.json",
        "min_containment": min_containment or "premium",
        "labels": labels,
    }


def _prepare(job_dir: str) -> Path:
    directory = Path(job_dir)
    directory.mkdir(parents=True, exist_ok=True)
    gitignore = directory.parent / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(JOBS_GITIGNORE, encoding="utf-8")
    return directory


@blueprint.node
def submit_job(
    logger: logging.Logger,
    job_dir: str,
    command: list[str],
    cwd: str,
    memory_mb: int = 0,
    cpus: int = 0,
    estimate_s: float = 0.0,
    result_file: str = "result.json",
    min_containment: str = "premium",
    labels: dict[str, str] | None = None,
    probe_units_timed: int = 0,
) -> Job:
    """Launch the measurement detached, and hand back the handle as a parameter."""
    if not command:
        return Job(job_dir=job_dir, error="the build produced no command", fault_locus="repo")
    if estimate_s > 0 and probe_units_timed <= 0:
        return Job(
            job_dir=job_dir,
            error="the estimate has no calibration probe behind it (units_timed=0)",
            fault_locus="design",
        )
    directory = _prepare(job_dir)
    if job.poll(directory).state != "running":
        for stale in (result_file or "result.json", job.RUNNER_NAME):
            (directory / stale).unlink(missing_ok=True)
        result_path(directory, cwd, result_file).unlink(missing_ok=True)
    manifest = _manifest(
        command=command,
        cwd=cwd,
        memory_mb=memory_mb,
        cpus=cpus,
        estimate_s=estimate_s,
        result_file=result_file,
        min_containment=min_containment,
        labels=labels or {},
    )
    try:
        handle = job.submit(manifest, job_dir=directory, logger=logger)
    except job.ContainmentUnavailable as exc:
        return Job(job_dir=job_dir, error=str(exc), fault_locus="tooling")
    except job.JobError as exc:
        return Job(job_dir=job_dir, error=str(exc), fault_locus="repo")
    logger.info(
        "submitted %s pid=%d tier=%s estimate=%.0fs",
        directory, handle.pid, handle.tier, estimate_s,
        extra={"activity": True},
    )
    return Job(
        submitted=True,
        job_dir=str(directory),
        wake_path=str(directory / job.WAKE_NAME),
        pid=handle.pid,
        pgid=handle.pgid,
        tier=handle.tier,
        started_at=handle.started_at,
        estimate_s=estimate_s,
    )




@blueprint.node
def dry_run(
    logger: logging.Logger,
    job_dir: str,
    command: list[str],
    cwd: str,
    repo_dir: str = "",
    result_file: str = "result.json",
    min_containment: str = "advisory",
    memory_mb: int = 0,
    cpus: int = 0,
) -> DryRun:
    """Rehearse the experiment at `n=1` **through the real runner**."""
    if not command:
        return DryRun(ok=False, reason="the build produced no dry-run command", fault_locus="repo")
    directory = _prepare(job_dir)
    for stale in (result_file or "result.json", job.RUNNER_NAME, job.HANDLE_NAME):
        Path(directory / stale).unlink(missing_ok=True)
    result_path(directory, cwd, result_file).unlink(missing_ok=True)
    manifest = _manifest(
        command=command,
        cwd=cwd,
        memory_mb=memory_mb,
        cpus=cpus,
        estimate_s=0.0,
        result_file=result_file,
        min_containment=min_containment,
        labels={"kind": "dry-run"},
    )
    try:
        job.submit(manifest, job_dir=directory, logger=logger)
    except job.ContainmentUnavailable as exc:
        return DryRun(ok=False, reason=str(exc), fault_locus="tooling")
    except job.JobError as exc:
        return DryRun(ok=False, reason=str(exc), fault_locus="repo")

    deadline = time.time() + DRY_RUN_TIMEOUT_S
    while time.time() < deadline:
        if job.poll(directory).state != "running":
            break
        time.sleep(DRY_RUN_POLL_S)
    else:
        job.kill(directory, reason="operator")
        return DryRun(
            ok=False,
            reason=f"the n=1 rehearsal did not finish within {DRY_RUN_TIMEOUT_S:.0f}s",
            fault_locus="repo",
            stderr_tail=_tail(directory / job.STDERR_NAME),
        )

    verdict = judge_rehearsal(directory, cwd=cwd, result_file=result_file, repo_dir=repo_dir)
    if verdict.ok:
        logger.info("n=1 rehearsal passed through the runner", extra={"activity": True})
    return verdict


def judge_rehearsal(
    job_dir: str | Path, *, cwd: str, result_file: str = "result.json", repo_dir: str = ""
) -> DryRun:
    """Read a finished rehearsal off its two files, with no model call."""
    directory = Path(job_dir)
    runner = job.collect(directory)
    stderr_tail = _tail(directory / job.STDERR_NAME)
    parsed, why = _read_result(result_path(directory, cwd, result_file))
    status = str(parsed.get("status") or "") if parsed is not None else ""
    if runner.exit_code == 0 and parsed is not None and status == "ok":
        return DryRun(ok=True, exit_code=0)
    if runner.exit_code not in (0, None):
        reason, locus = f"exit {runner.exit_code}", classify_fault(stderr_tail, repo_dir)
    elif runner.kill_reason:
        reason, locus = f"killed: {runner.kill_reason}", classify_fault(stderr_tail, repo_dir)
    elif parsed is None:
        reason, locus = why, classify_fault(stderr_tail, repo_dir)
    else:
        reason = f"the rehearsal's {result_file or 'result.json'} reports status {status!r}, not 'ok'"
        locus = "repo"
    return DryRun(
        ok=False,
        exit_code=runner.exit_code,
        fault_locus=locus,
        stderr_tail=stderr_tail,
        reason=reason,
    )




@blueprint.node
def watch_job(logger: logging.Logger, job_dir: str, seen_multiple: float = 0.0) -> JobWatch:
    """Arm the wake file, then read authoritative state — in that order."""
    wake = job.arm(job_dir)
    status = job.poll(job_dir)
    if status.state in ("finished", "lost", "missing"):
        return JobWatch(
            action="collect",
            wake_path=str(wake),
            state=status.state,
            elapsed_s=status.elapsed_s,
            estimate_s=status.estimate_s,
        )
    if status.overrun_multiple > seen_multiple:
        logger.warning(
            "job %s is %.0f× its estimate (%.0fs elapsed vs %.0fs)",
            job_dir, status.overrun_multiple, status.elapsed_s, status.estimate_s,
            extra={"activity": True},
        )
        return JobWatch(
            action="triage",
            wake_path=str(wake),
            state=status.state,
            overrun_multiple=status.overrun_multiple,
            elapsed_s=status.elapsed_s,
            estimate_s=status.estimate_s,
        )
    return JobWatch(
        action="wait",
        wake_path=str(wake),
        state=status.state,
        overrun_multiple=seen_multiple,
        elapsed_s=status.elapsed_s,
        estimate_s=status.estimate_s,
    )




def result_path(job_dir: str | Path, cwd: str, result_file: str = "") -> Path:
    """Where the experiment's `result.json` actually is."""
    name = result_file or "result.json"
    in_job = Path(job_dir) / name
    if in_job.exists() or not cwd:
        return in_job
    beside = Path(cwd) / name
    return beside if beside.exists() else in_job


def _archive_result(
    logger: logging.Logger, found: Path, job_dir: Path, result_file: str = ""
) -> None:
    """Copy a result written in the experiment's cwd into the job directory."""
    target = job_dir / (result_file or "result.json")
    if found == target or not found.exists():
        return
    try:
        target.write_bytes(found.read_bytes())
    except OSError as exc:
        logger.warning("could not file %s beside %s: %s", found, target, exc)


def _read_result(path: Path) -> tuple[dict | None, str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None, "no result file was written"
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        return None, f"result file is not JSON: {exc}"
    if not isinstance(parsed, dict):
        return None, "result file is not a JSON object"
    missing = [k for k in RESULT_CORE if k not in parsed]
    if missing:
        return None, f"result file is missing its core keys: {missing}"
    return parsed, ""


@blueprint.node
def collect_job(
    logger: logging.Logger,
    job_dir: str,
    repo_dir: str = "",
    cwd: str = "",
    result_file: str = "result.json",
    memory_mb: int = 0,
) -> Collected:
    """Decide what happened, with **zero model calls**."""
    directory = Path(job_dir)
    runner = job.collect(directory)
    stderr_tail = _tail(directory / job.STDERR_NAME)
    found = result_path(directory, cwd, result_file)
    _archive_result(logger, found, directory, result_file)
    parsed, why = _read_result(found)
    locus = classify_fault(stderr_tail, repo_dir)

    base = Collected(
        exit_code=runner.exit_code,
        peak_rss_mb=runner.peak_rss_mb,
        wall_s=runner.wall_s,
        kill_reason=runner.kill_reason,
        tier=runner.tier,
        result_path=str(directory / (result_file or "result.json")),
        stderr_tail=stderr_tail,
    )

    over_ceiling = memory_mb > 0 and runner.peak_rss_mb >= memory_mb
    if runner.kill_reason == "memory" or (runner.exit_code not in (0, None) and over_ceiling):
        logger.warning(
            "job %s went over its declared %dMB (peak %.0fMB)",
            job_dir, memory_mb, runner.peak_rss_mb, extra={"activity": True},
        )
        return base.model_copy(
            update={
                "outcome": "over_resource",
                "reason": (
                    f"peak RSS {runner.peak_rss_mb:.0f}MB against a declared {memory_mb}MB"
                ),
            }
        )
    if runner.kill_reason == "lost":
        return base.model_copy(
            update={
                "outcome": "crash",
                "fault_locus": locus,
                "reason": "the supervisor vanished without writing what the job cost",
            }
        )
    if runner.exit_code not in (0, None):
        return base.model_copy(
            update={
                "outcome": "crash",
                "fault_locus": locus,
                "reason": f"the experiment exited {runner.exit_code}",
            }
        )
    if parsed is None:
        return base.model_copy(
            update={"outcome": "invalid", "fault_locus": locus, "reason": why}
        )

    logger.info(
        "measurement collected: %.0fs, %.0fMB peak, tier=%s",
        runner.wall_s, runner.peak_rss_mb, runner.tier, extra={"activity": True},
    )
    return base.model_copy(
        update={
            "outcome": "ok",
            "result_status": str(parsed.get("status") or ""),
            "metrics": parsed.get("metrics") or {},
            "seeds": list(parsed.get("seeds") or []),
            "controls": list(parsed.get("controls") or []),
            "n_completed": int(parsed.get("n_completed") or 0),
            "n_planned": int(parsed.get("n_planned") or 0),
        }
    )


@blueprint.node
def kill_job(logger: logging.Logger, job_dir: str, reason: str = "operator") -> Collected:
    """Stop a job mid-flight, and keep what it cost up to that point."""
    runner = job.kill(job_dir, reason=reason)
    logger.warning(
        "killed the job in %s after %.0fs (%s)", job_dir, runner.wall_s, reason,
        extra={"activity": True},
    )
    return Collected(
        outcome="killed",
        exit_code=runner.exit_code,
        peak_rss_mb=runner.peak_rss_mb,
        wall_s=runner.wall_s,
        kill_reason=runner.kill_reason,
        tier=runner.tier,
        reason=reason,
        stderr_tail=_tail(Path(job_dir) / job.STDERR_NAME),
    )


__all__ = [
    "check_envelope",
    "classify_fault",
    "collect_job",
    "dry_run",
    "job_dir_for",
    "kill_job",
    "submit_job",
    "watch_job",
]
