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
rather than one overwritten one. A run whose session map predates the visit key gets one
reconstructed from the map's own order — ``legacy-<ordinal>-<node>`` — because the runs
worth going back to are mostly older than the key that addresses them.

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
from collections import Counter
from pathlib import Path
from typing import Any

from workhorse.runner import transcript as capture
from workhorse.turnkey import VisitKey

from groom import prices, store

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

#: The generation stamped on a record whose row predates the visit key, so a reader can
#: tell a reconstructed ordinal from a number the run actually counted. Negative because
#: the engine only ever counts up from zero — ``0`` itself is a real generation, which is
#: why the marker cannot be a small non-negative sentinel.
LEGACY_GENERATION = -1
#: First segment of a reconstructed slug. Non-numeric on purpose: it cannot collide with
#: a real ``f"{generation:03d}-{seq:05d}-{node}"``.
LEGACY_PREFIX = "legacy"


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


def _visits(rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], int, int, str]]:
    """Each session-map row paired with the visit it addresses: (row, generation, seq, slug).

    A row written before the engine stamped a visit key has neither number, and those
    runs are most of the history anyone comes back to — so rather than skip them, they
    get a key reconstructed from the map itself: generation :data:`LEGACY_GENERATION`,
    and a seq counting the *distinct* ``(node, session)`` pairs in file order. The map is
    append-only, so that ordinal is stable across re-harvests; deduping the pair rather
    than counting lines is what keeps a session the runner recorded twice from becoming
    two half-records of one session, since the CLI's store file is the whole session
    either way.

    The reconstructed slug carries a non-numeric first segment, so it can never alias a
    real ``NNN-NNNNN-node`` — a genuine generation of ``0`` is reachable (a run dir with
    no ``resume_generation`` file reads as one), which rules out borrowing a number as
    the marker.
    """
    ordinals: dict[tuple[str, str], int] = {}
    visits: list[tuple[dict[str, Any], int, int, str]] = []
    for row in rows:
        node, session_id = str(row.get("node", "")), str(row["session_id"])
        generation, seq = row.get("generation"), row.get("seq")
        if isinstance(generation, int) and isinstance(seq, int):
            visits.append((row, generation, seq, VisitKey(generation, seq, node).slug))
            continue
        ordinal = ordinals.setdefault((node, session_id), len(ordinals) + 1)
        visits.append((row, LEGACY_GENERATION, ordinal, f"{LEGACY_PREFIX}-{ordinal:05d}-{node}"))
    return visits


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
        ("transcript.json", Path(f"{stem}.export.json")),
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
    """What capture reported — ``store``, ``export``, ``tee``, or empty when absent.

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
    copied: set[tuple[Any, Any, str]] = set()
    for row, generation, seq, slug in _visits(rows):
        session_id = str(row["session_id"])
        sources = _sources(run_dir, slug, session_id)
        if not sources:
            continue
        key = (generation, seq, session_id)
        if key in copied:
            # The map records one session twice — a retry that kept the session. Both
            # lines address the one record, and copying it again would only overwrite it
            # with itself and inflate what this tick claims to have archived.
            continue
        digest, _ = _digest_of(sources)
        if known.get(key) == digest:
            continue
        target = root / run / f"{slug}__{session_id}"
        try:
            written = _copy_record(sources, target)
        except OSError:
            logger.debug("turn record not archived: %s", target)
            continue
        copied.add(key)
        archived.append(
            {
                "run_id": run,
                "workflow": workflow or str(row.get("workflow", "")),
                "flow": str(row.get("flow", "")),
                "node": str(row.get("node", "")),
                "session_id": session_id,
                "generation": generation,
                "seq": seq,
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
        for row, generation, seq, slug in _visits(rows):
            session_id = str(row["session_id"])
            key = (generation, seq, session_id)
            if key in known or _sources(run_dir, slug, session_id):
                continue
            backend = str(row.get("backend", ""))
            files = capture.store_files(backend, session_id)
            exported = capture.export_session(backend, session_id) if backend and not files else None
            if not files and not backend:
                # A row from before the map recorded which CLI ran the turn. The store
                # that holds the session is the one that answers to its id, so ask them
                # rather than drop a turn for want of a field it was never written with.
                backend, files = capture.probe_stores(session_id)
                if not files:
                    backend, exported = capture.probe_exporters(session_id)
            if not files and exported is None:
                continue
            sources = [
                ("transcript.jsonl" if path.is_file() else "sidechains", path)
                for path in files
            ]
            if exported is not None:
                digest, size = hashlib.sha256(exported).hexdigest(), len(exported)
            else:
                digest, size = _digest_of(sources)
            # Recorded as known straight away, so a session the map names twice is
            # planned once — what is being copied is the CLI's whole session file, and
            # both lines point at the same one.
            known[key] = digest
            target = root / run_id / f"{slug}__{session_id}"
            record = {
                "run_id": run_id,
                "workflow": workflow,
                "flow": str(row.get("flow", "")),
                "node": str(row.get("node", "")),
                "session_id": session_id,
                "generation": generation,
                "seq": seq,
                "ts": row.get("ts") or 0.0,
                "backend": backend,
                "source": "export-backfill" if exported is not None else "store-backfill",
                "path": str(target.relative_to(root)),
                "bytes": size,
                "sha256": digest,
                "head": row.get("head"),
            }
            planned.append(record)
            if dry_run:
                continue
            try:
                if exported is not None:
                    shutil.rmtree(target, ignore_errors=True)
                    target.mkdir(parents=True, exist_ok=True)
                    body = exported[:MAX_RECORD_BYTES]
                    (target / "transcript.json").write_bytes(body)
                    record["bytes"] = len(body)
                else:
                    record["bytes"] = _copy_record(sources, target)
            except OSError:
                logger.debug("backfill could not write %s", target)
                continue
            archived.append(record)
        if archived:
            store.insert_turns(archived)
    return planned


# ---------------------------------------------------------------- model resolution


#: Attribute paths a CLI's session record may carry the model under. Both spellings are
#: read because the record's shape is the CLI's business, not ours.
_MODEL_KEYS = (("message", "model"), ("model",))


def session_models(session_id: str, backend: str = "") -> list[str]:
    """Every model id this session's own store names, first seen first.

    The turn span says what the *harness was asked for* — which for a CLI invoked as
    `--model sonnet` is an alias no rate card can name. The session store says what the
    provider actually ran, per assistant message. That is the difference between
    recovering a model and guessing one.
    """
    files = capture.store_files(backend, session_id) if backend else []
    if not files:
        _backend, files = capture.probe_stores(session_id)
    exported = capture.export_session(backend, session_id) if backend and not files else None
    if not files and exported is None and not backend:
        _backend, exported = capture.probe_exporters(session_id)
    found: dict[str, None] = {}
    for path in files:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            for keys in _MODEL_KEYS:
                value: Any = record
                for key in keys:
                    value = value.get(key) if isinstance(value, dict) else None
                if isinstance(value, str) and value:
                    found[value] = None
    if exported is not None:
        try:
            payload = json.loads(exported)
        except ValueError:
            payload = {}
        messages = payload.get("messages", []) if isinstance(payload, dict) else []
        for message in messages if isinstance(messages, list) else []:
            info = message.get("info", {}) if isinstance(message, dict) else {}
            if not isinstance(info, dict):
                continue
            model = info.get("modelID")
            provider = info.get("providerID")
            if isinstance(model, str) and model:
                full = f"{provider}/{model}" if isinstance(provider, str) and provider else model
                found[full] = None
    return list(found)


def _resolved(alias: str, candidates: list[str]) -> str:
    """The one model in `candidates` that `alias` names and the rate card prices, else "".

    Two conditions, both load-bearing. The candidate has to *contain* the alias, so a
    session that ran both opus and sonnet resolves each alias to its own model rather
    than to whichever appeared first. And exactly one has to match — an ambiguous
    session is left unpriced, because a coin flip between two rates is the kind of
    number that reads as evidence and is not.
    """
    token = alias.strip().lower()
    matched = {
        candidate
        for candidate in candidates
        if token and token in candidate.lower() and prices.price_for(candidate) is not None
    }
    return matched.pop() if len(matched) == 1 else ""


def resolve_models(run: str = "", dry_run: bool = False) -> dict[str, Any]:
    """Price the turns whose recorded model is an alias, using their session stores.

    A turn the card cannot price is not always a missing rate — often the rate is there
    and the *name* is not, because the harness recorded what it was invoked with. This
    reads the concrete id out of the session the turn ran in and prices the tokens with
    it, stamping `priced_model` so the estimate says which rate produced it.

    Returns what it resolved and what it could not: `unresolved` maps each model still
    without a rate to its turn count, which is the list that genuinely needs a
    `prices.toml` entry.
    """
    rows = store.unpriceable_turns(run)
    seen: dict[str, list[str]] = {}
    updates: list[tuple[float, str, str]] = []
    resolved: Counter[str] = Counter()
    unresolved: Counter[str] = Counter()
    for row in rows:
        alias, session_id = str(row["model"] or ""), str(row["session_id"] or "")
        if not session_id:
            unresolved[alias or "(no model recorded)"] += 1
            continue
        if session_id not in seen:
            seen[session_id] = session_models(session_id, str(row["backend"] or ""))
        model = _resolved(alias, seen[session_id])
        estimated = (
            prices.estimate(
                model,
                row["input_tokens"],
                row["output_tokens"],
                row["cache_read_tokens"],
                row["cache_creation_tokens"],
            )
            if model
            else None
        )
        if model and estimated is not None:
            resolved[f"{alias} -> {model}"] += 1
            updates.append((estimated, model, str(row["span_id"])))
        else:
            unresolved[alias or "(no model recorded)"] += 1
    if not dry_run:
        store.apply_estimates(updates)
    return {
        "considered": len(rows),
        "sessions_read": len(seen),
        "priced": len(updates),
        "est_cost_usd": sum(value for value, _model, _span in updates),
        "resolved": dict(resolved.most_common()),
        "unresolved": dict(unresolved.most_common()),
    }


# ------------------------------------------------------------------------- reading


def visit_label(row: dict[str, Any]) -> str:
    """How an index row's visit reads to a human: ``3-17``, or ``legacy-17`` when the key
    was reconstructed from a session map written before the engine stamped one.

    A reader has to be able to tell the two apart: ``legacy-17`` orders the run's turns
    and nothing more, where a real ``3-17`` is the seventeenth turn of the third start.
    """
    generation, seq = row.get("generation"), row.get("seq")
    if generation == LEGACY_GENERATION:
        return f"{LEGACY_PREFIX}-{seq}"
    return f"{generation}-{seq}"


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
