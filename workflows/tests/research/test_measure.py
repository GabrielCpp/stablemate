"""The deterministic half of the research loop (`research/nodes/measure.py`).

Every function under test here decides something the loop used to leave to a prompt:
where a crash came from, whether a protocol fits the machine, and whether what came
back is a measurement at all. They are ordinary functions over two files on disk, so
they are tested as such — real directories, real `runner.json` / `result.json`, no
model call anywhere in the file.

That is the property worth protecting. `collect_job` telling `crash` from `invalid`
from `over_resource` is what lets the same three outcomes route to three different
owners; a version of it that asked an agent would route them all to whoever the agent
felt like naming.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from workhorse import job
from workhorse_workflows.research.nodes import measure

LOG = logging.getLogger("test.research.measure")


def _job_dir(root: Path, name: str = "G1") -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write(directory: Path, name: str, payload: dict) -> None:
    (directory / name).write_text(json.dumps(payload), encoding="utf-8")


# ------------------------------------------------------------------ fault locus


def _traceback(*files: str) -> str:
    frames = "\n".join(f'  File "{path}", line 12, in run\n    boom()' for path in files)
    return f"Traceback (most recent call last):\n{frames}\nRuntimeError: boom\n"


def test_the_deepest_frame_decides_the_locus(tmp_path):
    """A repo frame under an apparatus frame is a repo fault: the repo is what raised.

    Order matters more than presence here. Both packages appear in almost every
    traceback this loop will ever see — workhorse launched the thing — so a classifier
    that asked "is workhorse mentioned?" would route every crash to a human.
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    stack = _traceback(
        "/usr/lib/python3.12/site-packages/workhorse/job.py",
        str(repo / "src" / "train.py"),
    )
    assert measure.classify_fault(stack, str(repo)) == "repo"


def test_an_apparatus_frame_below_the_repo_is_a_tooling_fault(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    stack = _traceback(
        str(repo / "src" / "train.py"),
        "/usr/lib/python3.12/site-packages/ostler/graph.py",
    )
    assert measure.classify_fault(stack, str(repo)) == "tooling"


def test_a_third_party_frame_is_not_evidence_about_the_tooling(tmp_path):
    """numpy raising says the experiment called it wrong, which is a repo fault."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    stack = _traceback(
        str(repo / "src" / "train.py"),
        "/usr/lib/python3.12/site-packages/numpy/core/_methods.py",
    )
    assert measure.classify_fault(stack, str(repo)) == "repo"


def test_no_stack_is_unknown_not_a_guess(tmp_path):
    """A hang, an OOM and a silent wrong answer leave no frames. Say so."""
    assert measure.classify_fault("Killed\n", str(tmp_path)) == "unknown"
    assert measure.classify_fault("", str(tmp_path)) == "unknown"


# -------------------------------------------------------------------- envelope


def test_an_undeclared_axis_is_not_a_bound():
    """Zero means the program declared nothing there, so there is nothing to enforce."""
    check = measure.check_envelope(LOG, memory_mb=500_000, cpus=256, disk_gb=9000)
    assert check.fits, check.reason


def test_a_protocol_over_the_declared_machine_does_not_fit():
    check = measure.check_envelope(LOG, memory_mb=64_000, envelope_ram_gb=32)
    assert not check.fits
    assert "memory" in check.reason


def test_a_gpu_the_program_does_not_have_does_not_fit():
    check = measure.check_envelope(LOG, gpu="a100", envelope_gpu="none")
    assert not check.fits
    assert "gpu" in check.reason


def test_the_job_dir_is_one_directory_per_gate_inside_the_program():
    assert measure.job_dir_for("/w/repo", "programs/alpha", "G1") == (
        "/w/repo/programs/alpha/jobs/G1"
    )
    assert measure.job_dir_for("/w/repo", "programs/alpha", "G1", "-dry").endswith("G1-dry")


# ---------------------------------------------------------------- the refusals


def test_a_build_with_no_command_is_a_repo_fault(tmp_path):
    refused = measure.submit_job(LOG, job_dir=str(tmp_path / "G1"), command=[], cwd=str(tmp_path))
    assert not refused.submitted
    assert refused.fault_locus == "repo"


def test_an_estimate_with_no_probe_behind_it_is_refused_before_the_cpu_is_spent(tmp_path):
    """The scientist's refusal, not the engineer's: the probe is the designer's work.

    `estimate_s` is what every overrun threshold is derived from, so an estimate with
    nothing timed behind it makes the whole mid-flight triage unanswerable — and it is
    far cheaper to say so now than after four hours of a job nobody can judge as long.
    """
    refused = measure.submit_job(
        LOG,
        job_dir=str(tmp_path / "G1"),
        command=["true"],
        cwd=str(tmp_path),
        estimate_s=3600.0,
        probe_units_timed=0,
    )
    assert not refused.submitted
    assert refused.fault_locus == "design"
    # Nothing was launched: the refusal is before the manifest.
    assert not (tmp_path / "G1" / job.MANIFEST_NAME).exists()


# --------------------------------------------------------------- classifying


def _finished(directory: Path, **runner: object) -> None:
    _write(directory, job.HANDLE_NAME, {"pid": 1, "pgid": 1, "tier": "premium",
                                        "started_at": time.time() - 10})
    _write(directory, job.RUNNER_NAME, {"exit_code": 0, "peak_rss_mb": 100.0, "wall_s": 9.0,
                                        "kill_reason": "", "tier": "premium", **runner})


def test_a_clean_exit_with_a_well_formed_result_is_ok(tmp_path):
    directory = _job_dir(tmp_path)
    _finished(directory)
    _write(directory, "result.json", {
        "status": "ok", "metrics": {"accuracy": 0.93}, "seeds": [1, 2, 3],
        "controls": ["random"], "n_completed": 240, "n_planned": 240,
    })

    collected = measure.collect_job(LOG, job_dir=str(directory))

    assert collected.outcome == "ok"
    assert collected.metrics == {"accuracy": 0.93}
    assert collected.n_completed == 240 and collected.n_planned == 240
    # The cost came from the supervisor's file, which the experiment cannot write.
    assert collected.tier == "premium" and collected.wall_s == 9.0


def test_a_result_file_with_no_measurement_in_it_is_invalid_not_ok(tmp_path):
    """`invalid` is a separate outcome from `crash` on purpose: the command believed
    it succeeded, which is a different bug from one that fell over."""
    directory = _job_dir(tmp_path)
    _finished(directory)
    _write(directory, "result.json", {"note": "ran fine"})

    collected = measure.collect_job(LOG, job_dir=str(directory))

    assert collected.outcome == "invalid"
    assert "core keys" in collected.reason


def test_a_non_zero_exit_is_a_crash_carrying_where_it_came_from(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    directory = _job_dir(tmp_path)
    _finished(directory, exit_code=1)
    (directory / job.STDERR_NAME).write_text(_traceback(str(repo / "src" / "train.py")))

    collected = measure.collect_job(LOG, job_dir=str(directory), repo_dir=str(repo))

    assert collected.outcome == "crash"
    assert collected.fault_locus == "repo"
    assert "exited 1" in collected.reason


def test_going_over_the_declared_memory_is_the_scientist_s_to_rescope(tmp_path):
    directory = _job_dir(tmp_path)
    _finished(directory, exit_code=137, peak_rss_mb=8200.0, kill_reason="memory")

    collected = measure.collect_job(LOG, job_dir=str(directory), memory_mb=8000)

    assert collected.outcome == "over_resource"
    assert "8000MB" in collected.reason


def test_a_supervisor_that_vanished_is_a_crash_rather_than_silence(tmp_path):
    """No `runner.json` at all. "We do not know what it cost" is a classification."""
    directory = _job_dir(tmp_path)
    _write(directory, job.HANDLE_NAME, {"pid": 1, "pgid": 1, "tier": "premium",
                                        "started_at": time.time() - 10})

    collected = measure.collect_job(LOG, job_dir=str(directory))

    assert collected.outcome == "crash"
    assert collected.kill_reason == "lost"


# ------------------------------------------------------------------- watching


def _running(directory: Path, *, elapsed_s: float, estimate_s: float) -> None:
    """A job this process's own group stands in for, so `poll` reads it as alive."""
    _write(directory, job.HANDLE_NAME, {
        "pid": os.getpid(), "pgid": os.getpgid(0), "tier": "premium",
        "started_at": time.time() - elapsed_s,
    })
    _write(directory, job.MANIFEST_NAME, {"estimate_s": estimate_s, "result_file": "result.json"})
    (directory / job.HEARTBEAT_NAME).touch()


def test_watching_arms_the_wake_file_before_it_reads_the_state(tmp_path):
    """Arm first, poll second — the ordering is what makes a days-long wait lossless.

    A wakeup consumed on the previous lap would otherwise answer the next wait
    instantly; a wakeup that lands after the delete re-creates the file and answers the
    wait it belongs to. The reverse order drops exactly the event in between.
    """
    directory = _job_dir(tmp_path)
    _running(directory, elapsed_s=5.0, estimate_s=600.0)
    (directory / job.WAKE_NAME).write_text("stale wakeup")

    watch = measure.watch_job(LOG, job_dir=str(directory))

    assert watch.action == "wait"
    assert watch.wake_path == str(directory / job.WAKE_NAME)
    assert not (directory / job.WAKE_NAME).exists()


def test_a_finished_job_is_collected_not_waited_on(tmp_path):
    directory = _job_dir(tmp_path)
    _finished(directory)

    assert measure.watch_job(LOG, job_dir=str(directory)).action == "collect"


def test_an_overrun_past_a_fresh_threshold_goes_to_triage_once(tmp_path):
    """Time is a bug signal, so an overrun reaches the engineer — but each threshold
    reaches them once. `seen_multiple` is the highest already triaged, and it rides in
    the checkpoint precisely so a 10× job does not triage on every wakeup."""
    directory = _job_dir(tmp_path)
    _running(directory, elapsed_s=3600.0, estimate_s=360.0)

    first = measure.watch_job(LOG, job_dir=str(directory))
    assert first.action == "triage"
    assert first.overrun_multiple == 10.0

    again = measure.watch_job(LOG, job_dir=str(directory), seen_multiple=first.overrun_multiple)
    assert again.action == "wait"
