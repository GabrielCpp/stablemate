"""Archival: the way telemetry gets *out* of ``groom.db``.

A run is in exactly one of two states.

**Live** — its telemetry is rows in ``groom.db`` and its transcript records are
being harvested into ``transcripts/<run_id>/`` on :mod:`groom.turns`' tick.

**Frozen** — its telemetry is one ``telemetry.jsonl`` file on disk, its transcript
records sit in the same directory, and nothing ever writes there again.

Archival is the transition, and it is a **move**::

    <groom data dir>/
      groom.db                              live runs only
      transcripts/<run_id>/                 live — the harvester's target
        <gen>-<seq>-<node>__<session>/
      archives/<run_id>/                    frozen — moved here wholesale
        <gen>-<seq>-<node>__<session>/
        telemetry.jsonl

Both roots resolve under ``store.db_path().parent``, so promoting a run is one
same-filesystem :func:`os.rename` of its directory rather than a per-file copy.
Two roots rather than one is also what makes immutability *structural*: the
harvester only ever knows ``transcripts/``, so "an archived run is never written
to again" is a property of the layout and not a check somebody has to remember.

Without this, ``GROOM_RETENTION_DAYS`` is a data-loss dial — the only way to keep
history is to let the database grow without bound. With it, the window says how
long a run stays *queryable in SQL*, and :func:`groom.store.prune` becomes
fail-closed: rows go only once they are on disk.

The archive has **no retention of its own**. Not a knob defaulting to
keep-everything — no knob, so there is no single environment variable that can
empty the tree that is now the record of truth.

Nothing here may raise into groom's tick. A run that cannot be archived is a run
that stays in SQL, which is a bigger database and not a broken groom.
"""

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

#: Seconds between archival sweeps. Its own clock, not folded into the rules tick:
#: a sweep is a large read plus a large delete, and it has no business running at
#: the cadence of an alert evaluation. Six hours — a run crosses the retention
#: window once, and being archived four hours later costs nobody anything.
ARCHIVE_EVERY_S = float(os.environ.get("GROOM_ARCHIVE_EVERY_S", str(6 * 3600)))

#: Runs archived per sweep. The first sweep against a store carrying a very large
#: window's backlog would otherwise run for hours against the database the
#: dashboard is reading. Bounded, oldest first, the backlog drains over a few
#: ticks while ``groom serve`` stays responsive.
RUNS_PER_PASS = int(os.environ.get("GROOM_ARCHIVE_RUNS_PER_PASS", "25"))

#: The one file archival adds to a run's directory.
TELEMETRY_FILE = "telemetry.jsonl"

#: Written first, renamed into place. A reader that finds this has found a sweep
#: that died, and the next one overwrites it.
_TMP_SUFFIX = ".tmp"


# ------------------------------------------------------------------- the two roots


def archives_root() -> Path:
    """Where frozen runs live. See :func:`groom.turns.archives_root`."""
    return turns.archives_root()


def archive_dirs() -> list[Path]:
    """Every frozen run directory, by name. A plain ``readdir``: the directory name
    *is* the run id, so the common listing opens no files at all."""
    root = archives_root()
    try:
        return sorted(entry for entry in root.iterdir() if entry.is_dir())
    except OSError:
        return []


def archived_run_ids() -> set[str]:
    """The run ids the disk says are frozen — what :func:`groom.store.prune` is
    allowed to delete. A stat, not a table: the database is authoritative for live
    runs, the filesystem for frozen ones, and neither describes the other."""
    return {path.name for path in archive_dirs() if (path / TELEMETRY_FILE).exists()}


def is_archived(run_id: str) -> bool:
    """Has ``run_id`` been frozen?"""
    return bool(run_id) and (archives_root() / run_id / TELEMETRY_FILE).exists()


def manifest(path: Path) -> dict[str, Any]:
    """The first line of a run's ``telemetry.jsonl``, or ``{}``.

    Deliberately reads one line: the manifest exists so a reader can learn what a
    file holds without parsing a gigabyte of it.
    """
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


# ---------------------------------------------------------------------- eligibility


def eligible(
    bounds: dict[str, RunBounds] | None = None,
    retention_days: float = store.RETENTION_DAYS,
    now: float | None = None,
) -> tuple[list[RunBounds], list[RunBounds]]:
    """``(archivable, held)`` — runs wholly past the window, and runs still emitting.

    A run is archivable when its *last* sign of life is past the cutoff. Liveness
    gauges count toward that even though they are never archived, precisely
    because a run still ticking has not finished even if no span of it has closed.

    A run whose first rows are expired but whose last are not is **held**: skipped
    whole, nothing archived and nothing pruned, so its rows accumulate. That is
    deliberate — a run alive at the retention window is a stuck run, and database
    growth is the symptom worth seeing rather than a condition to paper over.
    """
    stamp = now if now is not None else time.time()
    cutoff = stamp - retention_days * 86400
    runs = store.run_bounds() if bounds is None else bounds
    archivable: list[RunBounds] = []
    held: list[RunBounds] = []
    for run in runs.values():
        if store.is_scratch_run_dir(run.run_dir):
            # A mkdtemp run archived forever is exactly the junk `groom
            # purge-tests` exists to remove. Prune deletes these unarchived.
            continue
        if not run.max_ts or run.max_ts >= cutoff:
            if run.min_ts and run.min_ts < cutoff:
                held.append(run)
            continue
        if run.rows:
            # A run holding nothing but expired liveness gauges would archive to an
            # empty file. Prune's exemption is what clears those rows instead.
            archivable.append(run)
    archivable.sort(key=lambda run: run.max_ts)
    held.sort(key=lambda run: run.max_ts)
    return archivable, held


# --------------------------------------------------------------------- the records


def _attrs(row: dict[str, Any]) -> dict[str, Any]:
    try:
        loaded = json.loads(row.get("attrs_json") or "{}")
    except ValueError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _record(kind: str, row: dict[str, Any]) -> dict[str, Any]:
    """One archived line: the stored row, plus the keys that address a transcript.

    The file's whole point is that it sits beside the node-keyed transcript
    directories, so the join keys are normalized onto every line rather than left
    for each consumer to dig out of ``attrs_json``:

    * every record carries ``node``;
    * a **span** additionally carries ``generation`` and ``seq``, which together
      name the directory ``<gen>-<seq>-<node>__<session>`` outright;
    * a **log** carries ``node`` and ``ts`` only. It has no ``seq``, and
      ``trace_id`` is not a fallback — workhorse never makes its node spans
      current, so a log's trace id is zeroes by design
      (:func:`groom.otlp.parse_logs`). A log is placed inside a visit by node plus
      timestamp containment in that span's window;
    * a **metric** carries ``node`` when its attributes have one, since the
      ``metrics`` table has no column for it.

    Every other column is passed through under its own name, so the file does not
    have to be revised when the schema gains one. Empty and null columns are
    dropped: absent means empty, and on a table of a hundred thousand log rows
    that is most of the bytes.
    """
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
    """One signal's archivable rows for a run, oldest first, read a page at a time.

    Keyset-paginated by :func:`groom.store.archive_page` rather than held whole:
    the file is written streaming, and a run's logs alone can be hundreds of
    thousands of rows.
    """
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
    """A run's spans, logs and archivable metrics, merged in ``ts`` order.

    Each signal is already sorted by its own query, so this is a merge and not a
    sort — nothing is ever held in memory beyond one page per signal.
    """
    streams = [_stream(run_id, kind) for kind in ("span", "log", "metric")]
    for _ts, _rowid, record in heapq.merge(
        *streams, key=lambda item: (item[0], item[1])
    ):
        yield record


def _manifest_line(run: RunBounds, now: float) -> dict[str, Any]:
    """Line 1 of the file: what it holds, without reading the rest of it.

    Load-bearing twice over. It makes the file self-describing when it is read
    years later with no ``groom.db`` beside it, and it is what tells an
    interrupted sweep apart from a resumed run (:func:`_destination`).

    ``min_ts``/``max_ts`` are the *run's* bounds as SQL reports them — liveness
    gauges included — rather than the bounds of the lines below, precisely so the
    comparison against a still-live store is like for like.
    """
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
    """Write ``target`` — manifest first, then every record in ``ts`` order; bytes.

    Written to a temporary sibling, fsynced and renamed, so a reader never sees a
    partial file and a crash mid-write leaves the run in SQL rather than half on
    disk. The row counts come from :func:`groom.store.run_bounds` and are checked
    against what was actually written: they can only disagree if something wrote
    to a run that is supposed to be finished, and archiving that run would drop
    the difference on the floor.
    """
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
    """Persist a rename, not just the bytes it moved.

    A renamed file whose *directory* entry is still only in the page cache is
    gone after a power loss, which is the one failure this whole module exists to
    be robust against.
    """
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


# ----------------------------------------------------------------- the name clash


def derived_name(run: RunBounds) -> str:
    """``<run_id>-<8 hex>`` for a run id whose archive already exists.

    A resume opens fresh spans under the *same* ``run_id`` — that is what
    ``resume_generation`` is for — so a run archived, resumed and archived again
    collides with its own frozen self. Derived rather than random so the lineage
    is visible in a directory listing next to the original, and deterministic so a
    retry after a failed sweep picks the same name rather than littering.
    """
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
    """Where this run's directory is going, or ``None`` if it is already there.

    A crash between the move and the delete leaves a complete archive *and* live
    SQL rows — which from the outside is indistinguishable from a run that was
    resumed after being archived. Getting it wrong means archiving the same rows
    twice under a spurious id, so the manifest decides: if the existing archive's
    ``max_ts`` and row counts match what SQL still holds, that sweep was
    interrupted and there is nothing left to write. Otherwise it is a genuine
    second life and the run gets a derived name.
    """
    root = archives_root()
    for candidate in (root / run.run_id, root / derived_name(run)):
        if not candidate.exists():
            return candidate
        if _matches(manifest(candidate), run):
            return None
    # Both names are taken by archives that do not describe this run. Nothing
    # frozen is ever overwritten, so this run stays in SQL and stays visible.
    raise RuntimeError(f"archive names for {run.run_id} are taken by other archives")


# ---------------------------------------------------------------------- the sweep


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


#: The last completed sweep, for `groom archive status`. Process-local and not
#: persisted: it describes this `groom serve`, and the durable answer to "what is
#: archived" is the filesystem.
_LAST: SweepResult | None = None


def archive_run(run: RunBounds, now: float | None = None) -> tuple[Path | None, int]:
    """Freeze one run: write its telemetry, move its directory, drop its rows.

    ``(destination, rows deleted)`` — ``destination`` is ``None`` when an earlier
    sweep had already written the archive and only the delete was outstanding.

    The order is the whole design. Nothing is deleted before the archive is on
    disk and fsynced, so a crash at any step re-runs from SQL rather than losing
    rows; and the file is written under ``transcripts/`` and *moved*, so it lands
    in ``archives/`` in the same instant the records beside it do.
    """
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
    """One archival pass, bounded at ``limit`` runs, oldest first.

    One run's failure is that run's failure: it is recorded and the pass carries
    on, because a single unwritable archive must not stop every other run from
    leaving the database.
    """
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
    """What an operator needs to know, computed on demand.

    Deliberately separate from :class:`groom.store.StoreHealth`, which stays about
    live runs: no archival information is written while a run is alive, so there is
    nothing here for the live-ops view to carry.

    ``retention_days`` is forwarded to :func:`eligible` so the held-by-activity
    report reflects the same window the next sweep will use. Without it, status
    answers the question against the *configured* retention window — which may
    be 100 years (the default ``GROOM_RETENTION_DAYS`` on a fresh install) —
    while the sweep just ran with a 30-day window and held a run that status
    will not surface.
    """
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
