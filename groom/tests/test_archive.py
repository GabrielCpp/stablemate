"""Archival: telemetry leaving SQLite for a file, and prune's refusal to delete
anything that has not gone.

What is asserted here is the order of the three steps — write, move, delete —
and what each failure between them leaves behind. The file layout is asserted
only where a reader depends on it: one JSONL per run, a manifest on line 1, and
records ordered by timestamp carrying the keys a transcript joins on.

Run: uv run pytest tests/test_archive.py
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from groom import archive, store, turns

DAY = 86400.0
NOW = 100 * DAY
OLD = NOW - 60 * DAY


class _DB:
    """A throwaway groom.db in its own directory, so both roots are temporary.

    ``transcripts/`` and ``archives/`` are derived from the database's parent, so
    pointing ``$GROOM_DB`` at a temp directory moves the whole feature into it.
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


def _seed(
    run_id: str = "R1",
    ts: float = OLD,
    node: str = "plan",
    run_dir: str = "/home/me/repo/.agents/runs/R1",
) -> None:
    """One run's worth of every signal: a span, a log, a kept metric, a dropped one."""
    store.insert_spans([
        {
            "run_id": run_id,
            "span_id": f"{abs(hash((run_id, ts))) % (2**63):016x}",
            "trace_id": "aa" * 16,
            "name": f"node:{node}",
            "node": node,
            "start_ts": ts,
            "end_ts": ts + 5,
            "status": "ok",
            "workflow": "coder",
            "repo": "example-org/api-service",
            "branch": "main",
            "run_dir": run_dir,
            "attrs": {"workhorse.seq": 3},
            "resume_generation": 1,
        }
    ])
    store.insert_logs([
        {
            "run_id": run_id,
            "ts": ts + 1,
            "severity": "INFO",
            "body": "hello",
            "node": node,
            "workflow": "coder",
            "run_dir": run_dir,
        }
    ])
    store.insert_metrics([
        {
            "run_id": run_id, "name": "workhorse.gas", "ts": ts + 2, "value": 7.0,
            "attrs": {"workhorse.node": node},
        },
        {
            "run_id": run_id, "name": "workhorse.turn.idle_s", "ts": ts + 2, "value": 42.0,
            "attrs": {"workhorse.node": node},
        },
    ])


def _live_dir(run_id: str = "R1") -> Path:
    path = turns.transcripts_root() / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


# --------------------------------------------------------------------------- #
# eligibility
# --------------------------------------------------------------------------- #
def test_a_run_still_emitting_is_held_whole_rather_than_half_archived():
    """A run whose oldest rows have expired but which is still writing would be
    archived with a hole in it: the file would end at the cutoff and the rows
    after it would have nowhere to go. Straddling runs are skipped entirely."""
    with _DB():
        _seed("straddler", ts=OLD)
        _seed("straddler", ts=NOW - 60, node="build")
        _seed("finished", ts=OLD)
        archivable, held = archive.eligible(retention_days=30, now=NOW)
        assert [run.run_id for run in archivable] == ["finished"]
        assert [run.run_id for run in held] == ["straddler"]


def test_scratch_runs_are_never_archived():
    """A suite's mkdtemp run dir is junk by construction; prune deletes it
    without an archive, so archiving it forever would be the bug."""
    with _DB():
        _seed("scratch", ts=OLD, run_dir=str(Path(tempfile.gettempdir()) / "tmpabcdef" / "runs"))
        archivable, held = archive.eligible(retention_days=30, now=NOW)
        assert archivable == [] and held == []


# --------------------------------------------------------------------------- #
# the file
# --------------------------------------------------------------------------- #
def test_one_file_per_run_manifest_first_then_records_in_timestamp_order():
    with _DB():
        _seed()
        _live_dir()
        archive.sweep(retention_days=30, now=NOW)

        target = archive.archives_root() / "R1" / archive.TELEMETRY_FILE
        lines = _read(target)
        manifest, records = lines[0], lines[1:]
        assert manifest["kind"] == "manifest"
        assert manifest["run_id"] == "R1"
        assert manifest["workflow"] == "coder"
        assert manifest["rows"] == {"span": 1, "log": 1, "metric": 1}
        assert [record["kind"] for record in records] == ["span", "log", "metric"]
        assert [record["ts"] for record in records] == sorted(r["ts"] for r in records)


def test_every_record_carries_the_keys_a_transcript_joins_on():
    """The point of the file is that it sits beside the transcripts and shares
    their index: run, node, and for a span the visit's generation and seq."""
    with _DB():
        _seed()
        _live_dir()
        archive.sweep(retention_days=30, now=NOW)

        records = _read(archive.archives_root() / "R1" / archive.TELEMETRY_FILE)[1:]
        assert all(record["run_id"] == "R1" for record in records)
        assert all(record["node"] == "plan" for record in records)
        span = next(record for record in records if record["kind"] == "span")
        assert span["generation"] == 1 and span["seq"] == 3


def test_the_liveness_and_activity_gauges_never_reach_the_file():
    """They describe where a live groom thinks a run is. Once it is over they
    are noise, and they were most of the metrics table."""
    with _DB():
        _seed()
        _live_dir()
        archive.sweep(retention_days=30, now=NOW)

        records = _read(archive.archives_root() / "R1" / archive.TELEMETRY_FILE)[1:]
        names = {record.get("name") for record in records}
        assert "workhorse.gas" in names
        assert "workhorse.turn.idle_s" not in names


# --------------------------------------------------------------------------- #
# write, move, delete — in that order
# --------------------------------------------------------------------------- #
def test_archival_moves_the_live_directory_and_only_then_deletes_the_rows():
    with _DB():
        _seed()
        live = _live_dir()
        (live / "001-00003-plan__s1").mkdir()

        result = archive.sweep(retention_days=30, now=NOW)
        assert result.archived == ["R1"]
        assert not live.exists()
        frozen = archive.archives_root() / "R1"
        assert (frozen / "001-00003-plan__s1").is_dir()
        assert (frozen / archive.TELEMETRY_FILE).is_file()
        assert store.query_spans(run="R1") == []
        assert store.query_logs(run="R1") == []


def test_a_write_that_fails_leaves_the_run_in_the_database(monkeypatch: pytest.MonkeyPatch):
    """Fail-closed is the whole contract: the delete is reachable only through a
    successful write and a successful move, so a broken archiver costs disk,
    never data."""
    with _DB():
        _seed()
        _live_dir()
        def _disk_full(
            run: store.RunBounds, target: Path, now: int | float | None = None
        ) -> int:
            raise OSError("disk full")

        monkeypatch.setattr(archive, "write_telemetry", _disk_full)
        result = archive.sweep(retention_days=30, now=NOW)
        assert result.archived == []
        assert "R1" in result.failed
        assert len(store.query_spans(run="R1")) == 1


def test_an_interrupted_sweep_finishes_instead_of_rewriting_or_colliding():
    """Crash between the move and the delete: the file and the directory are in
    place and the rows are still there. The next pass must recognise its own
    work by the manifest and just finish the delete."""
    with _DB():
        _seed()
        _live_dir()
        run = store.run_bounds()["R1"]
        frozen = archive.archives_root() / "R1"
        frozen.mkdir(parents=True)
        archive.write_telemetry(run, frozen / archive.TELEMETRY_FILE, now=NOW)
        written = (frozen / archive.TELEMETRY_FILE).read_bytes()

        result = archive.sweep(retention_days=30, now=NOW)
        assert result.resumed == ["R1"]
        assert (frozen / archive.TELEMETRY_FILE).read_bytes() == written
        assert store.query_spans(run="R1") == []


def test_a_frozen_run_is_never_overwritten_by_a_later_run_of_the_same_name():
    """An archived run is read-only forever. A second run that reused the id is
    archived under a derived name rather than merged into the first."""
    with _DB():
        _seed("R1", ts=OLD)
        _live_dir()
        archive.sweep(retention_days=30, now=NOW)
        first = (archive.archives_root() / "R1" / archive.TELEMETRY_FILE).read_bytes()

        _seed("R1", ts=OLD + DAY, node="build")
        _live_dir()
        result = archive.sweep(retention_days=30, now=NOW)

        assert (archive.archives_root() / "R1" / archive.TELEMETRY_FILE).read_bytes() == first
        assert result.archived and result.archived != ["R1"]
        derived = archive.archives_root() / result.archived[0]
        assert derived.name.startswith("R1-")
        records = _read(derived / archive.TELEMETRY_FILE)[1:]
        assert {record["node"] for record in records} == {"build"}


def test_a_bounded_pass_takes_the_oldest_runs_and_reports_the_rest_pending():
    """A first sweep over a year of backlog must not hold the writer for an
    hour, so the pass is bounded and the remainder is simply next time's work."""
    with _DB():
        for index in range(4):
            _seed(f"R{index}", ts=OLD + index * DAY)
            _live_dir(f"R{index}")
        result = archive.sweep(limit=2, retention_days=30, now=NOW)
        assert result.archived == ["R0", "R1"]
        assert result.pending == 4


def test_a_dry_run_writes_nothing_and_deletes_nothing():
    with _DB():
        _seed()
        _live_dir()
        result = archive.sweep(retention_days=30, now=NOW, dry_run=True)
        assert result.archived == ["R1"]
        assert not archive.archives_root().exists()
        assert len(store.query_spans(run="R1")) == 1


# --------------------------------------------------------------------------- #
# prune is fail-closed on the archive
# --------------------------------------------------------------------------- #
def test_prune_refuses_to_delete_a_run_no_archive_holds():
    """Retention used to be a data-loss dial, which is why it had to be set to a
    year. It is a database-size dial now: age alone authorises nothing."""
    with _DB():
        _seed()
        removed = store.prune(retention_days=30, now=NOW)
        assert len(store.query_spans(run="R1")) == 1
        assert len(store.query_logs(run="R1")) == 1
        # The activity gauge is never archived, so it goes on age alone.
        assert removed == 1


def test_prune_deletes_exactly_the_runs_the_archive_reports():
    with _DB():
        _seed("kept", ts=OLD)
        _seed("frozen", ts=OLD)
        store.prune(retention_days=30, now=NOW, archived={"frozen"})
        assert store.query_spans(run="frozen") == []
        assert len(store.query_spans(run="kept")) == 1


def test_prune_deletes_a_scratch_run_without_an_archive_behind_it():
    with _DB():
        _seed("scratch", ts=OLD, run_dir=str(Path(tempfile.gettempdir()) / "tmpabcdef" / "runs"))
        store.prune(retention_days=30, now=NOW)
        assert store.query_spans(run="scratch") == []


def test_prune_leaves_a_run_inside_the_window_alone_even_when_archived():
    """`archived` says a run *may* go, not that it must: the age test still
    decides, so a run archived early is not deleted early."""
    with _DB():
        _seed("recent", ts=NOW - DAY)
        store.prune(retention_days=30, now=NOW, archived={"recent"})
        assert len(store.query_spans(run="recent")) == 1


# --------------------------------------------------------------------------- #
# reading it back
# --------------------------------------------------------------------------- #
def test_what_is_archived_is_read_from_the_directory_not_an_index():
    """There is no index table, deliberately: a second source of truth about
    what is on disk is a second thing that can be wrong."""
    with _DB():
        _seed()
        _live_dir()
        archive.sweep(retention_days=30, now=NOW)
        assert archive.archived_run_ids() == {"R1"}
        assert archive.is_archived("R1")
        assert archive.manifest(archive.archives_root() / "R1")["run_id"] == "R1"


def test_status_reports_the_backlog_and_what_is_held():
    with _DB():
        _seed("frozen", ts=OLD)
        _live_dir("frozen")
        archive.sweep(retention_days=30, now=NOW)
        _seed("straddler", ts=OLD)
        _seed("straddler", ts=NOW - 60, node="build")

        report = archive.status(now=NOW)
        assert report["archived_runs"] == 1
        assert report["held_by_activity"] == ["straddler"]
        assert report["last_sweep"]["archived"] == ["frozen"]


def test_a_transcript_record_resolves_under_either_root():
    """The index row still says ``<run_id>/`` after archival, because the move
    is the only thing that happened. Resolution has to span both roots or every
    archived run's transcripts read as missing."""
    with _DB():
        _seed()
        live = _live_dir()
        (live / "001-00003-plan__s1").mkdir()
        archive.sweep(retention_days=30, now=NOW)

        resolved = turns.record_path({"run_id": "R1", "path": "R1/001-00003-plan__s1"})
        assert resolved == archive.archives_root() / "R1" / "001-00003-plan__s1"
        assert resolved.is_dir()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
