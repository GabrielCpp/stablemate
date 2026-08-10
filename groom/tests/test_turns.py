"""The durable turn-record archive: harvest, idempotency, backfill and retention.

What is asserted here is the archive's contract rather than its file layout: a node
visited twice yields two records, a tick that finds nothing new copies nothing, a run dir
that has gone is not an error, and a scratch run's records never become durable.

Run: uv run pytest tests/test_turns.py
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

from groom import store, turns


class _DB:
    """A throwaway groom.db in its own directory, so the archive is temporary too.

    A directory rather than a bare temp file because ``turns.transcripts_root`` is
    derived from the database's parent — which is the point of deriving it: pointing
    ``$GROOM_DB`` at a test location moves the bodies with the index.
    """

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
def _workspace() -> Iterator[Path]:
    """A scratch dir whose *name* does not look throwaway to the archive.

    ``store.is_scratch_run_dir`` reads a ``tmpXXXXXX`` directory in the temp root as a
    test run and excludes it from the inventory — correctly, and that is asserted below.
    So a test that needs its fake run to be inventoried cannot use the default prefix.
    """
    path = Path(tempfile.mkdtemp(prefix="turnstest-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _run_dir(root: Path, rows: list[dict]) -> Path:
    """A run dir shaped like the one the engine writes, for the given session-map rows."""
    run_dir = root / "run"
    (run_dir / "transcripts").mkdir(parents=True, exist_ok=True)
    (run_dir / "turns").mkdir(parents=True, exist_ok=True)
    with (run_dir / "sessions.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return run_dir


def _visit(run_dir: Path, row: dict, transcript: str = "{}\n", prompt: str = "do the thing") -> None:
    slug = f"{row['generation']:03d}-{row['seq']:05d}-{row['node']}"
    stem = run_dir / "transcripts" / f"{slug}__{row['session_id']}"
    Path(f"{stem}.jsonl").write_text(transcript, encoding="utf-8")
    Path(f"{stem}.meta.json").write_text(json.dumps({"source": "store"}), encoding="utf-8")
    visit = run_dir / "turns" / slug
    visit.mkdir(parents=True, exist_ok=True)
    (visit / "prompt.md").write_text(prompt, encoding="utf-8")
    (visit / "output.json").write_text('{"verdict": "ok"}', encoding="utf-8")


def _rows() -> list[dict]:
    return [
        {
            "node": "plan-qa", "session_id": "s1", "generation": 1, "seq": 1,
            "ts": 1000.0, "backend": "acme-cli", "run_id": "R1", "flow": "main",
            "head": "aaa111",
        },
        {
            "node": "plan-qa", "session_id": "s2", "generation": 1, "seq": 2,
            "ts": 1100.0, "backend": "acme-cli", "run_id": "R1", "flow": "main",
            "head": "bbb222",
        },
    ]


def _span(run_dir: Path, run_id: str = "R1") -> None:
    store.insert_spans([{
        "span_id": "sp1", "trace_id": "tr1", "run_id": run_id, "workflow": "coder",
        "run_dir": str(run_dir), "start_ts": 1.0, "end_ts": 2.0,
    }])


# --------------------------------------------------------------------------- harvest
def test_each_visit_is_archived_separately():
    """Two laps of one node are two records, not one overwritten one — which is the
    whole reason the archive is keyed by the visit."""
    with _DB(), _workspace() as tmp:
        rows = _rows()
        run_dir = _run_dir(tmp, rows)
        for row in rows:
            _visit(run_dir, row, prompt=f"lap {row['seq']}")

        assert turns.harvest_run(run_dir, "R1", "coder") == 2

        indexed = store.query_turns(run="R1")
        assert [r["seq"] for r in indexed] == [1, 2]
        assert [r["session_id"] for r in indexed] == ["s1", "s2"]
        assert [r["head"] for r in indexed] == ["aaa111", "bbb222"]
        assert all(r["source"] == "store" for r in indexed)
        first = turns.record_path(indexed[0])
        assert (first / "prompt.md").read_text() == "lap 1"
        assert (first / "transcript.jsonl").is_file()
        assert (first / "output.json").is_file()


def test_a_tick_that_finds_nothing_new_copies_nothing():
    """Harvest runs while runs are live, so it sees the same record over and over. A
    record that has not changed must cost a digest and no copy; one that has grown must
    replace its row rather than duplicate it."""
    with _DB(), _workspace() as tmp:
        rows = _rows()[:1]
        run_dir = _run_dir(tmp, rows)
        _visit(run_dir, rows[0], transcript='{"a": 1}\n')

        assert turns.harvest_run(run_dir, "R1", "coder") == 1
        assert turns.harvest_run(run_dir, "R1", "coder") == 0

        _visit(run_dir, rows[0], transcript='{"a": 1}\n{"b": 2}\n')
        assert turns.harvest_run(run_dir, "R1", "coder") == 1

        indexed = store.query_turns(run="R1")
        assert len(indexed) == 1
        archived = turns.record_path(indexed[0]) / "transcript.jsonl"
        assert archived.read_text().count("\n") == 2


def test_a_turn_with_no_visit_key_is_not_archived():
    """An old session-map line names its node but not which visit it was. Archiving it
    under a guessed key would put two laps in one directory."""
    with _DB(), _workspace() as tmp:
        run_dir = _run_dir(tmp, [{"node": "plan-qa", "session_id": "s0"}])
        (run_dir / "transcripts" / "000-00000-plan-qa__s0.jsonl").write_text("{}\n")

        assert turns.harvest_run(run_dir, "R1", "coder") == 0
        assert store.query_turns(run="R1") == []


def test_scratch_runs_are_never_archived():
    """A suite that runs a workflow under a temp root writes real turn records. Making
    them durable would fill the archive with runs nobody will come back to."""
    with _DB(), _workspace() as tmp:
        rows = _rows()[:1]
        scratch = Path(tempfile.gettempdir()) / "pytest-of-nobody" / "run"
        run_dir = _run_dir(tmp, rows)
        _visit(run_dir, rows[0])
        store.insert_spans([{
            "span_id": "sp1", "trace_id": "tr1", "run_id": "R1", "workflow": "coder",
            "run_dir": str(scratch), "start_ts": 1.0, "end_ts": 2.0,
        }])

        assert turns.harvest() == 0
        assert store.query_turns(run="R1") == []


def test_a_run_dir_that_is_gone_is_not_an_error():
    """Most rows in `spans` name a directory this host no longer has. That is the normal
    state of the inventory, not a failure of the harvest."""
    with _DB():
        _span(Path("/nonexistent/run-dir"))
        assert turns.harvest() == 0


# -------------------------------------------------------------------------- backfill
def test_backfill_archives_from_the_cli_store():
    """The transcripts already on disk from before capture existed join to a node and a
    visit exactly, through the run's own session map."""
    from workhorse.runner import transcript as capture

    with _DB(), _workspace() as tmp:
        rows = _rows()[:1]
        run_dir = _run_dir(tmp, rows)  # no transcripts/ or turns/ content
        _span(run_dir)
        cli_store = tmp / "cli"
        cli_store.mkdir()
        (cli_store / "s1.jsonl").write_text('{"role": "user"}\n', encoding="utf-8")
        previous = capture._STORES.get("acme-cli")
        capture._STORES["acme-cli"] = lambda session: [cli_store / f"{session}.jsonl"]
        try:
            planned = turns.backfill(dry_run=True)
            assert [p["session_id"] for p in planned] == ["s1"]
            assert store.query_turns(run="R1") == []

            turns.backfill()
            indexed = store.query_turns(run="R1")
            assert [r["source"] for r in indexed] == ["store-backfill"]
            assert (turns.record_path(indexed[0]) / "transcript.jsonl").is_file()
        finally:
            if previous is None:
                capture._STORES.pop("acme-cli", None)
            else:
                capture._STORES["acme-cli"] = previous


# --------------------------------------------------------------------------- pruning
def test_the_archive_keeps_everything_by_default():
    """Retention is its own clock and its default is *keep*: a transcript is wanted
    precisely when someone returns to a run long after its spans aged out."""
    with _DB(), _workspace() as tmp:
        rows = _rows()[:1]
        run_dir = _run_dir(tmp, rows)
        _visit(run_dir, rows[0])
        turns.harvest_run(run_dir, "R1", "coder")

        assert turns.prune(retention_days=0, now=1e12) == 0
        assert len(store.query_turns(run="R1")) == 1

        assert turns.prune(retention_days=1, now=1000.0 + 3 * 86400) == 1
        assert store.query_turns(run="R1") == []
        assert not (turns.transcripts_root() / "R1" / "001-00001-plan-qa__s1").exists()


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
