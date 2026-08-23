"""Running the experiment outside the agent turn, and classifying what came back.

Every function here is deterministic. That is the point of the file: the states that
submit a measurement, watch it, and decide what happened to it make **zero model
calls**, because the two artifacts a job leaves behind already answer the question. The
command writes what it found; the supervisor writes what it cost, in a file the command
cannot reach. "Measured and missed" and "produced no measurement" are therefore
different values rather than different readings of the same prose.

The engine primitive is `workhorse.job` (see `workhorse/docs/JOBS.md`). It knows
`command`, `memory_mb`, `estimate_s` — verbs. Everything in this module that is a noun
from *research*'s vocabulary — gates, envelopes, probes, `result.json`'s core — lives
here, on the workflow's side of that line.
"""
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

#: Where a gate's job directory goes, under the program. Inside the repo on purpose:
#: `publish_results` commits the program dir, so `result.json` and `runner.json` land on
#: the result branch beside the finding they justify. A year later "what did this number
#: cost, and on what commit" is answerable without a run directory nobody kept.
JOBS_DIR = "jobs"

#: The logs are the one thing that does not belong in git — they are large, they are
#: noise, and the classification already extracted the part that matters.
JOBS_GITIGNORE = "*.log\n"

#: The `n=1` rehearsal is bounded, because it runs *inside* the state that calls it.
#: A dry run that needs longer than this is not a dry run.
DRY_RUN_TIMEOUT_S = 900.0

#: How often the dry run looks for its own result while it blocks.
DRY_RUN_POLL_S = 1.0

#: Tail of `stderr.log` carried into a model's context. Enough to hold a traceback,
#: little enough that a chatty progress bar cannot crowd out the turn.
STDERR_TAIL_CHARS = 4000

#: The core `result.json` must carry for a measurement to count as one. A file that
#: parses but says nothing is `invalid`, not `ok` — the difference between an
#: experiment that ran and a file that exists.
RESULT_CORE = ("status", "metrics")

#: A Python traceback frame. The deepest one that names a file inside the repo is a
#: repo fault; the deepest one inside an installed `workhorse` / `ostler` is tooling.
FRAME_RE = re.compile(r'^\s*File "([^"]+)", line \d+', re.MULTILINE)

#: Installed packages whose frames mean *our apparatus* broke rather than the
#: experiment. A frame anywhere else — the stdlib, numpy, torch — is not evidence about
#: the tooling; it is evidence the experiment called it wrong.
TOOLING_PACKAGES = ("workhorse", "ostler")


# ── fault locus ─────────────────────────────────────────────────────────────


def classify_fault(stderr_text: str, repo_dir: str) -> str:
    """`repo`, `tooling`, or `unknown` — from the stack, not from an opinion.

    Routing a crash is the decision this loop gets most consequentially wrong when it
    is left to prose: a repo-code fault handed to a human is a run that sits dead until
    somebody notices, and a tooling fault handed to the engineer is three laps of
    repairing code that was never broken. The deepest frame is the one that raised, so
    it is the one that decides.

    `unknown` is returned honestly — a hang, an OOM, a silent wrong answer leaves no
    stack — and it is the only verdict that reaches an agent.
    """
    frames = FRAME_RE.findall(stderr_text or "")
    root = str(Path(repo_dir).resolve()) if repo_dir else ""
    for path in reversed(frames):  # deepest last in a Python traceback
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


# ── the envelope ────────────────────────────────────────────────────────────


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
    """Does the design fit the machine the program declared it has?

    A protocol that asks for more than the machine has is not a science failure and not
    an operator's problem — it is a protocol to rescope, which is the scientist's own
    work. Zero on an axis means the program declared no bound there, and an undeclared
    bound is not something to enforce.
    """
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


# ── submitting ──────────────────────────────────────────────────────────────


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
    """Launch the measurement detached, and hand back the handle as a parameter.

    Two refusals happen here rather than downstream, because both are cheaper to fix
    before hours of CPU than after:

    * **No probe, no job.** `estimate_s` sets the overrun thresholds the entire
      mid-flight triage is derived from, so an estimate with nothing timed behind it
      makes every later "is this running long?" unanswerable. It routes to the
      scientist, who owns the probe.
    * **A machine that cannot meet the containment floor** is a different repair from a
      command that will not start, which is why `workhorse.job` gives them different
      exceptions and why this keeps them apart.

    Idempotent by way of `job.submit`: a live job in this directory is adopted, not
    launched again. A resume re-enters this state from the top, and must not start a
    fifth hour of a four-hour job.
    """
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
        # A re-submission after a repair reuses the directory, and a previous attempt's
        # `result.json` left in it would make the next crash collect as a clean result.
        # Only ever when nothing is alive here: a live job is about to be *adopted*, and
        # deleting its artifacts underneath it would be deleting the measurement.
        for stale in (result_file or "result.json", job.RUNNER_NAME):
            (directory / stale).unlink(missing_ok=True)
        # And the copy in the experiment's own cwd, which is a repo directory reused by
        # every job: left there, last attempt's result is read as this attempt's.
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


# ── the n=1 rehearsal ───────────────────────────────────────────────────────


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
    """Rehearse the experiment at `n=1` **through the real runner**.

    Not in the engineer's shell. A command that works when typed and dies under the
    runner has failed the only test this node exists to run: it is the handoff that
    breaks — a relative path that meant something else from the agent's cwd, an
    inherited variable that is not in the job's environment, a result file written
    somewhere nobody will look.

    Bounded, because it blocks the state that called it. An overrun here is a failure,
    which is the one place in this workflow where that is true — the real measurement
    is never killed for running long.
    """
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
        estimate_s=0.0,  # no thresholds: this one is bounded by the caller instead
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

    runner = job.collect(directory)
    stderr_tail = _tail(directory / job.STDERR_NAME)
    produced = result_path(directory, cwd, result_file).exists()
    if runner.exit_code == 0 and produced:
        logger.info("n=1 rehearsal passed through the runner", extra={"activity": True})
        return DryRun(ok=True, exit_code=0)
    reason = (
        f"exit {runner.exit_code}" if runner.exit_code not in (0, None) else
        f"killed: {runner.kill_reason}" if runner.kill_reason else
        f"no {result_file} was written"
    )
    return DryRun(
        ok=False,
        exit_code=runner.exit_code,
        fault_locus=classify_fault(stderr_tail, repo_dir),
        stderr_tail=stderr_tail,
        reason=reason,
    )


# ── watching ────────────────────────────────────────────────────────────────


@blueprint.node
def watch_job(logger: logging.Logger, job_dir: str, seen_multiple: float = 0.0) -> JobWatch:
    """Arm the wake file, then read authoritative state — in that order.

    Arming first and polling second is what makes the wait lossless. An event that
    landed before the file was cleared is already in `poll`; an event after it
    re-creates the file, so the wait it answers is the next one. The reverse order
    drops exactly the wakeup that arrives between the two calls, which over a job
    measured in days is the one that matters.
    """
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


# ── collecting, and classifying ─────────────────────────────────────────────


def result_path(job_dir: str | Path, cwd: str, result_file: str = "") -> Path:
    """Where the experiment's `result.json` actually is.

    Two directories have a claim on it and only one of them is reachable from inside
    the experiment. The job directory is where the *supervisor* writes, and where a
    reader naturally looks — `runner.json` is there, and an artifact belongs beside
    the record of what it cost. But the experiment runs in the `cwd` the engineer
    declared, with an argv the runner does not rewrite, so a relative `--out` lands
    there and nowhere else; the job directory is not a path the command was ever told.

    Demanding the job directory anyway makes the contract unsatisfiable — the
    rehearsal fails, the engineer is handed "no result.json was written" about a file
    it can see on disk, and a repair budget is spent on an instruction no repair can
    follow. So both are accepted, job directory first, and `collect` files the winner
    beside `runner.json` afterwards.
    """
    name = result_file or "result.json"
    in_job = Path(job_dir) / name
    if in_job.exists() or not cwd:
        return in_job
    beside = Path(cwd) / name
    return beside if beside.exists() else in_job


def _archive_result(
    logger: logging.Logger, found: Path, job_dir: Path, result_file: str = ""
) -> None:
    """Copy a result written in the experiment's cwd into the job directory.

    So the pair the lead judges — what it found, what it cost — sits in one place, and
    so the next run of this gate cannot read the last one's file: the repo cwd is
    reused across jobs and is not cleared before launch, while the job directory is.
    """
    target = job_dir / (result_file or "result.json")
    if found == target or not found.exists():
        return
    try:
        target.write_bytes(found.read_bytes())
    except OSError as exc:  # the measurement is still valid; only the copy failed
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
    """Decide what happened, with **zero model calls**.

    Four outcomes, each read off a fact rather than off prose:

    * `over_resource` — the supervisor says it was killed for memory, or the kernel
      killed it under a cgroup ceiling. The protocol asked for more than it declared,
      so this is the scientist's to rescope.
    * `crash` — no usable measurement: a non-zero exit, or a supervisor that vanished.
    * `invalid` — a result file that will not parse, or one with no measurement in it.
      Distinct from `crash` on purpose: the command believed it succeeded, which is a
      different bug from one that fell over.
    * `ok` — a clean exit and a well-formed result. Only then is there anything for a
      lead to judge, and what it judges is the artifact.

    The fault locus rides along, decided from the stack.
    """
    directory = Path(job_dir)
    runner = job.collect(directory)
    stderr_tail = _tail(directory / job.STDERR_NAME)
    found = result_path(directory, cwd, result_file)
    _archive_result(logger, found, directory, result_file)
    parsed, why = _read_result(found)
    locus = classify_fault(stderr_tail, repo_dir)

    # What the *supervisor* recorded, which every outcome below carries unchanged —
    # a crash still says what it cost, and an abandoned experiment that said nothing
    # would be indistinguishable from one that was never run. Built as a model rather
    # than a dict of `**base` kwargs so the field types are checked here, once.
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
    """Stop a job mid-flight, and keep what it cost up to that point.

    A job that was stopped still says what it cost and why it stopped: deleting the
    evidence would make an abandoned experiment indistinguishable from one never run.
    """
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
