"""The container path for turn records: the sidecar's run-dir RPCs and the host's pull.

The property under test is end-to-end and not per-function: a run that only ever existed
inside a container ends up in the host archive, keyed by the same visit key a local run
would have used. So most of these drive the *real* sidecar handlers through a fake socket
rather than a mock — the two halves agreeing is the thing that can break.

Run: uv run pytest tests/test_sidecar_turns.py
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

from groom import sidecar, sidecar_turns, store, turns


class _DB:
    """A throwaway groom.db, so the archive and its staging tree are temporary too."""

    def __enter__(self) -> _DB:
        self._dir = tempfile.TemporaryDirectory()
        self._prev = os.environ.get("GROOM_DB")
        os.environ["GROOM_DB"] = str(Path(self._dir.name) / "groom.db")
        store.reset()
        return self

    def __exit__(self, *exc: object) -> None:
        store.reset()
        if self._prev is None:
            os.environ.pop("GROOM_DB", None)
        else:
            os.environ["GROOM_DB"] = self._prev
        self._dir.cleanup()


@contextlib.contextmanager
def _runs_volume() -> Iterator[Path]:
    """A stand-in for the container's ``/runs`` mount, holding one run with one turn."""
    root = Path(tempfile.mkdtemp(prefix="sidecarturns-"))
    run = root / "run-1"
    (run / "transcripts").mkdir(parents=True)
    (run / "turns" / "001-00001-plan-qa").mkdir(parents=True)
    row = {
        "node": "plan-qa", "session_id": "s1", "generation": 1, "seq": 1,
        "ts": 1000.0, "backend": "acme-cli", "run_id": "R1", "flow": "main",
        "head": "aaa111",
    }
    (run / "sessions.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    stem = run / "transcripts" / "001-00001-plan-qa__s1"
    Path(f"{stem}.jsonl").write_text('{"role": "user"}\n', encoding="utf-8")
    Path(f"{stem}.meta.json").write_text(json.dumps({"source": "tee"}), encoding="utf-8")
    (run / "turns" / "001-00001-plan-qa" / "prompt.md").write_text("do it", encoding="utf-8")
    (run / "checkpoint.json").write_text("{}", encoding="utf-8")  # not a turn record
    try:
        with patch.object(sidecar, "RUNS_DIR", root):
            yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


class _FakeConn:
    """A sidecar connection whose RPCs are served by the real handlers, in-process.

    The point is that the host's pull and the container's handlers are exercised against
    each other: a mocked ``rpc`` would let the two drift and still pass.
    """

    def __init__(self, container_id: str = "c0ffee") -> None:
        self.container_id = container_id
        self.calls: list[str] = []

    async def rpc(self, method: str, params: dict, *, timeout: float = 0.0):
        self.calls.append(method)
        return sidecar._RPC_METHODS[method](params)


# --------------------------------------------------------------- the sidecar handlers
def test_list_turns_names_the_turn_surface_and_nothing_else():
    """A run dir also holds checkpoints and events. The host has other ways to read
    those, and naming them here would make this RPC a general reader for the volume."""
    with _runs_volume():
        out = sidecar._rpc_list_turns({"run": "run-1"})
    listed = sorted(f["path"] for f in out["files"])
    assert out["run"] == "run-1"
    assert listed == [
        "sessions.jsonl",
        "transcripts/001-00001-plan-qa__s1.jsonl",
        "transcripts/001-00001-plan-qa__s1.meta.json",
        "turns/001-00001-plan-qa/prompt.md",
    ]
    assert all(f["size"] > 0 for f in out["files"])


def test_read_turn_file_slices_and_reports_the_end():
    with _runs_volume():
        first = sidecar._rpc_read_turn_file(
            {"run": "run-1", "path": "transcripts/001-00001-plan-qa__s1.jsonl", "length": 4}
        )
        rest = sidecar._rpc_read_turn_file(
            {"run": "run-1", "path": "transcripts/001-00001-plan-qa__s1.jsonl", "offset": 4}
        )
    assert base64.b64decode(first["data"]) == b'{"ro'
    assert first["eof"] is False
    assert base64.b64decode(rest["data"]) == b'le": "user"}\n'
    assert rest["eof"] is True


def test_read_turn_file_refuses_anything_outside_a_turn_record():
    """Traversal is the guard `_safe_relpath` already gives every read; this is the
    narrower one — a path with no `..` in it that is simply not a turn record."""
    with _runs_volume():
        for bad in ("checkpoint.json", "../etc/passwd", "/etc/passwd"):
            try:
                sidecar._rpc_read_turn_file({"run": "run-1", "path": bad})
            except ValueError:
                continue
            raise AssertionError(f"expected ValueError for {bad!r}")


def test_read_turn_file_refuses_a_symlink_out_of_the_volume():
    """The workspace reads survive on `_safe_relpath` alone because they return text a
    panel asked for. These return raw bytes of whatever they are pointed at, and a
    symlink inside the run dir leaves the volume without a single `..` in the request."""
    with _runs_volume() as root:
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            fh.write("secret\n")
            outside = fh.name
        (root / "run-1" / "transcripts" / "escape.jsonl").symlink_to(outside)
        try:
            sidecar._rpc_read_turn_file({"run": "run-1", "path": "transcripts/escape.jsonl"})
        except ValueError:
            return
        finally:
            os.unlink(outside)
    raise AssertionError("expected ValueError for a symlink out of the volume")


def test_a_transcript_write_announces_and_a_checkpoint_write_does_not():
    """The announce is a hint that costs one small frame per coalesced watch batch —
    which is what lets a node stream a megabyte of transcript without streaming it here."""
    with _runs_volume() as root:
        frame = sidecar._turn_announce(root / "run-1" / "transcripts" / "x.jsonl")
        assert frame is not None
        assert frame["type"] == "turn" and frame["run"] == "run-1"
        assert "run_id" in frame  # identity rides along; the host needs it to file the pull
        assert sidecar._turn_announce(root / "run-1" / "checkpoint.json") is None
        assert sidecar._turn_announce(Path("/workspace/a.py")) is None


# ------------------------------------------------------------------------- the pull
def test_a_container_run_is_pulled_into_the_host_archive():
    """The whole point: a run dir that exists only inside a container ends up archived
    under the same visit key a local run would have produced."""
    with _DB(), _runs_volume():
        conn = _FakeConn()
        archived = asyncio.run(sidecar_turns.pull(conn, run="run-1", run_id="R1", workflow="coder"))

        assert archived == 1
        indexed = store.query_turns(run="R1")
        assert [(r["generation"], r["seq"], r["session_id"]) for r in indexed] == [(1, 1, "s1")]
        assert indexed[0]["source"] == "tee"
        assert indexed[0]["head"] == "aaa111"
        record = turns.record_path(indexed[0])
        assert (record / "transcript.jsonl").read_text() == '{"role": "user"}\n'
        assert (record / "prompt.md").read_text() == "do it"


def test_a_second_pull_refetches_only_what_grew():
    """Announces arrive per watch batch on a live run, so most pulls concern files that
    are still the file they were. Re-reading them over the socket every time would make
    a chatty container expensive to watch."""
    with _DB(), _runs_volume() as root:
        conn = _FakeConn()
        asyncio.run(sidecar_turns.pull(conn, run="run-1", run_id="R1"))
        conn.calls.clear()

        asyncio.run(sidecar_turns.pull(conn, run="run-1", run_id="R1"))
        assert conn.calls == ["listTurns"]  # nothing moved, so nothing was read

        transcript = root / "run-1" / "transcripts" / "001-00001-plan-qa__s1.jsonl"
        transcript.write_text('{"role": "user"}\n{"role": "assistant"}\n', encoding="utf-8")
        conn.calls.clear()
        asyncio.run(sidecar_turns.pull(conn, run="run-1", run_id="R1"))
        assert conn.calls.count("readTurnFile") >= 1
        assert (turns.record_path(store.query_turns(run="R1")[0]) / "transcript.jsonl").read_text().count("\n") == 2


def test_a_failing_pull_is_not_a_broken_groom():
    """The sidecar is non-authoritative. A container whose records did not arrive is a
    poorer archive, and must not surface as an exception in the socket receive loop."""

    class _Broken(_FakeConn):
        async def rpc(self, method: str, params: dict, *, timeout: float = 0.0):
            raise RuntimeError("socket went away")

    async def _drive() -> None:
        conn = _Broken()
        sidecar_turns.schedule(conn, run="run-1")
        await asyncio.sleep(0)
        while conn.container_id in sidecar_turns._IN_FLIGHT:
            await asyncio.sleep(0.01)

    with _DB(), _runs_volume():
        asyncio.run(_drive())


def test_the_staged_mirror_is_dropped_once_the_run_is_over():
    """The mirror is a cache that makes the next pull cheap. After the terminal there is
    no next pull, and a throwaway container would otherwise leave its copy on disk
    forever."""

    async def _drive(conn) -> None:
        sidecar_turns.schedule(conn, run="run-1", run_id="R1", final=True)
        await asyncio.sleep(0)
        while conn.container_id in sidecar_turns._IN_FLIGHT:
            await asyncio.sleep(0.01)

    with _DB(), _runs_volume():
        conn = _FakeConn()
        asyncio.run(_drive(conn))

        assert len(store.query_turns(run="R1")) == 1  # archived before the cache went
        assert not (sidecar_turns.staging_root() / conn.container_id).exists()


if __name__ == "__main__":
    import sys
    import traceback

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except Exception:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    sys.exit(1 if failures else 0)
