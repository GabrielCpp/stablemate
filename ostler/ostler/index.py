"""The persistent, content-addressed parse index store.

``model._FEATURE_DOC_CACHE`` is already keyed on a file's **content digest** rather than
its mtime, and for the right reason: the writer phases of a workflow edit these files
between loads, so a same-size rewrite inside one filesystem timestamp tick is exactly
what a stat-keyed cache serves stale. What that cache lacks is survival — every ``ostler``
invocation is a fresh process, so its 24 seconds of saved work are thrown away at exit.
This module is that cache, persisted and generalised.

What it serves is :func:`ostler.model.read_doc` — the read-only document accessor. A
document's frontmatter, sections, bullets, links and tables are a **pure function of its
bytes**, which is why they can be stored under a content key with no invalidation rule
beyond the epoch below. Writers do not come through here at all: they call
``markdown.split`` and get a document of their own, because ``replace_body`` mutates in
place and a shared instance handed to a writer would be a live bug.

The controls landed ahead of the serving: an off switch (:attr:`IndexStore.enabled`), an
explicit directory, a hit/miss count a caller can print, an eviction entry point
(:func:`clean`) and an ambient :func:`session`. A cache that is on by default and has none
of those is a cache nobody can bisect against, which is why they came first.

Three rules carry the whole design.

*One epoch hash.* :func:`epoch` is a single combined hash over every global input —
the tool version, the bundled schemas, the dynamic kind registry, the config files ostler
reads, the waiver file and the freeze manifest. Any change to any one of them invalidates
every entry. There is deliberately no per-input granularity: recomputing a book is cheap
next to the cost of getting a partial invalidation subtly wrong, and a wrong partial
invalidation is silent.

*The entry key is the repo-name-qualified repo-relative path plus the content sha.*
Repo-relative rather than absolute is load-bearing — two worktrees of one repo, and the
same repo mounted in a container, produce the same key, so one entry serves all of them.
The repo name and the relative path are both in the key because the same bytes at a
different path are a different entry.

*Damage is a miss, never an error.* The store is an optimisation; it may never be the
reason a command fails. A truncated payload, a corrupt one, a payload stamped with a
schema version this build does not write, an index directory that cannot be created —
each reads as a miss and each write survives it.

Payloads are :mod:`pickle` stamped with :data:`SCHEMA_VERSION`, compared for *equality*
rather than ``>=``: a payload written by a newer ostler is as unreadable as one written
by an older one, and misreading it is worse than recomputing it.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import time
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import metadata
from importlib.resources import files
from pathlib import Path
from typing import Any

from ostler import dynamic_registry
from ostler._vendor.stablemate_core import base_cache, config as core_config

#: The environment override for the index directory. Highest precedence after an
#: explicit argument, so a container can point every tool in it at a copied-in cache.
INDEX_DIR_ENV = "OSTLER_INDEX_DIR"

#: The key ostler's own (shared, home) config uses to name the index directory.
CONFIG_KEY = "ostler_index_dir"

#: Where the index lands under the shared stablemate cache when nothing overrides it.
#: XDG semantics — deleting it at any point costs time and never correctness.
INDEX_DIR_NAME = "ostler-index"

#: The on-disk layout of an entry file. Bump for any change an older reader would get
#: *wrong*; the epoch already carries the ostler version, so class drift is caught for
#: free and this only has to guard the file layout itself.
SCHEMA_VERSION = 1

#: How long an entry may go unwritten before a prune removes it. Two weeks: long enough
#: that an occasional book survives a quiet fortnight, short enough that an unattended
#: machine cannot grow the cache without limit.
#:
#: *Unwritten*, not *unread*: an entry's age is its ``st_mtime``, and a read does not
#: refresh it. That is the right bound for a content-addressed store, where a key names
#: the exact bytes it was computed from — an entry still being read is one whose content
#: has not moved in a fortnight, and evicting it costs the single recomputation that
#: writes it back. Refreshing on read would buy nothing for that and would put a write
#: syscall on every hit of the path this cache exists to make fast.
DEFAULT_MAX_AGE_S = 14 * 24 * 60 * 60.0

#: How often a prune may actually sweep, regardless of how many entries are written.
#:
#: The sweep is a full ``rglob`` plus a ``stat`` per file, so running it on every write
#: made a store cost more the fuller it got: measured on a 1,200-file book, a cold fill
#: took 55.16s against 6.05s with the sweep stubbed out, and 5.57s with no index at all.
#: The bound this enforces is an *age* bound, and an age bound does not need to be checked
#: at write granularity — an entry a few hours past the cutoff is not a different outcome
#: from one evicted the instant it crossed. Stamped on disk rather than held per process,
#: because every ``ostler`` invocation is a fresh process and a per-process guard would
#: still sweep once per command.
PRUNE_INTERVAL_S = 60 * 60.0

#: The stamp recording when this directory was last swept. Skipped by :func:`clean` itself:
#: it is the sweep's own bookkeeping, not an entry, so it is neither counted nor evicted.
PRUNE_STAMP_NAME = ".last-prune"

#: The config files ``model._load_config`` reads, in its order. Mirrored rather than
#: imported because ``model`` exposes no constant for them; the epoch only needs their
#: *bytes*, so reading one ostler does not honour would over-invalidate, never
#: under-invalidate.
CONFIG_FILENAMES = ("ostler.yml", "ostler.yaml", "agents.yml", ".agents.yml")

#: ``docs/doctor-waivers.json``, relative to the repo root (``waivers.WAIVERS_FILE``).
WAIVERS_RELPATH = ("docs", "doctor-waivers.json")

#: ``.agents/ids.json``, relative to the repo root (``freeze._ids_path``).
IDS_RELPATH = (".agents", "ids.json")

#: Every global input the epoch covers, in the spelling :func:`epoch_inputs` keys.
EPOCH_LABELS: tuple[str, ...] = (
    "version",
    "schemas",
    "kinds",
    "config",
    "waivers",
    "freeze",
)

_PAYLOAD_KEY = "value"
_VERSION_KEY = "schema_version"


# ---------------------------------------------------------------------------
# Digest helpers
# ---------------------------------------------------------------------------
def _sha(*chunks: bytes) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(len(chunk).to_bytes(8, "big"))
        digest.update(chunk)
    return digest.hexdigest()


def content_sha(data: bytes) -> str:
    """The store's digest of a file's bytes, for a caller that has already read them.

    :func:`IndexStore.key` will read the file itself when it has to, but the document
    accessor has the bytes in hand — it read them to decide whether its own in-process memo
    is still current — and re-reading the whole book once per lookup is exactly the kind of
    cost this store exists to remove.
    """
    return _sha(data)


def _file_sha(path: Path) -> str | None:
    """The sha of *path*'s bytes, or ``None`` when it cannot be read.

    Absence is a legitimate answer here — the waiver file and the freeze manifest are
    both optional — so this never raises.
    """
    try:
        return _sha(path.read_bytes())
    except OSError:
        return None


def _absent() -> str:
    """The material of an input that is not on disk.

    A named constant rather than ``""`` so that "no waiver file" and "an empty waiver
    file" hash differently — creating an empty file is a real edit.
    """
    return "absent"


# ---------------------------------------------------------------------------
# The epoch: one hash over every global input
# ---------------------------------------------------------------------------
def _ostler_version() -> str:
    try:
        return metadata.version("ostler")
    except metadata.PackageNotFoundError:  # pragma: no cover - source checkout
        return "unknown"


def _schemas_material() -> str:
    """A digest over every bundled JSON Schema, by name and by content."""
    root = files("ostler").joinpath("schema")
    chunks: list[bytes] = []
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        if not entry.name.endswith(".json"):
            continue
        chunks.append(entry.name.encode("utf-8"))
        chunks.append(entry.read_bytes())
    return _sha(*chunks)


def _kinds_material(root: Path) -> str:
    """The dynamic kind registry: the repo's ``.agents/templates.yml`` plus the built-ins.

    Hashed from the file's raw bytes rather than the parsed mapping, so a change ostler's
    parser currently ignores still busts the cache.
    """
    templates = dynamic_registry.templates_path(root)
    builtins = ",".join(sorted(dynamic_registry.BUILTIN_NAMES))
    return _sha(
        builtins.encode("utf-8"),
        (_file_sha(templates) or _absent()).encode("utf-8"),
    )


def _config_material(root: Path) -> str:
    """Every config file ostler reads, named and hashed in the order it reads them."""
    chunks: list[bytes] = []
    for name in CONFIG_FILENAMES:
        chunks.append(name.encode("utf-8"))
        chunks.append((_file_sha(root / name) or _absent()).encode("utf-8"))
    return _sha(*chunks)


def _waivers_material(root: Path) -> str:
    return _file_sha(root.joinpath(*WAIVERS_RELPATH)) or _absent()


def _freeze_material(root: Path) -> str:
    """The ``frozen`` table of ``.agents/ids.json``, not the whole registry.

    Minting an id rewrites that file on almost every authoring turn, and a counter bump
    says nothing about any document's parse products. The frozen pins do.
    """
    path = root.joinpath(*IDS_RELPATH)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _absent()
    frozen = data.get("frozen") if isinstance(data, dict) else None
    return _sha(json.dumps(frozen, sort_keys=True, default=str).encode("utf-8"))


def epoch_inputs(root: Path) -> dict[str, str]:
    """The material of every global input, one entry per label in :data:`EPOCH_LABELS`.

    Separated from :func:`epoch` so that what the epoch covers is inspectable — a test,
    or a future ``ostler cache explain``, can see *which* input moved without owning a
    second, subtly different derivation of the hash.
    """
    return {
        "version": _ostler_version(),
        "schemas": _schemas_material(),
        "kinds": _kinds_material(root),
        "config": _config_material(root),
        "waivers": _waivers_material(root),
        "freeze": _freeze_material(root),
    }


def epoch(root: Path) -> str:
    """One combined hash over :func:`epoch_inputs`, and a pure function of it.

    ``epoch_inputs`` is looked up on the module at call time on purpose: that is the seam
    a test — and eventually a cache-explain command — substitutes to move one input whose
    material has no on-disk home.
    """
    inputs = epoch_inputs(root)
    chunks: list[bytes] = []
    for label in sorted(inputs):
        chunks.append(label.encode("utf-8"))
        chunks.append(str(inputs[label]).encode("utf-8"))
    return _sha(*chunks)


# ---------------------------------------------------------------------------
# Where the index lives
# ---------------------------------------------------------------------------
def index_dir(explicit: Path | str | None = None) -> Path:
    """The index directory: *explicit* → ``$OSTLER_INDEX_DIR`` → config → the default.

    The default is under the shared stablemate cache, which every stablemate tool already
    treats as deletable at any time — the right home for something whose loss costs only
    time.
    """
    if explicit is not None:
        return Path(explicit).expanduser()

    from_env = os.environ.get(INDEX_DIR_ENV)
    if from_env:
        return Path(from_env).expanduser()

    configured = core_config.get_config_value(CONFIG_KEY)
    if isinstance(configured, str) and configured.strip():
        return Path(configured).expanduser()

    return base_cache.cache_root() / INDEX_DIR_NAME


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------
class IndexStore:
    """A content-addressed store of parse products for one repo root.

    Construct one per command. It resolves its directory and its epoch lazily, so
    constructing it costs nothing when every lookup turns out to be a miss.
    """

    def __init__(
        self,
        root: Path,
        *,
        directory: Path | str | None = None,
        max_age_s: float = DEFAULT_MAX_AGE_S,
        enabled: bool = True,
    ) -> None:
        self.root = Path(root)
        self.directory = index_dir(directory)
        self.max_age_s = max_age_s
        # On by default; `--no-index` is the escape hatch, not the switch. A disabled store
        # is still constructed and still resolves its directory, so the run can *report*
        # which index it would have used while touching none of it.
        self.enabled = enabled
        self.hits = 0
        self.misses = 0
        self._epoch: str | None = None

    def stats(self) -> dict:
        """The hit/miss line, as it appears under ``index`` in ``--json`` output.

        The effective directory travels with the counts because that is the pair a
        disagreement between two runs is diagnosed from: the same counts against different
        directories is a different fault from different counts against the same one.
        """
        return {
            "dir": str(self.directory),
            "enabled": self.enabled,
            "hits": self.hits,
            "misses": self.misses,
        }

    # -- keys ---------------------------------------------------------------
    @property
    def epoch(self) -> str:
        if self._epoch is None:
            self._epoch = epoch(self.root)
        return self._epoch

    def entry_name(self, path: Path) -> str:
        """The repo-name-qualified repo-relative name of *path*.

        Absolute-path fallback for a file outside the root: it cannot be shared across
        worktrees, but it also must not silently collide with one that can.
        """
        target = Path(path)
        try:
            relative = target.resolve().relative_to(self.root.resolve())
        except (OSError, ValueError):
            return str(target)
        return f"{self.root.resolve().name}/{relative.as_posix()}"

    def key(self, path: Path, *, sha: str | None = None) -> str | None:
        """The entry key for *path*, or ``None`` when its bytes cannot be read.

        *sha* is :func:`content_sha` of the file's bytes, for a caller that has already read
        them; omitted, the file is read here.
        """
        content = sha if sha is not None else _file_sha(Path(path))
        if content is None:
            return None
        return _sha(
            self.epoch.encode("utf-8"),
            self.entry_name(path).encode("utf-8"),
            content.encode("utf-8"),
        )

    def content_key(self, *material: str) -> str:
        """An entry key built from *material* alone — for a product no path identifies.

        The document products are keyed on where a file sits as well as what is in it, because
        the same bytes at another path are a different document. A code file's **symbol set**
        is not like that: it is a pure function of the bytes and of the grammar that read them,
        so a vendored copy of a module declares exactly what the original does and should cost
        one extraction between them. The path is therefore deliberately absent here, and what
        takes its place is a namespace label the caller supplies, so two products cannot
        collide on one key by agreeing about their material.

        The epoch is still in it: ostler's own version is in the epoch, and a change to the
        extractor changes the answer as surely as a change to the grammar does.
        """
        return _sha(self.epoch.encode("utf-8"), *(part.encode("utf-8") for part in material))

    def _entry_path(self, key: str) -> Path:
        # Sharded on the first two hex characters so one directory never holds every
        # entry of every repo this machine has ever seen.
        return self.directory / key[:2] / key

    # -- reads and writes ---------------------------------------------------
    def get(self, path: Path, *, sha: str | None = None) -> Any | None:
        """The stored value for *path*, or ``None`` for any kind of miss.

        Every failure mode collapses to ``None`` on purpose: an unreadable file, a
        truncated pickle, a payload from another schema version and a directory that is
        not a directory are all "recompute it", and none of them is the caller's problem.

        A disabled store answers ``None`` without counting: under ``--no-index`` the
        counts must read zero, because a run whose misses climb is a run that consulted
        an index it was told not to.
        """
        return self.get_key(self.key(path, sha=sha))

    def get_key(self, key: str | None) -> Any | None:
        """The stored value under *key*, counted — for a caller that built its own key.

        ``None`` for *key* is the caller's own miss (a file whose bytes it could not read), and
        it counts as one: the run did want something the index could not give it.
        """
        if not self.enabled:
            return None
        value = self._read(key)
        if value is None:
            self.misses += 1
        else:
            self.hits += 1
        return value

    def _read(self, key: str | None) -> Any | None:
        if key is None:
            return None
        try:
            raw = self._entry_path(key).read_bytes()
        except OSError:
            return None
        try:
            payload = pickle.loads(raw)
        except Exception:
            # `pickle.loads` raises essentially anything on damaged input — the opcode
            # stream is a program. Narrowing this would only mean a corrupt entry
            # crashing the command instead of missing, which is the one outcome this
            # store must never produce.
            return None
        if not isinstance(payload, dict):
            return None
        # Equality, not `>=`: a payload a newer ostler wrote is as unreadable as an
        # older one's, and misreading it is worse than recomputing it.
        if payload.get(_VERSION_KEY) != SCHEMA_VERSION:
            return None
        return payload.get(_PAYLOAD_KEY)

    def put(self, path: Path, value: Any, *, sha: str | None = None) -> None:
        """Store *value* for *path*, pruning past the age bound when a prune is due.

        Never raises: a store that cannot write is a store that gives no speedup, not a
        command that fails. A disabled store writes nothing at all — ``--no-index`` has to
        leave the directory it was pointed at untouched, not merely unread.
        """
        self.put_key(self.key(path, sha=sha), value)

    def put_key(self, key: str | None, value: Any) -> None:
        """Store *value* under *key* — for a caller that built its own key. Never raises."""
        if not self.enabled:
            return
        if key is None:
            return
        self.prune()
        entry = self._entry_path(key)
        payload = {_VERSION_KEY: SCHEMA_VERSION, _PAYLOAD_KEY: value}
        try:
            entry.parent.mkdir(parents=True, exist_ok=True)
            # Written through a temporary in the same directory and renamed, so a reader
            # racing a writer sees either the old entry or the new one, never half of a
            # pickle. `os.replace` is atomic on every platform ostler runs on.
            temporary = entry.with_name(f"{entry.name}.{os.getpid()}.tmp")
            temporary.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
            os.replace(temporary, entry)
        except (OSError, pickle.PicklingError, TypeError, ValueError, RecursionError):
            return

    # -- self-bounding ------------------------------------------------------
    def prune(self, now: float | None = None) -> int:
        """Delete entries unwritten for longer than ``max_age_s``; return how many.

        A bound, not a sweep: an entry inside the bound survives every write. Runs on the
        write path rather than as a command, so an unattended machine bounds itself
        without anyone remembering to. ``ostler cache clean`` is the same sweep asked for
        explicitly, which is why both go through :func:`clean`.

        Rate-limited to once per :data:`PRUNE_INTERVAL_S` per directory. The write path is
        the only place this can run from, and a fill writes an entry per file, so without
        the limit the cost of storing a book was quadratic in the size of the cache — the
        measurements are on :data:`PRUNE_INTERVAL_S`. Returning 0 when the stamp is fresh
        is not a failure to prune; it is the sweep having already run recently enough that
        nothing is meaningfully past the bound.
        """
        if self.max_age_s <= 0:
            return 0
        if not self._prune_is_due(now):
            return 0
        return clean(self.directory, max_age_s=self.max_age_s, now=now)

    def _prune_is_due(self, now: float | None = None) -> bool:
        """Whether a sweep may run, stamping the directory when it may.

        The stamp is written *before* the sweep rather than after, so a crash mid-sweep
        costs one deferred prune instead of putting every process into a sweep loop. A
        directory that cannot be stamped — read-only, or not yet created — reports not-due:
        a store that cannot record having pruned must not sweep on every write instead.
        """
        moment = time.time() if now is None else now
        stamp = self.directory / PRUNE_STAMP_NAME
        try:
            if moment - stamp.stat().st_mtime < PRUNE_INTERVAL_S:
                return False
        except OSError:
            pass  # No stamp yet: the first write to a directory is due a sweep.
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            stamp.touch()
            os.utime(stamp, (moment, moment))
        except OSError:
            return False
        return True


# ---------------------------------------------------------------------------
# Eviction
# ---------------------------------------------------------------------------
def clean(
    directory: Path | str,
    *,
    everything: bool = False,
    max_age_s: float = DEFAULT_MAX_AGE_S,
    now: float | None = None,
) -> int:
    """Delete index entries under *directory* and return how many went.

    Entries whose *write* is older than ``max_age_s`` by default — a read does not refresh
    an entry's age, for the reason on :data:`DEFAULT_MAX_AGE_S` — and every entry under
    *everything*. A directory that is not there is the normal state of a fresh machine, not
    a failure: it removes nothing, reports nothing removed, and is *not* created on the way
    past — an eviction command that leaves a directory behind has done the opposite of its
    job.

    :data:`PRUNE_STAMP_NAME` is passed over by both modes. It records when this directory
    was last swept, so counting it would inflate the number reported to an operator and
    removing it under ``--all`` would hand the next writer a directory that looks never
    swept.
    """
    root = Path(directory).expanduser()
    cutoff = (time.time() if now is None else now) - max_age_s
    removed = 0
    try:
        candidates = sorted(root.rglob("*"))
    except OSError:
        return 0
    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
            if candidate.name == PRUNE_STAMP_NAME:
                continue
            if not everything and candidate.stat().st_mtime >= cutoff:
                continue
            candidate.unlink()
        except OSError:
            # Another process cleaning the same shared cache is expected, not an error:
            # it wins the race and the entry is gone either way.
            continue
        removed += 1
    # The shard directories are an implementation detail of the key, so an emptied one is
    # litter rather than state. Walking deepest-first empties a nested shard before its
    # parent is considered.
    for candidate in sorted(candidates, reverse=True):
        try:
            if candidate.is_dir():
                candidate.rmdir()
        except OSError:
            continue
    return removed


# ---------------------------------------------------------------------------
# The ambient store for one command
# ---------------------------------------------------------------------------
#: The store the running command opened, or ``None`` outside one. Ambient rather than
#: threaded because the read-only accessors that will consult it — the document accessor,
#: the anchor computation — are reached through call chains (``model.load``,
#: ``LinkResolver``) that no caller of ``doctor.run`` constructs or can pass through.
_ACTIVE: IndexStore | None = None


def active() -> IndexStore | None:
    """The store the enclosing :func:`session` opened, or ``None``.

    A consumer that gets ``None`` recomputes — outside a session there is no index, and
    that must read as a cold path rather than as an error.
    """
    return _ACTIVE


@contextmanager
def use(store: IndexStore) -> Iterator[IndexStore]:
    """Make an already-constructed *store* :func:`active` for the duration of a block.

    Restores whatever was active before rather than clearing it, so two sessions can nest
    — ``--verify-index`` runs one indexed and one not inside a single process — without
    the inner one leaving the outer's store dangling on the way out.

    Separate from :func:`session` because a long-lived caller (:class:`ostler.Ostler`)
    keeps one store across many loads and needs its counts to accumulate, rather than a
    fresh store per load.
    """
    global _ACTIVE
    previous = _ACTIVE
    _ACTIVE = store
    try:
        yield store
    finally:
        _ACTIVE = previous


@contextmanager
def session(
    root: Path,
    *,
    directory: Path | str | None = None,
    enabled: bool = True,
) -> Iterator[IndexStore]:
    """Open a store for the duration of one command and make it :func:`active`."""
    with use(IndexStore(root, directory=directory, enabled=enabled)) as store:
        yield store
