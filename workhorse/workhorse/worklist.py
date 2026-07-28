"""A generic backlog/worklist primitive — one place a run is *aware of what it is
working through*, instead of every workflow re-deriving "select next / mark / prune /
how many remain" against its own bespoke store.

Like :mod:`workhorse.stack`, this is a **parameterised primitive that learns no
workflow's schema**: an item is ``{id, status, kind?, order?, payload?}`` and nothing
here knows a "story" from an "epic" from a "unit". A workflow names its own statuses
(via :class:`Scheme`) and its own category key; the primitive only sequences, counts,
and summarizes. Every function **returns a plain dict/list and never prints or exits** —
the thin ``script:``-node wrapper a workflow writes owns the JSON-to-stdout contract.

``kind`` is a first-class item field so **one worklist can hold every list a run
tracks** — epics, stories and fixes in a single store — and each operation scopes to one
type with ``kind=`` (``None`` = every kind). ``kind`` still names nothing: it is the
workflow's own label, the same way ``status`` is. A worklist that only ever holds one
kind simply leaves the field off and never passes ``kind=``.

Storage is pluggable through the tiny :class:`Backend` protocol so the source of truth
stays where it belongs: the built-in :class:`JsonBackend` covers a workflow whose queue
is a JSON file, while a workflow whose items live elsewhere (an ostler doc-graph, a
fenced markdown section) supplies its own backend from its own script code — keeping
that dependency out of the engine.

The point of one primitive is one telemetry story: :meth:`WorkList.snapshot` returns the
current item, the counts, and a ``progress`` string in a shape a workflow can drop
straight into its ``labels:``/``activity:`` context (Phase 1), so "reviewing PRED-A2JX ·
3/12" reaches the dashboard without each workflow re-counting.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol


@dataclass(frozen=True)
class Scheme:
    """Which status strings mean what, so a workflow keeps its own vocabulary. Any
    status outside these three sets is treated as *pending* (open, selectable)."""

    done: frozenset[str] = frozenset({"done"})
    active: frozenset[str] = frozenset({"active"})
    blocked: frozenset[str] = frozenset({"blocked"})


DEFAULT_SCHEME = Scheme()


def _ordered(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Items in working order. An explicit ``order`` key wins (stable within ties);
    otherwise the given sequence order is preserved — so a backend that already returns
    a dependency-sorted list is left exactly as it is."""
    seq = list(items)
    if any("order" in it for it in seq):
        return sorted(seq, key=lambda it: (it.get("order", 0),))
    return seq


def _of_kind(
    items: Iterable[dict[str, Any]], kind: str | None
) -> list[dict[str, Any]]:
    """The items of one ``kind``, or all of them when ``kind`` is ``None`` — the single
    filter that lets one worklist serve every list a run tracks. An item with no ``kind``
    field belongs to no named kind, so it is only ever returned by the unscoped view."""
    seq = list(items)
    if kind is None:
        return seq
    return [it for it in seq if it.get("kind") == kind]


def select_next(
    items: Iterable[dict[str, Any]],
    *,
    skip: Iterable[str] = (),
    scheme: Scheme = DEFAULT_SCHEME,
    kind: str | None = None,
) -> dict[str, Any] | None:
    """The first item to work, or ``None`` when the queue is drained.

    An already-**active** item is preferred (crash-safe re-pick: a run killed mid-item
    resumes the same one rather than skipping it), then the first **pending** item in
    order. ``done``, ``blocked`` and any id in ``skip`` (e.g. a per-run "exhausted its
    budget" set) are passed over. ``kind`` scopes the pick to one list in a mixed
    worklist (``None`` = every kind).
    """
    skip = set(skip)
    ordered = _ordered(_of_kind(items, kind))
    for it in ordered:
        if it.get("status") in scheme.active and it.get("id") not in skip:
            return it
    for it in ordered:
        status = it.get("status")
        if status in scheme.done or status in scheme.blocked:
            continue
        if it.get("id") in skip:
            continue
        return it
    return None


def counts(
    items: Iterable[dict[str, Any]],
    *,
    scheme: Scheme = DEFAULT_SCHEME,
    category_key: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    """A count breakdown of the queue, scoped to one ``kind`` (``None`` = every kind).

    ``by_category`` buckets the **not-done** items by ``payload[category_key]`` — this
    is the "N of category X, K of category Z" a dashboard shows; empty when no
    ``category_key`` is given. ``by_kind`` is the same breakdown over the first-class
    ``kind`` field — the natural composition of a mixed worklist ("5 epic · 30 story").
    ``remaining`` is not-done work; ``pending`` is the selectable subset (open and not
    blocked/active).
    """
    seq = _of_kind(items, kind)
    by_status: Counter[str] = Counter(str(it.get("status") or "") for it in seq)
    done = sum(by_status[s] for s in scheme.done)
    active = sum(by_status[s] for s in scheme.active)
    blocked = sum(by_status[s] for s in scheme.blocked)
    total = len(seq)
    by_category: dict[str, int] = {}
    if category_key:
        cat: Counter[str] = Counter(
            str((it.get("payload") or {}).get(category_key) or "")
            for it in seq
            if it.get("status") not in scheme.done
        )
        by_category = {k: v for k, v in cat.items() if k}
    kc: Counter[str] = Counter(
        str(it.get("kind") or "")
        for it in seq
        if it.get("status") not in scheme.done
    )
    by_kind = {k: v for k, v in kc.items() if k}
    return {
        "total": total,
        "done": done,
        "active": active,
        "blocked": blocked,
        "pending": total - done - active - blocked,
        "remaining": total - done,
        "by_status": dict(by_status),
        "by_category": by_category,
        "by_kind": by_kind,
    }


def _composition(by_category: dict[str, int]) -> str:
    """A compact, deterministic "5 ui · 3 api" line for a dashboard activity string."""
    return " · ".join(f"{n} {cat}" for cat, n in sorted(by_category.items()))


def snapshot(
    items: Iterable[dict[str, Any]],
    *,
    current: str | None = None,
    scheme: Scheme = DEFAULT_SCHEME,
    category_key: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    """One dict a workflow drops into its label/activity context: the current item id,
    the counts, a ``progress`` "done/total", a ``composition`` line, and a ``kinds`` line
    ("5 epic · 30 story") — the shape a dashboard reads uniformly no matter which workflow
    produced it. ``kind`` scopes it to one list in a mixed worklist (``None`` = every
    kind). Stateless twin of :meth:`WorkList.snapshot`, for a workflow whose store isn't a
    :class:`Backend` (it hands the items in directly). Nothing here names a verb — the
    workflow's ``activity:`` template supplies "reviewing"."""
    c = counts(items, scheme=scheme, category_key=category_key, kind=kind)
    return {
        "current": current or "",
        "progress": f"{c['done']}/{c['total']}",
        "remaining": c["remaining"],
        "composition": _composition(c["by_category"]),
        "kinds": _composition(c["by_kind"]),
        "counts": c,
    }


class Backend(Protocol):
    """Where a worklist's items live. Two methods, both plain data."""

    def load(self) -> list[dict[str, Any]]: ...

    def save(self, items: list[dict[str, Any]]) -> None: ...


@dataclass
class JsonBackend:
    """A worklist stored as a JSON array of items at ``path`` — the zero-dependency
    default. Writes are atomic (tmp + ``os.replace``) so a crash mid-save can never
    leave a half-written queue, mirroring ``ArtifactWriter.write_checkpoint``."""

    path: Path
    # The JSON key holding the item list, when the file is an object rather than a bare
    # array (lets a workflow keep sibling metadata in the same file). "" = bare array.
    items_key: str = ""

    def load(self) -> list[dict[str, Any]]:
        p = Path(self.path)
        if not p.exists():
            return []
        data = json.loads(p.read_text() or "[]")
        if self.items_key:
            data = data.get(self.items_key, [])
        return list(data or [])

    def save(self, items: list[dict[str, Any]]) -> None:
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if self.items_key:
            existing = json.loads(p.read_text()) if p.exists() else {}
            existing = existing if isinstance(existing, dict) else {}
            existing[self.items_key] = items
            payload: Any = existing
        else:
            payload = items
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, p)


@dataclass
class WorkList:
    """A worklist bound to a :class:`Backend`, with a :class:`Scheme` and optional
    ``category_key``. The methods are the mechanics every workflow re-implemented:
    select the next item, mark/prune one, count what remains, and snapshot the whole
    for telemetry."""

    backend: Backend
    scheme: Scheme = DEFAULT_SCHEME
    category_key: str | None = None

    def items(self, kind: str | None = None) -> list[dict[str, Any]]:
        """The stored items, optionally just those of one ``kind`` (``None`` = every
        kind) — the read side of holding many lists in one worklist."""
        return _of_kind(self.backend.load(), kind)

    def select_next(
        self, skip: Iterable[str] = (), kind: str | None = None
    ) -> dict[str, Any] | None:
        return select_next(
            self.backend.load(), skip=skip, scheme=self.scheme, kind=kind
        )

    def mark(self, item_id: str, status: str, kind: str | None = None) -> bool:
        """Set one item's status. Returns whether an item matched (so a caller can
        tell a real transition from a no-op typo). ``kind`` disambiguates an id that
        recurs across lists in a mixed worklist."""
        items = self.backend.load()
        hit = False
        for it in items:
            if it.get("id") == item_id and (kind is None or it.get("kind") == kind):
                it["status"] = status
                hit = True
        if hit:
            self.backend.save(items)
        return hit

    def prune(self, item_id: str, kind: str | None = None) -> bool:
        """Drop one item entirely. Returns whether anything was removed. ``kind``
        disambiguates an id that recurs across lists in a mixed worklist."""
        items = self.backend.load()
        kept = [
            it
            for it in items
            if not (
                it.get("id") == item_id and (kind is None or it.get("kind") == kind)
            )
        ]
        if len(kept) != len(items):
            self.backend.save(kept)
            return True
        return False

    def counts(self, kind: str | None = None) -> dict[str, Any]:
        return counts(
            self.backend.load(),
            scheme=self.scheme,
            category_key=self.category_key,
            kind=kind,
        )

    def snapshot(
        self, current: str | None = None, kind: str | None = None
    ) -> dict[str, Any]:
        """This worklist's :func:`snapshot` — the label/activity-ready dict, scoped to one
        ``kind`` (``None`` = every kind). See the module-level function; this just binds it
        to the backend's current items."""
        return snapshot(
            self.backend.load(),
            current=current,
            scheme=self.scheme,
            category_key=self.category_key,
            kind=kind,
        )
