"""Id allocation — ostler owns ``.agents/ids.json`` (subsumes the workflow's allocate-ids script)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ostler import backlog
from ostler.model import Graph

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_TIME_LEN = 10
_RAND_LEN = 16
ULID_LEN = _TIME_LEN + _RAND_LEN
HANDLE_MIN = 6

_mono_lock = threading.Lock()
_last_ms = -1
_last_rand = 0


def path_for(graph: Graph) -> Path:
    return graph.root / ".agents" / "ids.json"


def load(graph: Graph) -> dict | None:
    if graph.ids is not None:
        return dict(graph.ids)
    p = path_for(graph)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return None
    return None


def save(graph: Graph, ids: dict) -> None:
    p = path_for(graph)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ids, indent=2) + "\n", encoding="utf-8")
    graph.ids = ids


def _repo_prefix(graph: Graph) -> str:
    """Derived id prefix: the first 4 letters of the CWD repo's name, uppercased."""
    letters = re.sub(r"[^A-Za-z0-9]", "", graph.root.name)
    return (letters[:4] or "REPO").upper()


def ensure(graph: Graph, prefix: str | None = None) -> dict:
    """Return the registry, creating it if absent (prefix derived from the repo name, then pinned)."""
    ids = load(graph)
    if ids is not None:
        return ids
    ids = {"prefix": prefix or _repo_prefix(graph)}
    save(graph, ids)
    return ids


def _b32(value: int, length: int) -> str:
    out = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        out.append(_CROCKFORD[rem])
    return "".join(reversed(out))


def new_ulid() -> str:
    """A monotonic ULID (26 chars, uppercase Crockford Base32): 48-bit ms time + 80-bit random."""
    global _last_ms, _last_rand
    with _mono_lock:
        ms = int(time.time() * 1000)
        if ms > _last_ms:
            _last_ms = ms
            _last_rand = int.from_bytes(os.urandom(10), "big")
        else:
            _last_rand += 1
            if _last_rand >> (_RAND_LEN * 5):
                _last_ms += 1
                _last_rand = int.from_bytes(os.urandom(10), "big")
        return _b32(_last_ms, _TIME_LEN) + _b32(_last_rand, _RAND_LEN)


def allocate(graph: Graph, prefix: str | None = None) -> str:
    """Mint the next id: ``<PREFIX>-<ULID>``."""
    return f"{ensure(graph, prefix)['prefix']}-{new_ulid()}"


def _split(identifier: str) -> tuple[str, str]:
    """(prefix, ulid) for an id; ('', id) for a legacy/prefixless one."""
    prefix, _, rest = identifier.partition("-")
    return (prefix, rest) if rest else ("", identifier)


_FP_LEN = 16


def _fingerprint(identifier: str) -> str:
    """A well-distributed Crockford-Base32 hash of the id's ULID — the space a handle slices from."""
    ulid = _split(identifier)[1]
    if len(ulid) != ULID_LEN:
        return ""
    digest = hashlib.blake2b(ulid.encode(), digest_size=10).digest()
    return _b32(int.from_bytes(digest, "big"), _FP_LEN)


def abbreviate(identifier: str, existing: Iterable[str], min_len: int = HANDLE_MIN) -> str:
    """The short handle for ``identifier``: ``<PREFIX>-<fingerprint slice>``, the shortest slice (≥min_len) unambiguous among ``existing`` — git-style."""
    prefix, _ = _split(identifier)
    fp = _fingerprint(identifier)
    if not fp:
        return identifier
    others = [f for f in (_fingerprint(o) for o in existing if o != identifier) if f]
    for length in range(max(min_len, 1), _FP_LEN + 1):
        slice_ = fp[:length]
        if not any(o.startswith(slice_) for o in others):
            return f"{prefix}-{slice_}" if prefix else slice_
    return identifier


def expand(handle: str, existing: Iterable[str]) -> str | None:
    """Resolve a short handle back to its full id."""
    ids = list(existing)
    if handle in ids:
        return handle
    prefix, _, slice_ = handle.partition("-")
    if not slice_:
        return None
    matches = [i for i in ids
               if _split(i)[0] == prefix and _fingerprint(i).startswith(slice_) and _fingerprint(i)]
    return matches[0] if len(matches) == 1 else None


def known(graph: Graph) -> list[str]:
    """Every minted id currently written down in the tree, sorted."""
    out: set[str] = set()
    for epic in graph.epics:
        out.add(epic.eid)
        out.update(s.id for s in epic.seeds)
        out.update(s.eid for s in epic.stories)
    for milestone in graph.milestones:
        out.add(milestone.eid)
        out.update(milestone.source_items)
    out.update(str(f.data.get("id") or "") for f in graph.features)
    out.update(i for i, _ in backlog.items(graph))
    out.discard("")
    return sorted(out)


def table(existing: Iterable[str], min_len: int = HANDLE_MIN) -> dict[str, str]:
    """``{id: handle}`` for every id in *existing* — :func:`abbreviate` for a whole set at once."""
    ids = [i for i in existing if i]
    fps = {i: _fingerprint(i) for i in ids}
    out: dict[str, str] = {}
    for identifier in ids:
        fp = fps[identifier]
        if not fp:
            out[identifier] = identifier
            continue
        others = [f for i, f in fps.items() if i != identifier and f]
        prefix = _split(identifier)[0]
        for length in range(max(min_len, 1), _FP_LEN + 1):
            slice_ = fp[:length]
            if not any(o.startswith(slice_) for o in others):
                out[identifier] = f"{prefix}-{slice_}" if prefix else slice_
                break
        else:
            out[identifier] = identifier
    return out


_ID_TOKEN = re.compile(rf"\b[A-Za-z][A-Za-z0-9_]{{0,15}}-[{_CROCKFORD}]{{{ULID_LEN}}}\b")


def shorten(data: Any, handles: dict[str, str]) -> Any:
    """*data* with every id in *handles* replaced by its handle, in strings and inside containers."""
    if isinstance(data, str):
        return _ID_TOKEN.sub(lambda m: handles.get(m.group(0), m.group(0)), data)
    if isinstance(data, dict):
        return {k: shorten(v, handles) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [shorten(v, handles) for v in data]
    return data


def resolve(graph: Graph, token: str) -> str:
    """*token* as a full id: a handle is expanded, anything else is returned untouched."""
    if not token:
        return token
    return expand(token, known(graph)) or token
