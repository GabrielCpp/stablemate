"""Tests for who a sidecar's run is: the ids it reads from the run record and the environment, the container id rule, the hello sent again on a change, and the wait for a mount that is not there yet."""
from __future__ import annotations

import asyncio
import contextlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from _settle import watch_started
from groom import sidecar, sidecar_identity


def test_a_container_launched_without_a_run_id_still_advertises(tmp_path):
    """Driving compose by hand sets no run id."""
    dockerenv = tmp_path / ".dockerenv"
    dockerenv.write_text("")
    with patch.object(sidecar, "snapshot", return_value={"gates": []}), \
         patch.object(sidecar, "DOCKERENV", dockerenv), \
         patch.object(sidecar, "RUNS_DIR", tmp_path / "runs"), \
         patch.dict(sidecar.os.environ, {}, clear=True):
        identity = sidecar._hello_frame()["identity"]
    assert identity["run_id"] == ""
    assert identity["container_id"]


def _record(runs: Path, name: str = "20260101T000000", **fields) -> None:
    run_dir = runs / name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(json.dumps(fields))


def test_identity_comes_from_the_run_record_over_the_environment(tmp_path):
    _record(
        tmp_path,
        run_id="run-from-record",
        workflow="coder",
        repo_start={"root": "/work/acme-api", "path": "/work/acme-api/sub", "branch": "feat/x"},
    )
    env = {"AGENT_RUN_ID": "run-from-env", "WORKFLOW": "other", "REPO_NAME": "env-repo", "REPO_BRANCH": "env-branch"}
    with patch.object(sidecar, "RUNS_DIR", tmp_path), patch.dict(sidecar.os.environ, env, clear=True):
        identity = sidecar._identity()
    assert identity["run_id"] == "run-from-record"
    assert identity["workflow"] == "coder"
    assert identity["repo_name"] == "acme-api"
    assert identity["name"] == "acme-api"
    assert identity["repo_branch"] == "feat/x"


def test_the_repo_name_falls_back_to_the_start_path_when_the_record_has_no_root(tmp_path):
    _record(tmp_path, run_id="r", repo_start={"path": "/work/acme-web", "branch": "main"})
    with patch.object(sidecar, "RUNS_DIR", tmp_path), patch.dict(sidecar.os.environ, {}, clear=True):
        assert sidecar._identity()["repo_name"] == "acme-web"


def test_identity_falls_back_to_the_environment_with_no_run_record(tmp_path):
    env = {"AGENT_RUN_ID": "run-from-env", "WORKFLOW": "coder", "REPO_NAME": "env-repo", "REPO_BRANCH": "env-branch"}
    with patch.object(sidecar, "RUNS_DIR", tmp_path), patch.dict(sidecar.os.environ, env, clear=True):
        identity = sidecar._identity()
    assert (identity["run_id"], identity["workflow"], identity["repo_name"], identity["repo_branch"]) == (
        "run-from-env", "coder", "env-repo", "env-branch",
    )
    assert identity["name"] == "env-repo"


def test_a_record_missing_a_field_leaves_that_field_to_the_environment(tmp_path):
    _record(tmp_path, workflow="coder")
    with patch.object(sidecar, "RUNS_DIR", tmp_path), \
         patch.dict(sidecar.os.environ, {"AGENT_RUN_ID": "run-from-env"}, clear=True):
        identity = sidecar._identity()
    assert identity["run_id"] == "run-from-env"
    assert identity["workflow"] == "coder"


def test_the_name_is_the_hostname_when_no_repo_is_known(tmp_path):
    with patch.object(sidecar, "RUNS_DIR", tmp_path), \
         patch.object(sidecar_identity.socket, "gethostname", return_value="build-box"), \
         patch.dict(sidecar.os.environ, {}, clear=True):
        assert sidecar._identity()["name"] == "build-box"


def test_no_container_id_outside_a_container(tmp_path):
    with patch.object(sidecar, "RUNS_DIR", tmp_path), \
         patch.object(sidecar, "DOCKERENV", tmp_path / "no-dockerenv"), \
         patch.dict(sidecar.os.environ, {}, clear=True):
        assert sidecar._identity()["container_id"] == ""


def test_the_container_id_is_the_hostname_inside_a_container(tmp_path):
    dockerenv = tmp_path / ".dockerenv"
    dockerenv.write_text("")
    with patch.object(sidecar, "RUNS_DIR", tmp_path), \
         patch.object(sidecar, "DOCKERENV", dockerenv), \
         patch.object(sidecar_identity.socket, "gethostname", return_value="0123456789abcdef"), \
         patch.dict(sidecar.os.environ, {}, clear=True):
        assert sidecar._identity()["container_id"] == "0123456789ab"


def test_groom_container_id_wins_over_the_hostname(tmp_path):
    dockerenv = tmp_path / ".dockerenv"
    dockerenv.write_text("")
    with patch.object(sidecar, "RUNS_DIR", tmp_path), \
         patch.object(sidecar, "DOCKERENV", dockerenv), \
         patch.dict(sidecar.os.environ, {"GROOM_CONTAINER_ID": "named-box"}, clear=True):
        assert sidecar._identity()["container_id"] == "named-box"
    with patch.object(sidecar, "RUNS_DIR", tmp_path), \
         patch.object(sidecar, "DOCKERENV", tmp_path / "no-dockerenv"), \
         patch.dict(sidecar.os.environ, {"GROOM_CONTAINER_ID": "named-box"}, clear=True):
        assert sidecar._identity()["container_id"] == "named-box"


def test_a_second_hello_follows_the_run_record_once_it_appears():
    async def _drive():
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            with patch.object(sidecar, "WORKSPACE_DIR", Path("/nonexistent-groom-test-xyz")), \
                 patch.object(sidecar, "RUNS_DIR", runs), \
                 patch.object(sidecar, "DOCKERENV", runs / "no-dockerenv"), \
                 patch.dict(sidecar.os.environ, {}, clear=True), \
                 watch_started(sidecar) as watching:
                first = sidecar._hello_frame()
                outbox: asyncio.Queue = asyncio.Queue()
                stop = asyncio.Event()
                watcher = asyncio.create_task(sidecar._watch_loop(outbox, stop, sidecar._announced(first["identity"])))
                await watching.wait()
                _record(runs, run_id="run-late", workflow="coder", repo_start={"root": "/work/acme", "branch": "main"})
                try:
                    while True:
                        frame = await asyncio.wait_for(outbox.get(), timeout=30)
                        if frame["type"] == "hello":
                            return first, frame
                finally:
                    stop.set()
                    watcher.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await watcher

    first, second = asyncio.run(_drive())
    assert first["identity"]["run_id"] == ""
    assert second["identity"]["run_id"] == "run-late"
    assert second["identity"]["repo_name"] == "acme"


def test_an_unchanged_identity_sends_no_second_hello():
    with patch.object(sidecar, "_identity", return_value={"run_id": "r"}):
        assert sidecar._announced({"run_id": "r"}).refresh() is None


def test_a_runs_dir_that_appears_after_the_start_is_watched_and_greeted(tmp_path):
    async def _drive():
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        runs = tmp_path / "runs"
        with patch.object(sidecar, "WORKSPACE_DIR", workspace), \
             patch.object(sidecar, "RUNS_DIR", runs), \
             patch.object(sidecar, "MOUNT_POLL_S", 0.05), \
             patch.object(sidecar, "DOCKERENV", tmp_path / "no-dockerenv"), \
             patch.dict(sidecar.os.environ, {}, clear=True), \
             watch_started(sidecar) as watching:
            first = sidecar._hello_frame()
            outbox: asyncio.Queue = asyncio.Queue()
            stop = asyncio.Event()
            watcher = asyncio.create_task(sidecar._watch_loop(outbox, stop, sidecar._announced(first["identity"])))
            await watching.wait()
            _record(runs, run_id="run-after-mount", workflow="coder")
            try:
                while True:
                    frame = await asyncio.wait_for(outbox.get(), timeout=30)
                    if frame["type"] == "hello":
                        return frame
            finally:
                stop.set()
                watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watcher

    assert asyncio.run(_drive())["identity"]["run_id"] == "run-after-mount"


def test_a_sidecar_started_with_neither_mount_waits_for_them(tmp_path):
    async def _drive():
        workspace = tmp_path / "workspace"
        runs = tmp_path / "runs"
        with patch.object(sidecar, "WORKSPACE_DIR", workspace), \
             patch.object(sidecar, "RUNS_DIR", runs), \
             patch.object(sidecar, "MOUNT_POLL_S", 0.05), \
             patch.object(sidecar, "DOCKERENV", tmp_path / "no-dockerenv"), \
             patch.dict(sidecar.os.environ, {}, clear=True):
            first = sidecar._hello_frame()
            outbox: asyncio.Queue = asyncio.Queue()
            stop = asyncio.Event()
            watcher = asyncio.create_task(sidecar._watch_loop(outbox, stop, sidecar._announced(first["identity"])))
            await asyncio.sleep(0)
            _record(runs, run_id="run-late-mounts", workflow="coder")
            workspace.mkdir()
            try:
                return await asyncio.wait_for(outbox.get(), timeout=30)
            finally:
                stop.set()
                watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watcher

    frame = asyncio.run(_drive())
    assert frame["type"] == "hello"
    assert frame["identity"]["run_id"] == "run-late-mounts"
