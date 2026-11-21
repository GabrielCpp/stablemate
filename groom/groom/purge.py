"""Purge: every trace of a run that has been quiet longer than a cutoff, wherever groom keeps it."""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from groom import archive, attend_ledger, attend_transcript, dispatch_ledger, history, store, turns

DAY_S = 86400.0

TRASH_DIR = "purging"


@dataclass
class Footprint:
    """One run as groom holds it: the time of its latest record anywhere, and the folders that hold its files."""

    run_id: str
    last_ts: float = 0.0
    folders: list[Path] = field(default_factory=list)


@dataclass
class PurgeResult:
    """What one purge removed, or would remove under ``dry_run``."""

    cutoff: float
    dry_run: bool
    runs: list[str] = field(default_factory=list)
    kept: int = 0
    bytes: int = 0
    rows: int = 0
    summaries: int = 0
    attend_folders: int = 0
    attend_sessions: int = 0
    dispatch_items: int = 0
    failed: dict[str, str] = field(default_factory=dict)
    vacuumed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "cutoff": self.cutoff,
            "dry_run": self.dry_run,
            "runs": self.runs,
            "kept": self.kept,
            "bytes": self.bytes,
            "rows": self.rows,
            "summaries": self.summaries,
            "attend_folders": self.attend_folders,
            "attend_sessions": self.attend_sessions,
            "dispatch_items": self.dispatch_items,
            "failed": self.failed,
            "vacuumed": self.vacuumed,
        }


def trash_root() -> Path:
    """Where a purge moves folders before it deletes them, so no reader sees a half-deleted run."""
    return store.db_path().parent / TRASH_DIR


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return total


def _subdirs(root: Path) -> list[Path]:
    try:
        return sorted(entry for entry in root.iterdir() if entry.is_dir())
    except OSError:
        return []


def _run_folders() -> list[Path]:
    """The folders under the transcripts root that hold one run each: every one but the attendant's."""
    return [folder for folder in _subdirs(turns.transcripts_root()) if folder.name != attend_transcript.ATTEND_DIR]


def footprints() -> dict[str, Footprint]:
    """Every run groom holds anything of, with the latest time its records give. A transcript folder no record dates is as old as the folder."""
    found: dict[str, Footprint] = {}

    def seen(run_id: str, ts: float) -> Footprint:
        entry = found.setdefault(run_id, Footprint(run_id))
        entry.last_ts = max(entry.last_ts, ts)
        return entry

    for run in store.run_bounds().values():
        seen(run.run_id, run.max_ts)
    for run_id, ts in store.turn_last_seen().items():
        seen(run_id, ts)
    for run_id, ts in history.last_seen().items():
        seen(run_id, ts)
    for run_id, ts, folder in archive.frozen():
        seen(run_id, ts).folders.append(folder)
    for folder in _run_folders():
        known = found.get(folder.name)
        if known is None or not known.last_ts:
            known = seen(folder.name, _mtime(folder))
        known.folders.append(folder)
    return found


def _stale_attend_folders(cutoff: float) -> list[Path]:
    """The attendant's session folders untouched since ``cutoff``, except those a running attendance still names."""
    running = {session for row in attend_ledger.attend_orphans() for session in row["session_ids"]}
    return [
        folder
        for folder in _subdirs(attend_transcript.attend_root())
        if folder.name not in running and _mtime(folder) < cutoff
    ]


def _move_out(folder: Path) -> None:
    target = trash_root() / folder.parent.name / folder.name
    target.parent.mkdir(parents=True, exist_ok=True)
    os.rename(folder, target)


def purge(older_than_days: float, now: float | None = None, dry_run: bool = False, vacuum: bool = True) -> PurgeResult:
    """Delete every run whose latest record is older than ``older_than_days``: its archive and transcript folders, its telemetry and turn index rows, and its summary. Ended attendances and dispatch items older than the cutoff go with them."""
    stamp = now if now is not None else time.time()
    cutoff = stamp - older_than_days * DAY_S
    result = PurgeResult(cutoff=cutoff, dry_run=dry_run)
    prints = footprints()
    doomed = sorted((one for one in prints.values() if one.last_ts < cutoff), key=lambda one: (one.last_ts, one.run_id))
    result.kept = len(prints) - len(doomed)
    stale = _stale_attend_folders(cutoff)
    if not dry_run:
        shutil.rmtree(trash_root(), ignore_errors=True)
    for one in doomed:
        size = sum(_size(folder) for folder in one.folders)
        try:
            if not dry_run:
                for folder in one.folders:
                    _move_out(folder)
        except OSError as exc:
            result.failed[one.run_id] = str(exc)
            continue
        result.runs.append(one.run_id)
        result.bytes += size
    for folder in stale:
        size = _size(folder)
        try:
            if not dry_run:
                _move_out(folder)
        except OSError as exc:
            result.failed[f"{attend_transcript.ATTEND_DIR}/{folder.name}"] = str(exc)
            continue
        result.attend_folders += 1
        result.bytes += size
    if dry_run:
        result.attend_sessions = attend_ledger.attend_ended_before(cutoff)
        result.dispatch_items = dispatch_ledger.dispatch_ended_before(cutoff)
        return result
    result.rows = store.delete_runs(result.runs)
    result.summaries = history.forget(result.runs)
    result.attend_sessions = attend_ledger.attend_forget_ended(cutoff)
    result.dispatch_items = dispatch_ledger.dispatch_forget_ended(cutoff)
    shutil.rmtree(trash_root(), ignore_errors=True)
    store.checkpoint()
    if vacuum and (result.rows or result.summaries or result.attend_sessions or result.dispatch_items):
        store.vacuum()
        result.vacuumed = True
    return result
