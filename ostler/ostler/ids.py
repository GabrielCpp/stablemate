"""Id allocation — ostler owns ``.agents/ids.json`` (subsumes the workflow's allocate-ids script).

An id is ``<PREFIX>-<ULID>``: a per-repo prefix (the first 4 letters of the CWD repo name,
uppercased, pinned in the registry) followed by a **monotonic ULID** — a 48-bit millisecond
timestamp plus 80 bits of randomness, Crockford Base32 (26 chars). ULIDs are lexicographically
sortable by creation time, globally unique, and mint **without any coordination** — so concurrent
worktrees, processes, and clones never collide and there is no counter to lock, merge, or serialize.
(This replaced a ``<prefix>-<n>`` counter, which was a central-authority sequence that could not be
distributed across worktrees; earlier ``ACME-42``-style ids keep working — an id is just an opaque,
sortable string.)

For readability a **short handle** — ``<PREFIX>-<slice of a hash of the ULID>`` — abbreviates an id
git-style: the shortest slice that is unambiguous among the current ids, lengthened on collision and
resolved back with :func:`expand`. The slice is of a *hash* of the ULID, not of the id itself,
precisely because monotonic ids minted in one millisecond differ only in their low bits — hashing
decorrelates them, so even a burst of ids gets short, well-spread handles. Handles are for
display/input only; ordering always lives on the full id.

**Where handles apply.** :func:`known` is the universe a handle is unambiguous within — every id
written down anywhere in the tree — so a handle printed by one command resolves in the next.
:func:`resolve` accepts a handle wherever ostler takes an id, *always*: that costs nothing and a
caller that pasted a full id is unaffected. Rendering is the side with a choice, and :func:`table`
plus :func:`shorten` are what the CLI renders through — see ``cli.py``'s ``--handles`` /
``--full-ids``. A handle is unstable by construction (it lengthens when a later id collides with
it), which is why it is never what gets *written* into a document.

The registry is ``{prefix, frozen}``; ``frozen`` (freeze.py / doctor.py) is unaffected.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections.abc import Iterable
from pathlib import Path

from ostler import backlog
from ostler.model import Graph

# Crockford Base32, in ASCII order (0-9 then A-Z minus I, L, O, U) so a raw string sort == value
# sort — the property that makes a ULID lexicographically increasing.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_TIME_LEN = 10   # chars encoding the 48-bit millisecond timestamp
_RAND_LEN = 16   # chars encoding the 80-bit randomness (the "tail")
ULID_LEN = _TIME_LEN + _RAND_LEN
HANDLE_MIN = 6   # default short-handle tail length (git-style abbreviation floor)

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
    """A monotonic ULID (26 chars, uppercase Crockford Base32): 48-bit ms time + 80-bit random.

    Strictly increasing within this process — within one millisecond (or if the clock steps back)
    the timestamp is held non-decreasing and the random field is incremented, so the id still climbs.
    Across processes the timestamp orders them, with no shared state to coordinate.
    """
    global _last_ms, _last_rand
    with _mono_lock:
        ms = int(time.time() * 1000)
        if ms > _last_ms:
            _last_ms = ms
            _last_rand = int.from_bytes(os.urandom(10), "big")
        else:
            _last_rand += 1
            if _last_rand >> (_RAND_LEN * 5):      # 80-bit random overflowed (never, in practice)
                _last_ms += 1
                _last_rand = int.from_bytes(os.urandom(10), "big")
        return _b32(_last_ms, _TIME_LEN) + _b32(_last_rand, _RAND_LEN)


def allocate(graph: Graph, prefix: str | None = None) -> str:
    """Mint the next id: ``<PREFIX>-<ULID>``. Coordination-free — no counter, no lock, no file write
    per call (the prefix is pinned once by :func:`ensure`; the ULID needs no persisted state)."""
    return f"{ensure(graph, prefix)['prefix']}-{new_ulid()}"


def _split(identifier: str) -> tuple[str, str]:
    """(prefix, ulid) for an id; ('', id) for a legacy/prefixless one. Only the ULID's random tail
    is meaningful for handles, so a legacy ``ACME-42`` simply has no usable tail."""
    prefix, _, rest = identifier.partition("-")
    return (prefix, rest) if rest else ("", identifier)


_FP_LEN = 16  # Crockford chars of hash fingerprint (80 bits) a handle may slice from


def _fingerprint(identifier: str) -> str:
    """A well-distributed Crockford-Base32 hash of the id's ULID — the space a handle slices from.

    Hashing (not slicing the id itself) is what keeps handles short for a burst: two monotonic ids
    from the same millisecond differ by one bit, but their hashes are entirely different. A legacy /
    prefixless id has no ULID and returns '' (no hashable handle → it stays whole)."""
    ulid = _split(identifier)[1]
    if len(ulid) != ULID_LEN:
        return ""
    digest = hashlib.blake2b(ulid.encode(), digest_size=10).digest()
    return _b32(int.from_bytes(digest, "big"), _FP_LEN)


def abbreviate(identifier: str, existing: Iterable[str], min_len: int = HANDLE_MIN) -> str:
    """The short handle for ``identifier``: ``<PREFIX>-<fingerprint slice>``, the shortest slice
    (≥min_len) unambiguous among ``existing`` — git-style. Falls back to the full id when it has no
    ULID (a legacy counter id)."""
    prefix, _ = _split(identifier)
    fp = _fingerprint(identifier)
    if not fp:
        return identifier
    others = [f for f in (_fingerprint(o) for o in existing if o != identifier) if f]
    for length in range(max(min_len, 1), _FP_LEN + 1):
        slice_ = fp[:length]
        if not any(o.startswith(slice_) for o in others):
            return f"{prefix}-{slice_}" if prefix else slice_
    return identifier  # fully ambiguous only if a duplicate id exists — return the id itself


def expand(handle: str, existing: Iterable[str]) -> str | None:
    """Resolve a short handle back to its full id. Returns the id, or None if it matches zero or
    (ambiguously) more than one. An exact full id passes straight through."""
    ids = list(existing)
    if handle in ids:
        return handle
    prefix, _, slice_ = handle.partition("-")
    if not slice_:
        return None
    matches = [i for i in ids
               if _split(i)[0] == prefix and _fingerprint(i).startswith(slice_) and _fingerprint(i)]
    return matches[0] if len(matches) == 1 else None


# ---------------------------------------------------------------------------
# The graph's ids: one universe to abbreviate within and resolve against
# ---------------------------------------------------------------------------
def known(graph: Graph) -> list[str]:
    """Every minted id currently written down in the tree, sorted.

    The universe matters more than it looks: an abbreviation is only unambiguous *relative to a
    set*, so a handle printed by `list` resolves in `seed remove` only if both commands ask the
    same question. Collecting from the whole graph — not from the rows one command happens to be
    holding — is what makes the handle a token you can copy from any output into any input.
    """
    out: set[str] = set()
    for epic in graph.epics:
        out.add(epic.eid)
        out.update(s.id for s in epic.seeds)
        out.update(s.eid for s in epic.stories)
    out.update(str(f.data.get("id") or "") for f in graph.features)
    # The backlog is markdown ostler manages but does not load into the graph, and its ids are
    # exactly the ones a person retypes most (`backlog prune <id>`) — so they are in the universe.
    out.update(i for i, _ in backlog.items(graph))
    out.discard("")
    return sorted(out)


def table(existing: Iterable[str], min_len: int = HANDLE_MIN) -> dict[str, str]:
    """``{id: handle}`` for every id in *existing* — :func:`abbreviate` for a whole set at once.

    Batched because the per-id call re-hashes every other id to find its shortest unambiguous
    slice; over a few hundred ids that is quadratic for an answer the whole set shares.
    """
    ids = [i for i in existing if i]
    fps = {i: _fingerprint(i) for i in ids}
    out: dict[str, str] = {}
    for identifier in ids:
        fp = fps[identifier]
        if not fp:
            out[identifier] = identifier   # legacy/prefixless: nothing to abbreviate
            continue
        others = [f for i, f in fps.items() if i != identifier and f]
        prefix = _split(identifier)[0]
        for length in range(max(min_len, 1), _FP_LEN + 1):
            slice_ = fp[:length]
            if not any(o.startswith(slice_) for o in others):
                out[identifier] = f"{prefix}-{slice_}" if prefix else slice_
                break
        else:
            out[identifier] = identifier   # only reachable if the same id is listed twice
    return out


#: An id as it appears inside free text: a prefix, a hyphen, and a full 26-char ULID. Narrow on
#: purpose — :func:`shorten` rewrites *matches of this*, never arbitrary substrings, so a body of
#: prose or a path that merely contains a hyphen is left exactly as it was.
_ID_TOKEN = re.compile(rf"\b[A-Za-z][A-Za-z0-9_]{{0,15}}-[{_CROCKFORD}]{{{ULID_LEN}}}\b")


def shorten(data, handles: dict[str, str]):
    """*data* with every id in *handles* replaced by its handle, in strings and inside containers.

    Works on a JSON row, a list of them, or a line of human output alike, so the CLI has one
    rendering seam rather than a per-command list of which keys hold an id. Keys are left alone:
    a mapping keyed by id (the freeze registry) still reads back by id.
    """
    if isinstance(data, str):
        return _ID_TOKEN.sub(lambda m: handles.get(m.group(0), m.group(0)), data)
    if isinstance(data, dict):
        return {k: shorten(v, handles) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [shorten(v, handles) for v in data]
    return data


def resolve(graph: Graph, token: str) -> str:
    """*token* as a full id: a handle is expanded, anything else is returned untouched.

    Untouched rather than rejected because ostler's id arguments are rarely *only* ids — the same
    argument takes a story slug or a doc path — and a lookup that cannot find a handle has no
    standing to declare the caller wrong. The caller's own "not found" is the better error.
    """
    if not token:
        return token
    return expand(token, known(graph)) or token
