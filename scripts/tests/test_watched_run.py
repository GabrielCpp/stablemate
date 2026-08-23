"""What survives each way a watched run can die.

Every case kills something for real and reads the verdict back off disk, because the
thing under test is what is *left behind* by a death, and a fake that returns a
prepared status file has already supplied the record whose absence is the bug.

The two that matter are the last two: a child killed while its supervisor lives leaves
a tombstone, and a whole group killed at once leaves nothing but a stale heartbeat.
The second is the case the module exists for — it is how a real benchmark round
disappeared, reporting an empty log and no exit code.
"""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "watched_run.py"


@pytest.fixture(scope="module")
def watched() -> Any:
    spec = importlib.util.spec_from_file_location("watched_run", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before exec: the module defines a dataclass, and `dataclasses` resolves
    # its annotations through `sys.modules[cls.__module__]`.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _start(watched: Any, directory: Path, name: str, *command: str) -> dict[str, Any]:
    """Launch, then wait for the supervisor's first record to land."""
    code = watched.main(["--dir", str(directory), "start", "--name", name, "--", *command])
    assert code == 0
    status = directory / f"{name}.json"
    for _ in range(200):
        if status.exists():
            with open(status) as handle:
                return dict(json.load(handle))
        time.sleep(0.05)
    raise AssertionError(f"{name}: supervisor wrote no status file")


def _settle(status: Path, *, until: tuple[str, ...], timeout: float = 15.0) -> dict[str, Any]:
    """Poll the status file until the supervisor writes one of the states asked for."""
    deadline = time.time() + timeout
    data: dict[str, Any] = {}
    while time.time() < deadline:
        with open(status) as handle:
            data = dict(json.load(handle))
        if data.get("state") in until:
            return data
        time.sleep(0.05)
    raise AssertionError(f"stayed {data.get('state')!r}, never reached {until}")


def _verdict(watched: Any, directory: Path, name: str) -> str:
    status = directory / f"{name}.json"
    with open(status) as handle:
        record = watched.Record(status, json.load(handle))
    return str(watched._classify(record)[0])


def test_a_command_that_succeeds_is_recorded_as_ok(watched: Any, tmp_path: Path) -> None:
    _start(watched, tmp_path, "fine", "bash", "-c", "echo hello; exit 0")
    _settle(tmp_path / "fine.json", until=("exited",))
    assert _verdict(watched, tmp_path, "fine") == "ok"
    assert (tmp_path / "fine.log").read_text().strip() == "hello"


def test_a_nonzero_exit_is_failed_rather_than_ok(watched: Any, tmp_path: Path) -> None:
    _start(watched, tmp_path, "bad", "bash", "-c", "exit 3")
    record = _settle(tmp_path / "bad.json", until=("exited",))
    assert record["returncode"] == 3
    assert _verdict(watched, tmp_path, "bad") == "failed"


def test_output_is_captured_unbuffered_so_a_death_leaves_progress(watched: Any, tmp_path: Path) -> None:
    """An empty log is indistinguishable from a killed run; a buffered one is empty."""
    _start(watched, tmp_path, "chatty", "python3", "-c", "print('step one'); import time; time.sleep(30)")
    log = tmp_path / "chatty.log"
    deadline = time.time() + 10
    while time.time() < deadline and "step one" not in log.read_text():
        time.sleep(0.05)
    assert "step one" in log.read_text()
    assert _verdict(watched, tmp_path, "chatty") == "running"


def test_a_child_killed_under_a_live_supervisor_leaves_a_tombstone(watched: Any, tmp_path: Path) -> None:
    started = _start(watched, tmp_path, "childkill", "bash", "-c", "sleep 30")
    os.kill(int(started["pid"]), signal.SIGKILL)
    record = _settle(tmp_path / "childkill.json", until=("signaled",))
    assert record["signal"] == "SIGKILL"
    assert _verdict(watched, tmp_path, "childkill") == "killed"


def test_a_whole_group_killed_at_once_is_still_seen_as_a_death(watched: Any, tmp_path: Path) -> None:
    """No tombstone is written — nothing was alive to write one. The heartbeat is the evidence."""
    started = _start(watched, tmp_path, "groupkill", "bash", "-c", "sleep 30")
    supervisor = int(started["supervisor_pid"])
    os.killpg(supervisor, signal.SIGKILL)
    for _ in range(200):
        if not _alive(supervisor):
            break
        time.sleep(0.05)

    status = tmp_path / "groupkill.json"
    with open(status) as handle:
        assert json.load(handle)["state"] == "running", "the supervisor died before it could say so"

    assert _verdict(watched, tmp_path, "groupkill") == "vanished"
    with open(status) as handle:
        assert json.load(handle)["state"] == "vanished", "the verdict is recorded, not just printed"


def test_check_reports_nonzero_when_any_run_died(watched: Any, tmp_path: Path) -> None:
    _start(watched, tmp_path, "fine", "bash", "-c", "exit 0")
    _settle(tmp_path / "fine.json", until=("exited",))
    assert watched.main(["--dir", str(tmp_path), "check"]) == 0

    _start(watched, tmp_path, "bad", "bash", "-c", "exit 1")
    _settle(tmp_path / "bad.json", until=("exited",))
    assert watched.main(["--dir", str(tmp_path), "check"]) == 1


def test_a_second_start_under_a_live_name_is_refused(watched: Any, tmp_path: Path) -> None:
    """Two supervisors on one name would each overwrite the other's record."""
    _start(watched, tmp_path, "busy", "bash", "-c", "sleep 30")
    assert watched.main(["--dir", str(tmp_path), "start", "--name", "busy", "--", "true"]) == 2


def test_start_without_a_command_is_an_error(watched: Any, tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        watched.main(["--dir", str(tmp_path), "start", "--name", "empty"])


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True
