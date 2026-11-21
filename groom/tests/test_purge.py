"""Purge: a run quiet past the cutoff leaves every place groom keeps it, and a run with one recent record keeps all of them."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from test_history import seed
from test_run_clock import _DB

from groom import archive, attend_ledger, attend_transcript, cli, dispatch_ledger, history, purge, store, turns

DAY = 86400.0
NOW = time.time()
OLD = NOW - 60 * DAY
RECENT = NOW - 1 * DAY


def _turn(run: str, base: float) -> Path:
    """One harvested turn record: its folder under the run's transcripts and its index row."""
    slug = "1-00001-dev__sess"
    folder = turns.transcripts_root() / run / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "prompt.md").write_text("do the work\n" * 100, encoding="utf-8")
    store.insert_turns([
        {"run_id": run, "workflow": "coder", "node": "dev", "session_id": f"{run}-sess", "generation": 1, "seq": 1, "ts": base + 10, "path": f"{run}/{slug}", "bytes": 1200, "sha256": "ab"}
    ])
    return folder


def _live(run: str, base: float) -> None:
    seed(run, base)
    _turn(run, base)


def _archived(run: str, base: float) -> Path:
    _live(run, base)
    destination, _ = archive.archive_run(store.run_bounds()[run], NOW)
    assert destination is not None
    return destination


def _held(run: str) -> dict[str, bool]:
    """Where groom still holds anything of ``run``."""
    return {
        "telemetry": store.has_run_rows(run),
        "turns": bool(store.query_turns(run=run)),
        "summary": history.stored(run) is not None,
        "archive": any(run_id == run for run_id, _ts, _folder in archive.frozen()),
        "transcripts": (turns.transcripts_root() / run).exists(),
    }


NOWHERE = {"telemetry": False, "turns": False, "summary": False, "archive": False, "transcripts": False}


def _aged(folder: Path, ts: float) -> None:
    os.utime(folder, (ts, ts))


def test_an_archived_run_quiet_past_the_cutoff_leaves_every_place_groom_keeps_it() -> None:
    with _DB():
        folder = _archived("R1", OLD)
        assert folder.stat().st_mtime > NOW - DAY
        result = purge.purge(30, now=NOW)
        assert result.runs == ["R1"]
        assert _held("R1") == NOWHERE
        assert not folder.exists()
        assert "R1" not in {item["run_id"] for item in history.listing(set(), now=NOW, archives=True)["runs"]}


def test_a_run_the_store_still_holds_is_purged_without_being_archived_first() -> None:
    with _DB():
        _live("R1", OLD)
        assert _held("R1")["telemetry"] and _held("R1")["transcripts"]
        result = purge.purge(30, now=NOW)
        assert result.runs == ["R1"]
        assert result.rows > 0
        assert _held("R1") == NOWHERE


def test_a_run_with_one_record_inside_the_window_keeps_its_old_archive_and_everything_else() -> None:
    with _DB():
        _archived("R1", OLD)
        _live("R1", RECENT)
        _live("R2", OLD)
        store.insert_logs([{"run_id": "R2", "ts": RECENT, "severity": "INFO", "body": "still here", "node": "dev"}])
        before = _held("R1")
        result = purge.purge(30, now=NOW)
        assert result.runs == []
        assert result.kept == 2
        assert _held("R1") == before
        assert _held("R2")["telemetry"] and _held("R2")["transcripts"]


def test_a_transcript_folder_nothing_else_knows_goes_by_its_own_age_and_the_attendant_folder_is_never_a_run() -> None:
    with _DB():
        stale = turns.transcripts_root() / "orphan-old"
        fresh = turns.transcripts_root() / "orphan-new"
        for folder in (stale, fresh):
            (folder / "1-00001-dev__s").mkdir(parents=True)
        _aged(stale, OLD)
        attend_transcript.attend_root().mkdir(parents=True)
        _aged(attend_transcript.attend_root(), OLD)
        result = purge.purge(30, now=NOW)
        assert result.runs == ["orphan-old"]
        assert not stale.exists()
        assert fresh.exists()
        assert attend_transcript.attend_root().exists()


def test_a_run_whose_turn_rows_carry_no_time_goes_by_the_age_of_its_transcript_folder() -> None:
    with _DB():
        for run in ("undated-old", "undated-new"):
            folder = _turn(run, 0.0).parent
            store.insert_turns([{**store.query_turns(run=run)[0], "ts": 0.0}])
        _aged(turns.transcripts_root() / "undated-old", OLD)
        result = purge.purge(30, now=NOW)
        assert result.runs == ["undated-old"]
        assert _held("undated-old") == NOWHERE
        assert folder.exists()


def test_attendances_and_dispatch_items_that_ended_before_the_cutoff_go_and_running_ones_stay() -> None:
    with _DB():
        attend_ledger.attend_start("ended", run_id="R9", session_id="s-ended", started_at=OLD)
        attend_ledger.attend_finish("ended", exit_code=0, ended_at=OLD + 60)
        attend_ledger.attend_start("running", run_id="R9", session_id="s-running", started_at=OLD)
        for session in ("s-ended", "s-running"):
            folder = attend_transcript.session_dir(session)
            folder.mkdir(parents=True)
            _aged(folder, OLD)
        dispatch_ledger.dispatch_enqueue("done-old", queue="q", command="c", enqueued_at=OLD)
        dispatch_ledger.dispatch_finish("done-old", status="done", exit_code=0, ended_at=OLD + 60)
        dispatch_ledger.dispatch_enqueue("pending", queue="q", command="c", enqueued_at=OLD)
        result = purge.purge(30, now=NOW)
        assert (result.attend_sessions, result.attend_folders, result.dispatch_items) == (1, 1, 1)
        assert attend_ledger.attend_get("ended") is None
        assert attend_ledger.attend_get("running") is not None
        assert not attend_transcript.session_dir("s-ended").exists()
        assert attend_transcript.session_dir("s-running").exists()
        assert dispatch_ledger.dispatch_get("done-old") is None
        assert dispatch_ledger.dispatch_get("pending") is not None


def test_a_dry_run_reports_what_the_purge_then_removes_and_deletes_nothing() -> None:
    with _DB():
        _archived("R1", OLD)
        _live("R2", OLD)
        _live("R3", RECENT)
        before = {run: _held(run) for run in ("R1", "R2", "R3")}
        dry = purge.purge(30, now=NOW, dry_run=True)
        assert {run: _held(run) for run in ("R1", "R2", "R3")} == before
        assert sorted(dry.runs) == ["R1", "R2"]
        assert dry.bytes > 0
        done = purge.purge(30, now=NOW)
        assert sorted(done.runs) == sorted(dry.runs)
        assert done.bytes == dry.bytes
        assert _held("R3") == before["R3"]


def test_a_folder_an_interrupted_purge_left_in_the_trash_is_deleted_by_the_next_one() -> None:
    with _DB():
        left = purge.trash_root() / "archives" / "R0"
        left.mkdir(parents=True)
        (left / archive.TELEMETRY_FILE).write_text("{}\n", encoding="utf-8")
        purge.purge(30, now=NOW)
        assert not purge.trash_root().exists()


def test_the_command_prints_what_a_dry_run_would_purge(capsys: pytest.CaptureFixture[str]) -> None:
    with _DB():
        _live("R1", OLD)
        cli.main(["purge", "--older-than", "30", "--dry-run"])
        out = capsys.readouterr().out
        assert "would purge 1 run(s)" in out
        assert "  R1\n" in out
        assert store.has_run_rows("R1")


@pytest.mark.parametrize("days", ["0", "-3", "thirty"])
def test_the_command_refuses_an_age_that_is_not_a_positive_number_of_days(days: str) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["purge", "--older-than", days])
    assert stopped.value.code == 2
