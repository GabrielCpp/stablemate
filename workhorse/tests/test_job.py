"""The detached job runner: what it measures, and what it refuses to guess.

These run real subprocesses, because every interesting property of this module is a
property of a *process that outlives the caller* — a fake would assert the mock. They are
still fast: the jobs are sub-second and the supervisor's sample interval is set from the
manifest, so nothing here waits on a wall clock.

Run: ./.venv/bin/python tests/test_job.py   (or via pytest)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

import pytest

from workhorse import job

LOG = logging.getLogger("test-job")

#: Every job in this file is sampled fast enough that a sub-second command is still seen.
FAST = {"sample_s": 0.05, "min_containment": "advisory"}


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def _finish(job_dir: Path, timeout: float = 30.0) -> job.RunnerResult:
    """Block until the supervisor has written what the job cost."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if (job_dir / job.RUNNER_NAME).exists():
            return job.collect(job_dir)
        time.sleep(0.05)
    raise AssertionError(f"no {job.RUNNER_NAME} in {job_dir} after {timeout}s")


def test_the_tiers_are_ordered_and_a_floor_is_compared_against_them():
    assert job.meets("premium", "best_effort")
    assert job.meets("best_effort", "best_effort")
    assert not job.meets("advisory", "best_effort")
    with pytest.raises(job.JobError):
        job.meets("premium", "gold")


def test_overrun_thresholds_double_and_are_derived_from_the_clock_alone():
    """`poll` and the supervisor must agree without either keeping a ledger."""
    assert job.overrun_multiple(elapsed_s=50, estimate_s=10, first=10) == 0.0
    assert job.overrun_multiple(elapsed_s=100, estimate_s=10, first=10) == 10.0
    assert job.overrun_multiple(elapsed_s=250, estimate_s=10, first=10) == 20.0
    assert job.overrun_multiple(elapsed_s=500, estimate_s=10, first=10) == 40.0
    assert job.overrun_multiple(elapsed_s=1000, estimate_s=10, first=10) == 80.0


def test_an_unestimated_job_never_reports_an_overrun():
    """No probe behind it means no threshold to cross — not an overrun at t=0."""
    assert job.overrun_multiple(elapsed_s=9999, estimate_s=0, first=10) == 0.0


def test_a_finished_job_reports_its_exit_code_and_what_it_cost(tmp_path: Path):
    directory = tmp_path / "ok"
    job.submit(
        {**FAST, "command": _python("open('result.json','w').write('{\"status\": \"ok\"}')")},
        job_dir=directory, logger=LOG,
    )
    result = _finish(directory)

    assert result.exit_code == 0
    assert result.kill_reason == ""
    assert result.wall_s > 0
    assert result.tier in job.TIERS

    status = job.poll(directory)
    assert status.state == "finished"
    assert status.alive is False
    assert status.result_ready is True


def test_a_crash_is_told_apart_from_a_miss_without_asking_anyone(tmp_path: Path):
    """The whole point of two artifacts: no result file *and* a non-zero exit."""
    directory = tmp_path / "crash"
    job.submit({**FAST, "command": _python("raise SystemExit(3)")}, job_dir=directory, logger=LOG)
    result = _finish(directory)

    assert result.exit_code == 3
    assert job.poll(directory).result_ready is False


def test_the_handle_is_on_disk_before_the_command_starts(tmp_path: Path):
    """A crash between submit and launch must still leave a findable job."""
    directory = tmp_path / "ordering"
    handle = job.submit(
        {**FAST, "command": _python(
            "import json,shutil; shutil.copyfile('handle.json','result.json')"
        )},
        job_dir=directory, logger=LOG,
    )
    result = _finish(directory)

    assert result.exit_code == 0
    seen = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    assert seen["pid"] == handle.pid


def test_stdout_and_stderr_are_the_commands_own_files(tmp_path: Path):
    directory = tmp_path / "streams"
    job.submit(
        {**FAST, "command": _python("import sys; print('out'); print('err', file=sys.stderr)")},
        job_dir=directory, logger=LOG,
    )
    _finish(directory)

    assert "out" in (directory / job.STDOUT_NAME).read_text(encoding="utf-8")
    assert "err" in (directory / job.STDERR_NAME).read_text(encoding="utf-8")


def test_a_live_job_is_adopted_rather_than_launched_twice(tmp_path: Path):
    """Re-entering the state that submitted a four-hour job must not start a fifth hour."""
    directory = tmp_path / "adopt"
    first = job.submit({**FAST, "command": _python("import time; time.sleep(30)")},
                       job_dir=directory, logger=LOG)
    _await_running(directory)
    second = job.submit({**FAST, "command": _python("import time; time.sleep(30)")},
                        job_dir=directory, logger=LOG)

    assert second.pid == first.pid
    job.kill(directory)


def test_a_killed_job_still_reports_what_it_cost(tmp_path: Path):
    directory = tmp_path / "killed"
    job.submit({**FAST, "command": _python("import time; time.sleep(30)")},
               job_dir=directory, logger=LOG)
    _await_running(directory)

    result = job.kill(directory, reason="operator")

    assert result.kill_reason == "operator"
    assert result.wall_s > 0
    assert job.poll(directory).state == "finished"


HOG = (
    "b=[]\n"
    "import time\n"
    "while True:\n"
    "    b.append(bytearray(8_000_000)); time.sleep(0.02)\n"
)


def test_the_sampler_kills_a_job_over_its_ceiling_and_says_which(tmp_path: Path):
    """The `best_effort` / `advisory` path, driven in-process so the tier is the one asserted.

    The supervisor reads its tier from the handle, so a test can hold this machine's own
    containment out of it — otherwise the branch under test is whichever branch the
    developer's kernel happens to offer.
    """
    directory = tmp_path / "sampled"
    directory.mkdir()
    _write(directory / job.MANIFEST_NAME,
           {"command": _python(HOG), "memory_mb": 64, "sample_s": 0.05})
    _write(directory / job.HANDLE_NAME,
           {"job_dir": str(directory), "pid": os.getpid(), "pgid": os.getpgid(0),
            "started_at": time.time(), "tier": "advisory"})

    job.supervise(directory)
    result = job.collect(directory)

    assert result.kill_reason == "memory"
    assert result.tier == "advisory"
    assert result.peak_rss_mb > 64


def test_a_job_over_its_ceiling_does_not_survive_on_this_machines_own_tier(tmp_path: Path):
    """However this machine contains a job, a 64MB ceiling is not something to run past.

    Which half fires is a property of the kernel, not of the code: under `premium` the
    cgroup kills it and the supervisor merely records the exit, so demanding one spelling
    of "stopped" here would make the suite pass or fail on the developer's init system.
    """
    directory = tmp_path / "hog"
    job.submit({**FAST, "memory_mb": 64, "command": _python(HOG)},
               job_dir=directory, logger=LOG)
    result = _finish(directory, timeout=60.0)

    if result.tier == "premium":
        assert result.exit_code not in (0, None)
    else:
        assert result.kill_reason == "memory"


def test_a_machine_that_cannot_meet_the_floor_refuses_the_job(tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch):
    """A weak machine is a different repair from a command that would not start."""
    monkeypatch.setattr(job, "containment_tier", lambda: "advisory")
    with pytest.raises(job.ContainmentUnavailable):
        job.submit({"command": ["true"], "min_containment": "premium"},
                   job_dir=tmp_path / "weak", logger=LOG)

    assert not (tmp_path / "weak" / job.HANDLE_NAME).exists()


def test_a_manifest_with_no_command_fails_in_the_callers_process(tmp_path: Path):
    """Not in a detached process whose stderr nobody is reading."""
    with pytest.raises(job.JobError):
        job.submit({**FAST, "command": []}, job_dir=tmp_path / "empty", logger=LOG)


def test_polling_a_directory_that_holds_no_job_is_an_answer_not_a_crash(tmp_path: Path):
    status = job.poll(tmp_path / "nothing")
    assert status.state == "missing"
    assert status.alive is False


def test_a_job_whose_supervisor_vanished_collects_as_lost(tmp_path: Path):
    """"We do not know" is a classification; silence is not."""
    directory = tmp_path / "lost"
    directory.mkdir()
    (directory / job.HANDLE_NAME).write_text(
        json.dumps({"job_dir": str(directory), "pid": 999_999, "pgid": 999_999,
                    "started_at": time.time() - 3600, "tier": "advisory"}),
        encoding="utf-8",
    )

    assert job.poll(directory).state == "lost"
    assert job.collect(directory).kill_reason == "lost"


def _await_running(job_dir: Path, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if (job_dir / job.CHILD_NAME).exists() and job.poll(job_dir).alive:
            return
        time.sleep(0.05)
    raise AssertionError(f"job in {job_dir} never came up")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
