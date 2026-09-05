"""Keep each agent turn's transcript in the run dir, beside the prompt that caused it.

`prompt.md` is what a node was told and `output.json` is what it answered; everything in
between — the reasoning, the tool calls, the file it read and then ignored — lives only in
the agent CLI's own session store. That store is keyed by nothing telemetry can join on,
exists only on the host that ran the CLI, and the CLI is free to prune it. So a node that
re-decided the same thing five times is diagnosable for exactly as long as the CLI feels
like keeping the evidence.

Three sources, in this order:

* **The store**, which is strictly richer than the stream: a Claude session directory
  carries attachments, queued operations and a whole sibling tree of subagent sidechains
  that never cross stdout at all.
* **A public session export**, for a CLI such as OpenCode whose internal database is not
  a stable filesystem contract but whose export includes reasoning, tool, file and subtask
  parts.
* **A tee of the stream**, for a CLI whose store this module cannot resolve and for a
  container whose store is not on this host. It is opened at the one redaction choke
  point, so what it keeps is redacted by construction.

Every captured turn records *which* of the two it came from. A consumer must never have
to guess what it is holding.

Nothing here may fail a turn: a capture that cannot be written is a capture that did not
happen, which is a worse run dir and not a worse run.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from workhorse import gitstate, turnkey

#: Where captures land inside a run dir.
TRANSCRIPTS_DIR = "transcripts"
#: Where a tee writes while the turn is still running and its session id is unknown.
PENDING_DIR = ".pending"
#: Per-turn ceiling. A turn runs 0.5-1.1 MB of JSONL; the cap is for the pathological
#: turn, so it is generous enough that a normal one never notices it.
DEFAULT_MAX_BYTES = 32 * 1024 * 1024


# --------------------------------------------------------------------------- stores


def _claude_store(session_id: str) -> list[Path]:
    """`~/.claude/projects/<cwd-slug>/<session>.jsonl`, plus the sibling directory of
    the same name holding subagent sidechains and tool results.

    Globbed over the project slugs rather than derived from cwd: the slug is the CLI's
    own encoding of a working directory, and a run that moved between trees would make a
    derivation wrong in a way a glob is not.
    """
    root = Path.home() / ".claude" / "projects"
    found: list[Path] = []
    for project in sorted(root.glob("*")):
        transcript = project / f"{session_id}.jsonl"
        if transcript.is_file():
            found.append(transcript)
        sidechains = project / session_id
        if sidechains.is_dir():
            found.append(sidechains)
    return found


def _codex_store(session_id: str) -> list[Path]:
    """`~/.codex/sessions/<y>/<m>/<d>/rollout-<timestamp>-<session>.jsonl`."""
    root = Path.home() / ".codex" / "sessions"
    return [p for p in sorted(root.glob(f"*/*/*/rollout-*{session_id}.jsonl")) if p.is_file()]


#: Backend name → "where does this CLI keep this session". Keyed by name rather than by
#: adapter class on purpose: the adapters import the classifier that calls this, so
#: importing the registry here would close that into a cycle.
#:
#: A backend absent from this table is not a defect — it means the tee is its source.
_STORES: dict[str, Callable[[str], list[Path]]] = {
    "claude": _claude_store,
    "codex": _codex_store,
}


def _opencode_export(session_id: str) -> bytes | None:
    """OpenCode's public full-session export, including reasoning and tool parts."""
    try:
        result = subprocess.run(
            ["opencode", "export", session_id],
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        loaded = json.loads(result.stdout)
    except ValueError:
        return None
    return result.stdout if isinstance(loaded, dict) else None


#: Backends whose public CLI can materialize a full session but whose internal store is
#: not a stable filesystem contract. Kept separate from `_STORES` because these produce
#: bytes rather than paths.
_EXPORTERS: dict[str, Callable[[str], bytes | None]] = {
    "opencode": _opencode_export,
}


def store_files(backend: str, session_id: str) -> list[Path]:
    """What this backend kept for ``session_id``, or an empty list.

    Empty covers every way this can come up short — a CLI with no resolver, a store on
    another host, a session the CLI already pruned — because the caller does the same
    thing in all of them: fall back to the tee.
    """
    resolver = _STORES.get(backend)
    if resolver is None:
        return []
    try:
        return resolver(session_id)
    except OSError:
        return []


def probe_stores(session_id: str) -> tuple[str, list[Path]]:
    """Which CLI's store holds this session, for a caller that does not know: (backend,
    files), or ``("", [])`` when none of them do.

    A session map written before the backend was recorded still names the session, and
    the store is where that session's body is. Probing is exact rather than heuristic —
    a resolver either finds files under that id or it does not, and the ids are opaque
    per-CLI tokens no two stores mint the same way — so this recovers the backend rather
    than guessing at it.
    """
    for backend in _STORES:
        files = store_files(backend, session_id)
        if files:
            return backend, files
    return "", []


def export_session(backend: str, session_id: str) -> bytes | None:
    """A backend's public full-session export, or ``None`` when unavailable."""
    exporter = _EXPORTERS.get(backend)
    if exporter is None:
        return None
    try:
        return exporter(session_id)
    except OSError:
        return None


def probe_exporters(session_id: str) -> tuple[str, bytes | None]:
    """Which public backend exporter recognizes ``session_id``, if any."""
    for backend in _EXPORTERS:
        exported = export_session(backend, session_id)
        if exported is not None:
            return backend, exported
    return "", None


# -------------------------------------------------------------------------- settings


@dataclass
class _Settings:
    run_dir: Path | None = None
    enabled: bool = False
    max_bytes: int = DEFAULT_MAX_BYTES
    #: Set once a store capture has actually worked in this run. Until then the tee runs
    #: alongside, because "this backend has a resolver" is not the same claim as "this
    #: host has the store" — a container is exactly where the two part company.
    store_proven: bool = False
    #: Kept for the run's own reporting; also what makes the tee droppable once the
    #: store is proven.
    backend: str = ""
    captures: list[Path] = field(default_factory=list)


_settings = _Settings()


def bind(run_dir: Path, *, enabled: bool = True, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    """Point capture at ``run_dir``. Called once, at the process boundary.

    Module state rather than a threaded parameter for the same reason
    :mod:`workhorse.gitstate` is: the two writers are a stream callback four layers below
    the run and a classifier that never saw the run's configuration, and threading a
    setting through both would put a transcript knob in signatures that are about
    something else.
    """
    global _settings
    _settings = _Settings(run_dir=run_dir, enabled=enabled, max_bytes=max(0, max_bytes))


def unbind() -> None:
    global _settings
    _settings = _Settings()


def bound() -> bool:
    return _settings.enabled and _settings.run_dir is not None


def transcripts_dir() -> Path | None:
    if _settings.run_dir is None:
        return None
    return _settings.run_dir / TRANSCRIPTS_DIR


# ------------------------------------------------------------------------------ tee


class Tee:
    """A live copy of one turn's stream, written before its session id is known.

    Opened under `.pending/` and named for the visit, because that is all that is known
    at the time; :func:`capture` renames it once the CLI has said which session this was,
    or deletes it when the store turned out to have a better copy.
    """

    def __init__(self, path: Path, max_bytes: int) -> None:
        self._path = path
        self._fh: TextIO | None
        self._max = max_bytes
        self._written = 0
        self._truncated = False
        self._fh = path.open("w", encoding="utf-8")

    def write(self, line: str) -> None:
        if self._fh is None or self._truncated:
            return
        try:
            budget = self._max - self._written
            if budget < len(line):
                # The cap lands mid-line more often than not. Keep the fragment — it is
                # still evidence — but close it off, or the marker below would be
                # concatenated onto it and neither would parse.
                self._written += self._fh.write(line[:budget])
                if budget > 0 and not line[:budget].endswith("\n"):
                    self._fh.write("\n")
                self._truncate()
                return
            self._written += self._fh.write(line)
        except OSError:
            self.close()

    def _truncate(self) -> None:
        """Stop at the cap, saying so in the file rather than by ending mid-line.

        A truncated transcript that announces itself is usable evidence; one that just
        stops is indistinguishable from a turn that died."""
        self._truncated = True
        if self._fh is None:
            return
        try:
            self._fh.write(json.dumps({"truncated": True, "bytes": self._written}) + "\n")
        except OSError:
            pass

    def close(self) -> None:
        if self._fh is None:
            return
        try:
            self._fh.close()
        except OSError:
            pass
        self._fh = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def truncated(self) -> bool:
        return self._truncated


def tee_begin(node_id: str) -> Tee | None:
    """Open a tee for the visit now running, or None when there is nothing to tee into.

    Skipped once a store capture has worked in this run: from that point the tee would be
    a second, poorer copy of something already kept.
    """
    if not bound() or _settings.store_proven:
        return None
    key = turnkey.current()
    if key is None or key.node != node_id:
        return None
    root = transcripts_dir()
    if root is None:
        return None
    try:
        pending = root / PENDING_DIR
        pending.mkdir(parents=True, exist_ok=True)
        return Tee(pending / f"{key.slug}.jsonl", _settings.max_bytes)
    except OSError:
        return None


# -------------------------------------------------------------------------- capture


def _copy_capped(src: Path, dst: Path, budget: int) -> tuple[int, bool]:
    """Copy at most ``budget`` bytes of ``src``. Returns (bytes written, truncated)."""
    written = 0
    truncated = False
    with src.open("rb") as fin, dst.open("wb") as fout:
        while budget > 0:
            chunk = fin.read(min(1 << 20, budget))
            if not chunk:
                break
            fout.write(chunk)
            written += len(chunk)
            budget -= len(chunk)
        if fin.read(1):
            truncated = True
            fout.write(json.dumps({"truncated": True, "bytes": written}).encode() + b"\n")
    return written, truncated


def _copy_tree_capped(src: Path, dst: Path, budget: int) -> tuple[int, bool]:
    written = 0
    truncated = False
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        if budget <= 0:
            return written, True
        target = dst / path.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        n, cut = _copy_capped(path, target, budget)
        written += n
        budget -= n
        truncated = truncated or cut
    return written, truncated


def _write_bytes_capped(data: bytes, dst: Path, budget: int) -> tuple[int, bool]:
    """Write a command-backed export with the same bounded-record contract as stores."""
    body = data[:budget]
    truncated = len(data) > len(body)
    with dst.open("wb") as fh:
        fh.write(body)
        if truncated:
            fh.write(b'\n{"truncated":true,"bytes":' + str(len(body)).encode() + b"}\n")
    return len(body), truncated


def _write_meta(stem: Path, meta: dict[str, object]) -> None:
    try:
        Path(f"{stem}.meta.json").write_text(json.dumps(meta, indent=2))
    except OSError:
        pass


def _discard(paths: Iterable[Path]) -> None:
    for path in paths:
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        except OSError:
            pass


def capture(backend: str, node_id: str, session_id: str, tee: Tee | None = None) -> Path | None:
    """Keep this turn's transcript, and return where it landed (None when nothing was).

    Called once the turn is over and the CLI has named its session — which is the first
    moment either source can be addressed by the visit key the rest of the run record
    uses.
    """
    if not bound() or not session_id:
        return None
    key = turnkey.current()
    if key is None or key.node != node_id:
        # Same guard as the rest of the visit record: a turn taken outside a visit the
        # engine opened has no name to file under, and an invented one would collide.
        return None
    root = transcripts_dir()
    if root is None:
        return None
    stem = root / f"{key.slug}__{session_id}"
    pending = tee.path if tee is not None else root / PENDING_DIR / f"{key.slug}.jsonl"

    meta: dict[str, object] = {
        "backend": backend,
        "session_id": session_id,
        "node": node_id,
        "generation": key.generation,
        "seq": key.seq,
        "ts": int(time.time()),
    }
    head = gitstate.current_head()
    if head:
        meta["head"] = head

    try:
        root.mkdir(parents=True, exist_ok=True)
        files = store_files(backend, session_id)
        if files:
            written, truncated = 0, False
            budget = _settings.max_bytes
            for src in files:
                target = Path(f"{stem}.jsonl") if src.is_file() else Path(f"{stem}.d")
                if src.is_file():
                    n, cut = _copy_capped(src, target, max(0, budget))
                else:
                    n, cut = _copy_tree_capped(src, target, max(0, budget))
                written += n
                budget -= n
                truncated = truncated or cut
            _settings.store_proven = True
            _discard([pending])
            meta |= {"source": "store", "bytes": written, "truncated": truncated}
            _write_meta(stem, meta)
            _settings.captures.append(stem)
            return stem
        exported = export_session(backend, session_id)
        if exported is not None:
            written, truncated = _write_bytes_capped(
                exported, Path(f"{stem}.export.json"), _settings.max_bytes
            )
            _discard([pending])
            meta |= {"source": "export", "bytes": written, "truncated": truncated}
            _write_meta(stem, meta)
            _settings.captures.append(stem)
            return stem
        if pending.exists() and pending.stat().st_size > 0:
            landed = Path(f"{stem}.tee.jsonl")
            landed.unlink(missing_ok=True)
            pending.replace(landed)
            meta |= {
                "source": "tee",
                "bytes": landed.stat().st_size,
                "truncated": tee.truncated if tee is not None else False,
            }
            _write_meta(stem, meta)
            _settings.captures.append(stem)
            return stem
        _discard([pending])
    except OSError:
        return None
    return None
