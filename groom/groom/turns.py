"""The durable archive of turn records, and the harvester that fills it.

A run directory is where a turn record is *written*; it is not where it lives. Run dirs
are pruned, moved, live inside a container, or belong to a machine that is not this one —
so the transcript of the turn that explains a livelock is exactly the artifact most
likely to be gone by the time anyone goes looking. groom already keeps the durable
cross-run index beside its own database, and this is the same tree for bodies:

``<groom data dir>/transcripts/<run_id>/<gen>-<seq>-<node>__<session>/``

holding, for that one visit, the transcript the runner captured, the ``prompt.md`` that
provoked it and the ``output.json`` it answered with. Run-major so a run can be dropped
in one ``rm -rf``; keyed by the visit so a node visited five times is five directories
rather than one overwritten one.

The archive is **additive and idempotent**. Harvest runs on a tick while runs are live,
so it sees the same record many times: a record whose bytes have not changed is skipped
on its digest, and one that has grown is re-copied and its index row replaced. Nothing
here deletes anything a run wrote.

Retention is deliberately its own clock (``GROOM_TRANSCRIPT_RETENTION_DAYS``, default
*keep everything*) rather than the span window: a transcript is wanted precisely when
someone comes back to a run long after its telemetry has aged out.

Nothing here may raise into groom's tick. A record that cannot be copied is a record that
is not archived, which is a poorer archive and not a broken groom.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

from workhorse.runner import transcript as capture
from workhorse.turnkey import VisitKey

from groom import store

logger = logging.getLogger(__name__)

#: Days of archived turn records to keep. ``0`` — the default — keeps everything: the
#: archive is small next to what it explains, and the whole reason it exists is that the
#: evidence outlives the run that produced it.
RETENTION_DAYS = float(os.environ.get("GROOM_TRANSCRIPT_RETENTION_DAYS", "0"))

#: Ceiling on one archived record. The runner already caps what it writes; this bounds
#: the *backfill* path too, which copies out of a CLI's own store and so has never been
#: through that cap.
MAX_RECORD_BYTES = int(os.environ.get("GROOM_TRANSCRIPT_MAX_BYTES", str(64 * 1024 * 1024)))

#: Subdirectory of a run dir holding what the capture layer wrote.
RUN_TRANSCRIPTS = capture.TRANSCRIPTS_DIR
#: Subdirectory of a run dir holding each visit's rendered prompt and parsed output.
RUN_TURNS = "turns"
#: What a run's per-turn session map is called.
SESSION_MAP = "sessions.jsonl"


def transcripts_root() -> Path:
    """Where archived records live — beside ``groom.db``, wherever that is.

    Derived from :func:`groom.store.db_path` rather than from the platform data dir
    directly, so a test (or an operator) that points ``$GROOM_DB`` somewhere else moves
    the bodies with the index instead of writing them into the real archive.
    """
    return store.db_path().parent / "transcripts"


# ------------------------------------------------------------------------ discovery


def _session_rows(run_dir: Path) -> list[dict[str, Any]]:
    """The run's per-turn session map, one dict per turn, unparseable lines dropped.

    Every key past ``node``/``session_id`` is optional: the map predates the visit key,
    and a run recorded by an older engine still has to read.
    """
    rows: list[dict[str, Any]] = []
    try:
        text = (run_dir / SESSION_MAP).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("session_id"):
            rows.append(row)
    return rows


def _slug(row: dict[str, Any]) -> str | None:
    """This turn's visit key, or None when the row is too old to have one.

    A row without a generation and a seq cannot be told apart from the other visits to
    its node, and archiving it under a name it does not own would put two laps in one
    directory. Better absent than wrong.
    """
    generation, seq = row.get("generation"), row.get("seq")
    if not isinstance(generation, int) or not isinstance(seq, int):
        return None
    return VisitKey(generation, seq, str(row.get("node", ""))).slug


def _sources(run_dir: Path, slug: str, session_id: str) -> list[tuple[str, Path]]:
    """The files this visit contributed, as (name in the record, path in the run dir).

    Named rather than copied wholesale so a consumer reads one layout regardless of
    which capture source produced the transcript — and so ``source`` in the index, not
    a filename, is what says which one it was.
    """
    stem = run_dir / RUN_TRANSCRIPTS / f"{slug}__{session_id}"
    found: list[tuple[str, Path]] = []
    for name, path in (
        ("transcript.jsonl", Path(f"{stem}.jsonl")),
        ("transcript.jsonl", Path(f"{stem}.tee.jsonl")),
        ("sidechains", Path(f"{stem}.d")),
        ("capture.json", Path(f"{stem}.meta.json")),
    ):
        if path.exists():
            found.append((name, path))
    visit = run_dir / RUN_TURNS / slug
    for name in ("prompt.md", "output.json", "context_after.json"):
        if (visit / name).is_file():
            found.append((name, visit / name))
    return found


def _capture_source(run_dir: Path, slug: str, session_id: str) -> str:
    """What the capture layer said it was — ``store``, ``tee``, or empty when it is gone.

    Read from the sidecar meta rather than inferred from the filename, because a
    consumer that has to guess what it is holding will guess wrong about the turn that
    matters.
    """
    meta = run_dir / RUN_TRANSCRIPTS / f"{slug}__{session_id}.meta.json"
    try:
        loaded = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(loaded.get("source", "")) if isinstance(loaded, dict) else ""


# -------------------------------------------------------------------------- copying


def _digest_of(sources: list[tuple[str, Path]]) -> tuple[str, int]:
    """A content digest over the whole record, and its size in bytes.

    Over every file rather than the transcript alone: a record whose prompt arrives on
    one tick and whose transcript grows on the next has changed both times, and a digest
    that only watched one of them would skip the other.
    """
    sha = hashlib.sha256()
    total = 0
    for name, path in sources:
        for member in _members(name, path):
            sha.update(member[0].encode())
            try:
                with member[1].open("rb") as fh:
                    while chunk := fh.read(1 << 20):
                        sha.update(chunk)
                        total += len(chunk)
            except OSError:
                continue
    return sha.hexdigest(), total


def _members(name: str, path: Path) -> list[tuple[str, Path]]:
    """Flatten a source into (record-relative name, file) pairs; a dir yields its tree."""
    if path.is_dir():
        return [
            (f"{name}/{p.relative_to(path).as_posix()}", p)
            for p in sorted(path.rglob("*"))
            if p.is_file()
        ]
    return [(name, path)] if path.is_file() else []


def _copy_record(sources: list[tuple[str, Path]], target: Path) -> int:
    """Materialize one record under ``target``; bytes written.

    Rewritten from empty each time rather than merged into what is there, so a record
    that shrank — a re-run that captured less — does not leave the older, longer file
    beside the newer one pretending to be part of the same turn.
    """
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)
    written = 0
    for name, path in sources:
        for member, src in _members(name, path):
            if written >= MAX_RECORD_BYTES:
                return written
            dst = target / member
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copyfile(src, dst)
                written += dst.stat().st_size
            except OSError:
                logger.debug("turn record member unreadable: %s", src)
    return written


# ------------------------------------------------------------------------- harvest


def _indexed(run_id: str) -> dict[tuple[Any, Any, str], str]:
    """What is already archived for this run: visit key → digest."""
    return {
        (row["generation"], row["seq"], row["session_id"]): row["sha256"]
        for row in store.query_turns(run=run_id, limit=100_000)
    }


def harvest_run(run_dir: Path, run_id: str = "", workflow: str = "") -> int:
    """Archive every turn record this run dir holds that is not already archived.

    Returns the number of records copied — zero on a run that has not moved since the
    last tick, which is the common case and the reason the digest check comes before any
    copying.
    """
    rows = _session_rows(run_dir)
    if not rows:
        return 0
    run = run_id or str(rows[0].get("run_id", "")) or run_dir.name
    known = _indexed(run)
    root = transcripts_root()
    archived: list[dict[str, Any]] = []
    for row in rows:
        slug = _slug(row)
        if slug is None:
            continue
        session_id = str(row["session_id"])
        sources = _sources(run_dir, slug, session_id)
        if not sources:
            continue
        digest, _ = _digest_of(sources)
        key = (row.get("generation"), row.get("seq"), session_id)
        if known.get(key) == digest:
            continue
        target = root / run / f"{slug}__{session_id}"
        try:
            written = _copy_record(sources, target)
        except OSError:
            logger.debug("turn record not archived: %s", target)
            continue
        archived.append(
            {
                "run_id": run,
                "workflow": workflow or str(row.get("workflow", "")),
                "flow": str(row.get("flow", "")),
                "node": str(row.get("node", "")),
                "session_id": session_id,
                "generation": row.get("generation"),
                "seq": row.get("seq"),
                "ts": row.get("ts") or 0.0,
                "backend": str(row.get("backend", "")),
                "source": _capture_source(run_dir, slug, session_id),
                "path": str(target.relative_to(root)),
                "bytes": written,
                "sha256": digest,
                "head": row.get("head"),
            }
        )
    return store.insert_turns(archived)


def known_runs() -> list[tuple[str, Path, str]]:
    """Every run telemetry has seen a directory for: (run_id, run_dir, workflow).

    Scratch and test run dirs are excluded — a suite that runs a workflow under
    ``tempfile.mkdtemp`` produces real turn records, and archiving them durably would
    fill the archive with runs nobody will ever come back to.
    """
    found: list[tuple[str, Path, str]] = []
    for row in store.run_directories():
        run_dir = str(row["run_dir"])
        if store.is_scratch_run_dir(run_dir):
            continue
        found.append((str(row["run_id"]), Path(run_dir), str(row["workflow"] or "")))
    return found


def harvest() -> int:
    """Harvest every known run dir that still exists on this host; records copied.

    A run dir that is gone — pruned, or belonging to a container whose records arrive by
    another path — is skipped silently. Its absence is not an error here; it is the
    normal state of most of the rows in ``spans``.
    """
    copied = 0
    for run_id, run_dir, workflow in known_runs():
        if not run_dir.is_dir():
            continue
        try:
            copied += harvest_run(run_dir, run_id, workflow)
        except (OSError, ValueError):
            logger.debug("harvest skipped run %s", run_id, exc_info=True)
    return copied


# ------------------------------------------------------------------------ backfill


def backfill(dry_run: bool = False) -> list[dict[str, Any]]:
    """Archive turns whose transcript never reached the run dir but is still in the CLI's
    own store, joining on the session ids in each known run's session map.

    This is what makes the sessions already on disk from before capture existed
    addressable, and it is an exact join rather than a heuristic: the session map says
    which node and which visit each of those session files belongs to.

    Returns one dict per record it would archive, so ``--dry-run`` and the real thing
    report the same thing.
    """
    planned: list[dict[str, Any]] = []
    root = transcripts_root()
    for run_id, run_dir, workflow in known_runs():
        rows = _session_rows(run_dir)
        known = _indexed(run_id)
        archived: list[dict[str, Any]] = []
        for row in rows:
            slug = _slug(row)
            if slug is None:
                continue
            session_id = str(row["session_id"])
            key = (row.get("generation"), row.get("seq"), session_id)
            if key in known or _sources(run_dir, slug, session_id):
                continue
            backend = str(row.get("backend", ""))
            files = capture.store_files(backend, session_id)
            if not files:
                continue
            sources = [
                ("transcript.jsonl" if path.is_file() else "sidechains", path)
                for path in files
            ]
            digest, size = _digest_of(sources)
            target = root / run_id / f"{slug}__{session_id}"
            record = {
                "run_id": run_id,
                "workflow": workflow,
                "flow": str(row.get("flow", "")),
                "node": str(row.get("node", "")),
                "session_id": session_id,
                "generation": row.get("generation"),
                "seq": row.get("seq"),
                "ts": row.get("ts") or 0.0,
                "backend": backend,
                "source": "store-backfill",
                "path": str(target.relative_to(root)),
                "bytes": size,
                "sha256": digest,
                "head": row.get("head"),
            }
            planned.append(record)
            if dry_run:
                continue
            try:
                record["bytes"] = _copy_record(sources, target)
            except OSError:
                logger.debug("backfill could not write %s", target)
                continue
            archived.append(record)
        if archived:
            store.insert_turns(archived)
    return planned


# ------------------------------------------------------------------------- reading


def record_path(row: dict[str, Any]) -> Path:
    """Where an index row's bodies are."""
    return transcripts_root() / str(row.get("path", ""))


def read_record(row: dict[str, Any]) -> dict[str, Any]:
    """One archived record as data: its index row, its files, and the prompt text.

    The transcript itself is *not* read into memory — a record can be tens of megabytes
    and a caller that wants it wants to stream it. The path is what is returned.
    """
    directory = record_path(row)
    files = sorted(p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file())
    prompt = ""
    try:
        prompt = (directory / "prompt.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    return {**row, "dir": str(directory), "files": files, "prompt": prompt}


# -------------------------------------------------------------------------- pruning


def prune(retention_days: float = RETENTION_DAYS, now: float | None = None) -> int:
    """Drop archived records older than the window; records removed.

    A window of zero or less keeps everything, which is the default. Bodies go first and
    the index rows after, so an interrupted prune leaves rows pointing at directories
    that are gone — which :func:`read_record` reports as an empty record — rather than
    orphaned directories nothing can find.
    """
    if retention_days <= 0:
        return 0
    cutoff = (now if now is not None else time.time()) - retention_days * 86400
    doomed = store.turns_before(cutoff)
    root = transcripts_root()
    for row in doomed:
        shutil.rmtree(root / str(row["path"]), ignore_errors=True)
    return store.delete_turns(cutoff)
