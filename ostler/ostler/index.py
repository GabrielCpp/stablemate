"""The persistent, content-addressed parse index store."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pickle
import time
import typing
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import metadata
from importlib.resources import files
from pathlib import Path
from typing import Any

from ostler import dynamic_registry
from ostler._vendor.stablemate_core import base_cache, config as core_config

INDEX_DIR_ENV = "OSTLER_INDEX_DIR"

CONFIG_KEY = "ostler_index_dir"

INDEX_DIR_NAME = "ostler-index"

SCHEMA_VERSION = 10

DEFAULT_MAX_AGE_S = 14 * 24 * 60 * 60.0

PRUNE_INTERVAL_S = 60 * 60.0

PRUNE_STAMP_NAME = ".last-prune"

CONFIG_FILENAMES = ("ostler.yml", "ostler.yaml", "agents.yml", ".agents.yml")

IDS_RELPATH = (".agents", "ids.json")

EPOCH_LABELS: tuple[str, ...] = (
    "version",
    "schemas",
    "kinds",
    "config",
    "freeze",
    "shape",
)

_PAYLOAD_KEY = "value"
_VERSION_KEY = "schema_version"


def _sha(*chunks: bytes) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(len(chunk).to_bytes(8, "big"))
        digest.update(chunk)
    return digest.hexdigest()


def content_sha(data: bytes) -> str:
    """The store's digest of a file's bytes, for a caller that has already read them."""
    return _sha(data)


def _file_sha(path: Path) -> str | None:
    """The sha of *path*'s bytes, or ``None`` when it cannot be read."""
    try:
        return _sha(path.read_bytes())
    except OSError:
        return None


def _absent() -> str:
    """The material of an input that is not on disk."""
    return "absent"


def _nested_types(annotation: object) -> list[type]:
    """Every concrete type named inside a (possibly generic) type annotation."""
    origin = typing.get_origin(annotation)
    if origin is not None:
        found: list[type] = []
        for arg in typing.get_args(annotation):
            found.extend(_nested_types(arg))
        return found
    if isinstance(annotation, type):
        return [annotation]
    return []


def _reachable_dataclasses(roots: tuple[type, ...]) -> set[type[Any]]:
    """Every dataclass reachable from *roots* through a field's type, *roots* included."""
    seen: set[type[Any]] = set()
    stack: list[type[Any]] = list(roots)
    while stack:
        candidate = stack.pop()
        if not dataclasses.is_dataclass(candidate) or candidate in seen:
            continue
        seen.add(candidate)
        hints = typing.get_type_hints(candidate)
        for f in dataclasses.fields(candidate):
            stack.extend(_nested_types(hints.get(f.name, f.type)))
    return seen


def dataclass_shape_digest(*roots: type) -> str:
    """A stable digest over the field *names and annotations* of *roots* and every dataclass reachable from them."""
    types_ = sorted(
        _reachable_dataclasses(roots), key=lambda tp: f"{tp.__module__}.{tp.__qualname__}"
    )
    chunks: list[bytes] = []
    for tp in types_:
        chunks.append(f"{tp.__module__}.{tp.__qualname__}".encode("utf-8"))
        for f in dataclasses.fields(tp):
            chunks.append(f.name.encode("utf-8"))
            chunks.append(str(f.type).encode("utf-8"))
    return _sha(*chunks)


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
    """The dynamic kind registry: the repo's ``.agents/templates.yml`` plus the built-ins."""
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


def _freeze_material(root: Path) -> str:
    """The ``frozen`` table of ``.agents/ids.json``, not the whole registry."""
    path = root.joinpath(*IDS_RELPATH)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _absent()
    frozen = data.get("frozen") if isinstance(data, dict) else None
    return _sha(json.dumps(frozen, sort_keys=True, default=str).encode("utf-8"))


def _shape_material() -> str:
    """The stored dataclasses' field-name-and-annotation digest, as an epoch input."""
    from ostler import api, inventory, model

    return dataclass_shape_digest(
        model.UINode, model._DocProducts, api.Snapshot, inventory._SymbolTable
    )


def epoch_inputs(root: Path) -> dict[str, str]:
    """The material of every global input, one entry per label in :data:`EPOCH_LABELS`."""
    return {
        "version": _ostler_version(),
        "schemas": _schemas_material(),
        "kinds": _kinds_material(root),
        "config": _config_material(root),
        "freeze": _freeze_material(root),
        "shape": _shape_material(),
    }


def epoch(root: Path) -> str:
    """One combined hash over :func:`epoch_inputs`, and a pure function of it."""
    inputs = epoch_inputs(root)
    chunks: list[bytes] = []
    for label in sorted(inputs):
        chunks.append(label.encode("utf-8"))
        chunks.append(str(inputs[label]).encode("utf-8"))
    return _sha(*chunks)


def index_dir(explicit: Path | str | None = None) -> Path:
    """The index directory: *explicit* → ``$OSTLER_INDEX_DIR`` → config → the default."""
    if explicit is not None:
        return Path(explicit).expanduser()

    from_env = os.environ.get(INDEX_DIR_ENV)
    if from_env:
        return Path(from_env).expanduser()

    configured = core_config.get_config_value(CONFIG_KEY)
    if isinstance(configured, str) and configured.strip():
        return Path(configured).expanduser()

    return base_cache.cache_root() / INDEX_DIR_NAME


class IndexStore:
    """A content-addressed store of parse products for one repo root."""

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
        self.enabled = enabled
        self.hits = 0
        self.misses = 0
        self._epoch: str | None = None

    def stats(self) -> dict:
        """The hit/miss line, as it appears under ``index`` in ``--json`` output."""
        return {
            "dir": str(self.directory),
            "enabled": self.enabled,
            "hits": self.hits,
            "misses": self.misses,
        }

    @property
    def epoch(self) -> str:
        if self._epoch is None:
            self._epoch = epoch(self.root)
        return self._epoch

    def entry_name(self, path: Path) -> str:
        """The repo-name-qualified repo-relative name of *path*."""
        target = Path(path)
        try:
            relative = target.resolve().relative_to(self.root.resolve())
        except (OSError, ValueError):
            return str(target)
        return f"{self.root.resolve().name}/{relative.as_posix()}"

    def key(self, path: Path, *, sha: str | None = None) -> str | None:
        """The entry key for *path*, or ``None`` when its bytes cannot be read."""
        content = sha if sha is not None else _file_sha(Path(path))
        if content is None:
            return None
        return _sha(
            self.epoch.encode("utf-8"),
            self.entry_name(path).encode("utf-8"),
            content.encode("utf-8"),
        )

    def content_key(self, *material: str) -> str:
        """An entry key built from *material* alone — for a product no path identifies."""
        return _sha(self.epoch.encode("utf-8"), *(part.encode("utf-8") for part in material))

    def _entry_path(self, key: str) -> Path:
        return self.directory / key[:2] / key

    def get(self, path: Path, *, sha: str | None = None) -> Any | None:
        """The stored value for *path*, or ``None`` for any kind of miss."""
        return self.get_key(self.key(path, sha=sha))

    def get_key(self, key: str | None) -> Any | None:
        """The stored value under *key*, counted — for a caller that built its own key."""
        if not self.enabled:
            return None
        value = self._read(key)
        if value is None:
            self.misses += 1
        else:
            self.hits += 1
        return value

    def read_key(self, key: str | None) -> Any | None:
        """The stored value under *key* without counting it — for a caller that counts itself."""
        return self._read(key)

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
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get(_VERSION_KEY) != SCHEMA_VERSION:
            return None
        return payload.get(_PAYLOAD_KEY)

    def put(self, path: Path, value: Any, *, sha: str | None = None) -> None:
        """Store *value* for *path*, pruning past the age bound when a prune is due."""
        self.put_key(self.key(path, sha=sha), value)

    def put_key(self, key: str | None, value: Any) -> None:
        """Store *value* under *key* — for a caller that built its own key."""
        if not self.enabled:
            return
        if key is None:
            return
        self.prune()
        entry = self._entry_path(key)
        payload = {_VERSION_KEY: SCHEMA_VERSION, _PAYLOAD_KEY: value}
        try:
            entry.parent.mkdir(parents=True, exist_ok=True)
            temporary = entry.with_name(f"{entry.name}.{os.getpid()}.tmp")
            temporary.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
            os.replace(temporary, entry)
        except (OSError, pickle.PicklingError, TypeError, ValueError, RecursionError):
            return

    def prune(self, now: float | None = None) -> int:
        """Delete entries unwritten for longer than ``max_age_s``; return how many."""
        if self.max_age_s <= 0:
            return 0
        if not self._prune_is_due(now):
            return 0
        return clean(self.directory, max_age_s=self.max_age_s, now=now)

    def _prune_is_due(self, now: float | None = None) -> bool:
        """Whether a sweep may run, stamping the directory when it may."""
        moment = time.time() if now is None else now
        stamp = self.directory / PRUNE_STAMP_NAME
        try:
            if moment - stamp.stat().st_mtime < PRUNE_INTERVAL_S:
                return False
        except OSError:
            pass
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            stamp.touch()
            os.utime(stamp, (moment, moment))
        except OSError:
            return False
        return True


def clean(
    directory: Path | str,
    *,
    everything: bool = False,
    max_age_s: float = DEFAULT_MAX_AGE_S,
    now: float | None = None,
) -> int:
    """Delete index entries under *directory* and return how many went."""
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
            continue
        removed += 1
    for candidate in sorted(candidates, reverse=True):
        try:
            if candidate.is_dir():
                candidate.rmdir()
        except OSError:
            continue
    return removed


_ACTIVE: IndexStore | None = None


def active() -> IndexStore | None:
    """The store the enclosing :func:`session` opened, or ``None``."""
    return _ACTIVE


@contextmanager
def use(store: IndexStore) -> Iterator[IndexStore]:
    """Make an already-constructed *store* :func:`active` for the duration of a block."""
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
