"""Archival: the way telemetry gets *out* of ``groom.db``."""

from __future__ import annotations

import hashlib
import heapq
import json
import logging
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from groom import store, turns
from groom.store import RunBounds

logger = logging.getLogger(__name__)

ARCHIVE_EVERY_S = float(os.environ.get("GROOM_ARCHIVE_EVERY_S", str(6 * 3600)))

RUNS_PER_PASS = int(os.environ.get("GROOM_ARCHIVE_RUNS_PER_PASS", "25"))

TELEMETRY_FILE = "telemetry.jsonl"

_TMP_SUFFIX = ".tmp"




def archives_root() -> Path:
    """Where frozen runs live."""
    return turns.archives_root()


def archive_dirs() -> list[Path]:
    """Every frozen run directory, by name."""
    root = archives_root()
    try:
        return sorted(entry for entry in root.iterdir() if entry.is_dir())
    except OSError:
        return []


def archived_run_ids() -> set[str]:
    """The run ids the disk says are frozen — what :func:`groom.store.prune` is allowed to delete."""
    return {path.name for path in archive_dirs() if (path / TELEMETRY_FILE).exists()}


def is_archived(run_id: str) -> bool:
    """Has ``run_id`` been frozen?"""
    return bool(run_id) and (archives_root() / run_id / TELEMETRY_FILE).exists()


def manifest(path: Path) -> dict[str, Any]:
    """The first line of a run's ``telemetry.jsonl``, or ``{}``."""
    target = path / TELEMETRY_FILE if path.is_dir() else path
    try:
        with target.open(encoding="utf-8") as handle:
            first = handle.readline()
    except OSError:
        return {}
    try:
        loaded = json.loads(first)
    except ValueError:
        return {}
    return loaded if isinstance(loaded, dict) else {}




def eligible(
    bounds: dict[str, RunBounds] | None = None,
    retention_days: float = store.RETENTION_DAYS,
    now: float | None = None,
) -> tuple[list[RunBounds], list[RunBounds]]:
    """``(archivable, held)`` — runs wholly past the window, and runs still emitting."""
    stamp = now if now is not None else time.time()
    cutoff = stamp - retention_days * 86400
    runs = store.run_bounds() if bounds is None else bounds
    archivable: list[RunBounds] = []
    held: list[RunBounds] = []
    for run in runs.values():
        if store.is_scratch_run_dir(run.run_dir):
            continue
        if not run.max_ts or run.max_ts >= cutoff:
            if run.min_ts and run.min_ts < cutoff:
                held.append(run)
            continue
        if run.rows:
            archivable.append(run)
    archivable.sort(key=lambda run: run.max_ts)
    held.sort(key=lambda run: run.max_ts)
    return archivable, held




def _attrs(row: dict[str, Any]) -> dict[str, Any]:
    try:
        loaded = json.loads(row.get("attrs_json") or "{}")
    except ValueError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _record(kind: str, row: dict[str, Any]) -> dict[str, Any]:
    """One archived line: the stored row, plus the keys that address a transcript."""
    attrs = _attrs(row)
    record: dict[str, Any] = {"kind": kind, "ts": row["_ts"]}
    for key, value in row.items():
        if key in ("_ts", "_rowid", "attrs_json") or value is None or value == "":
            continue
        record[key] = value
    if kind == "span":
        record["generation"] = row.get("resume_generation")
        record["seq"] = attrs.get("workhorse.seq")
        record.pop("resume_generation", None)
    if kind == "metric":
        node = attrs.get("node") or attrs.get("workhorse.node")
        if node:
            record["node"] = node
    record.setdefault("node", "")
    if attrs:
        record["attrs"] = attrs
    return {key: value for key, value in record.items() if value is not None}


def _stream(run_id: str, kind: str) -> Iterator[tuple[float, int, dict[str, Any]]]:
    """One signal's archivable rows for a run, oldest first, read a page at a time."""
    cursor = (0.0, 0)
    while True:
        page = store.archive_page(run_id, kind, cursor)
        if not page:
            return
        for row in page:
            yield float(row["_ts"]), int(row["_rowid"]), _record(kind, row)
        last = page[-1]
        cursor = (float(last["_ts"]), int(last["_rowid"]))


def records(run_id: str) -> Iterator[dict[str, Any]]:
    """A run's spans, logs and archivable metrics, merged in ``ts`` order."""
    streams = [_stream(run_id, kind) for kind in ("span", "log", "metric")]
    for _ts, _rowid, record in heapq.merge(
        *streams, key=lambda item: (item[0], item[1])
    ):
        yield record


def _manifest_line(run: RunBounds, now: float) -> dict[str, Any]:
    """Line 1 of the file: what it holds, without reading the rest of it."""
    return {
        "kind": "manifest",
        "run_id": run.run_id,
        "workflow": run.workflow,
        "repo": run.repo,
        "branch": run.branch,
        "archived_at": now,
        "min_ts": run.min_ts,
        "max_ts": run.max_ts,
        "rows": {"span": run.spans, "log": run.logs, "metric": run.metrics},
    }


def write_telemetry(run: RunBounds, target: Path, now: float | None = None) -> int:
    """Write ``target`` — manifest first, then every record in ``ts`` order; bytes."""
    stamp = now if now is not None else time.time()
    counts = {"span": 0, "log": 0, "metric": 0}
    tmp = target.with_name(target.name + _TMP_SUFFIX)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(_manifest_line(run, stamp)) + "\n")
        for record in records(run.run_id):
            counts[record["kind"]] += 1
            handle.write(json.dumps(record) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    written = {"span": run.spans, "log": run.logs, "metric": run.metrics}
    if counts != written:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"archive of {run.run_id} counted {counts} rows but its manifest claims"
            f" {written}; the run is still being written to"
        )
    tmp.replace(target)
    _fsync_dir(target.parent)
    return target.stat().st_size


def _fsync_dir(path: Path) -> None:
    """Persist a rename, not just the bytes it moved."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)




def derived_name(run: RunBounds) -> str:
    """``<run_id>-<8 hex>`` for a run id whose archive already exists."""
    token = hashlib.sha256(f"{run.run_id}:{run.max_ts!r}".encode()).hexdigest()[:8]
    return f"{run.run_id}-{token}"


def _matches(found: dict[str, Any], run: RunBounds) -> bool:
    """Does an existing archive hold exactly what SQL still holds for this run?"""
    rows = found.get("rows") or {}
    return (
        float(found.get("max_ts") or 0.0) == run.max_ts
        and int(rows.get("span") or 0) == run.spans
        and int(rows.get("log") or 0) == run.logs
        and int(rows.get("metric") or 0) == run.metrics
    )


def _destination(run: RunBounds) -> Path | None:
    """Where this run's directory is going, or ``None`` if it is already there."""
    root = archives_root()
    for candidate in (root / run.run_id, root / derived_name(run)):
        if not candidate.exists():
            return candidate
        if _matches(manifest(candidate), run):
            return None
    raise RuntimeError(f"archive names for {run.run_id} are taken by other archives")




@dataclass
class SweepResult:
    """What one pass did, for ``groom archive now`` and ``groom archive status``."""

    archived: list[str] = field(default_factory=list)
    resumed: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    held: list[str] = field(default_factory=list)
    pending: int = 0
    rows: int = 0
    bytes: int = 0
    started: float = 0.0
    finished: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "archived": self.archived,
            "resumed": self.resumed,
            "failed": self.failed,
            "held": self.held,
            "pending": self.pending,
            "rows": self.rows,
            "bytes": self.bytes,
            "started": self.started,
            "finished": self.finished,
        }


_LAST: SweepResult | None = None


def archive_run(run: RunBounds, now: float | None = None) -> tuple[Path | None, int]:
    """Freeze one run: write its telemetry, move its directory, drop its rows."""
    destination = _destination(run)
    if destination is not None:
        source = turns.transcripts_root() / run.run_id
        source.mkdir(parents=True, exist_ok=True)
        write_telemetry(run, source / TELEMETRY_FILE, now)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.rename(source, destination)
        _fsync_dir(destination.parent)
    return destination, store.delete_run_telemetry(run.run_id)


def sweep(
    limit: int = RUNS_PER_PASS,
    retention_days: float = store.RETENTION_DAYS,
    now: float | None = None,
    dry_run: bool = False,
) -> SweepResult:
    """One archival pass, bounded at ``limit`` runs, oldest first."""
    global _LAST  # noqa: PLW0603 - one process-local "last sweep", read by `archive status`
    stamp = now if now is not None else time.time()
    result = SweepResult(started=stamp)
    archivable, held = eligible(retention_days=retention_days, now=stamp)
    result.pending = len(archivable)
    result.held = [run.run_id for run in held]
    for run in archivable[:limit]:
        if dry_run:
            result.archived.append(run.run_id)
            result.rows += run.rows
            continue
        try:
            destination, removed = archive_run(run, stamp)
        except (OSError, RuntimeError) as exc:
            logger.warning("groom: archiving run %s failed: %s", run.run_id, exc)
            result.failed[run.run_id] = str(exc)
            continue
        result.rows += removed
        if destination is None:
            result.resumed.append(run.run_id)
            continue
        result.archived.append(destination.name)
        with_size = destination / TELEMETRY_FILE
        try:
            result.bytes += with_size.stat().st_size
        except OSError:
            pass
    result.finished = time.time()
    if not dry_run:
        _LAST = result
    return result


def status(
    now: float | None = None,
    retention_days: float = store.RETENTION_DAYS,
) -> dict[str, Any]:
    """What an operator needs to know, computed on demand."""
    archivable, held = eligible(retention_days=retention_days, now=now)
    return {
        "root": str(archives_root()),
        "archived_runs": len(archive_dirs()),
        "pending": len(archivable),
        "held_by_activity": [run.run_id for run in held],
        "every_s": ARCHIVE_EVERY_S,
        "runs_per_pass": RUNS_PER_PASS,
        "retention_days": retention_days,
        "last_sweep": _LAST.as_dict() if _LAST else None,
        "unarchived_deletable": store.unarchived_row_counts(),
    }
