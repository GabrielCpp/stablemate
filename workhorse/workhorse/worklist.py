"""A generic backlog/worklist primitive — one place a run is *aware of what it is
working through*, instead of every workflow re-deriving "select next / mark / prune /
how many remain" against its own bespoke store.

Like :mod:`workhorse.stack`, this is a **parameterised primitive that learns no
workflow's schema**: an item is a :class:`WorkItem` — ``id``, ``status``, ``kind``,
``order``, ``payload``, plus whatever else the workflow's own file carries — and nothing
here knows a "story" from an "epic" from a "unit". A workflow names its own statuses
(via :class:`Scheme`) and its own category key; the primitive only sequences, counts,
and summarizes. Every function **returns a value and never prints or exits** — the thin
node wrapper a workflow writes owns the JSON-to-stdout contract.

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
straight into its ``labels:``/``activity:`` context (Phase 1), so "reviewing ACME-A2JX ·
3/12" reaches the dashboard without each workflow re-counting.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field


class WorkItem(BaseModel):
    """One unit of work on a worklist — the type :class:`Backend` speaks.

    A worklist is read from JSON on disk *and* from whatever store a workflow supplies
    its own :class:`Backend` for, so an item is genuinely outside data and is parsed,
    not trusted. Naming it is also what keeps the port honest: ``load() ->
    list[dict[str, Any]]`` named no type at all, so every implementer invented its own
    item shape and no two agreed.

    Every field is optional because the primitive still learns no workflow's schema — a
    worklist holding one kind leaves ``kind`` off; a store keyed by its own field (okf's
    ``(kind, target)``) leaves ``id`` off. ``extra="allow"`` is the same decision: the
    workflow's fields (``path``, ``target``, ``context``) ride **top-level** where its
    file already puts them, and :meth:`Backend.save` writes back only the keys that were
    set — the file is the workflow's, not workhorse's to reshape.
    """

    model_config = ConfigDict(extra="allow")

    id: str = ""
    status: str = ""
    kind: str = ""
    order: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkCounts:
    """The count breakdown of a queue — see :func:`counts` for what each bucket means."""

    total: int
    done: int
    active: int
    blocked: int
    pending: int
    remaining: int
    by_status: dict[str, int]
    by_category: dict[str, int]
    by_kind: dict[str, int]


@dataclass(frozen=True, slots=True)
class WorkSnapshot:
    """The label/activity-ready summary — see :func:`snapshot`.

    This is the telemetry contract: the shape a dashboard reads uniformly no matter which
    workflow produced it. In-memory only — a workflow renders it into its own labels and
    nothing writes it to disk — so a frozen record, not a model.
    """

    current: str
    progress: str
    remaining: int
    composition: str
    kinds: str
    counts: WorkCounts


@dataclass(frozen=True)
class Scheme:
    """Which status strings mean what, so a workflow keeps its own vocabulary. Any
    status outside these three sets is treated as *pending* (open, selectable)."""

    done: frozenset[str] = frozenset({"done"})
    active: frozenset[str] = frozenset({"active"})
    blocked: frozenset[str] = frozenset({"blocked"})


DEFAULT_SCHEME = Scheme()


def _ordered(items: Iterable[WorkItem]) -> list[WorkItem]:
    """Items in working order. An explicit ``order`` wins (stable within ties);
    otherwise the given sequence order is preserved — so a backend that already returns
    a dependency-sorted list is left exactly as it is."""
    seq = list(items)
    if any(it.order is not None for it in seq):
        return sorted(seq, key=lambda it: (it.order or 0,))
    return seq


def _of_kind(items: Iterable[WorkItem], kind: str | None) -> list[WorkItem]:
    """The items of one ``kind``, or all of them when ``kind`` is ``None`` — the single
    filter that lets one worklist serve every list a run tracks. An item with no ``kind``
    belongs to no named kind, so it is only ever returned by the unscoped view."""
    seq = list(items)
    if kind is None:
        return seq
    return [it for it in seq if it.kind == kind]


def select_next(
    items: Iterable[WorkItem],
    *,
    skip: Iterable[str] = (),
    scheme: Scheme = DEFAULT_SCHEME,
    kind: str | None = None,
) -> WorkItem | None:
    """The first item to work, or ``None`` when the queue is drained.

    An already-**active** item is preferred (crash-safe re-pick: a run killed mid-item
    resumes the same one rather than skipping it), then the first **pending** item in
    order. ``done``, ``blocked`` and any id in ``skip`` (e.g. a per-run "exhausted its
    budget" set) are passed over. ``kind`` scopes the pick to one list in a mixed
    worklist (``None`` = every kind).
    """
    skipped = set(skip)
    ordered = _ordered(_of_kind(items, kind))
    for it in ordered:
        if it.status in scheme.active and it.id not in skipped:
            return it
    for it in ordered:
        if it.status in scheme.done or it.status in scheme.blocked:
            continue
        if it.id in skipped:
            continue
        return it
    return None


def counts(
    items: Iterable[WorkItem],
    *,
    scheme: Scheme = DEFAULT_SCHEME,
    category_key: str | None = None,
    kind: str | None = None,
) -> WorkCounts:
    """A count breakdown of the queue, scoped to one ``kind`` (``None`` = every kind).

    ``by_category`` buckets the **not-done** items by ``payload[category_key]`` — this
    is the "N of category X, K of category Z" a dashboard shows; empty when no
    ``category_key`` is given. ``by_kind`` is the same breakdown over the first-class
    ``kind`` field — the natural composition of a mixed worklist ("5 epic · 30 story").
    ``remaining`` is not-done work; ``pending`` is the selectable subset (open and not
    blocked/active).
    """
    seq = _of_kind(items, kind)
    by_status: Counter[str] = Counter(it.status for it in seq)
    done = sum(by_status[s] for s in scheme.done)
    active = sum(by_status[s] for s in scheme.active)
    blocked = sum(by_status[s] for s in scheme.blocked)
    total = len(seq)
    by_category: dict[str, int] = {}
    if category_key:
        cat: Counter[str] = Counter(
            str(it.payload.get(category_key) or "")
            for it in seq
            if it.status not in scheme.done
        )
        by_category = {k: v for k, v in cat.items() if k}
    kc: Counter[str] = Counter(
        it.kind for it in seq if it.status not in scheme.done
    )
    by_kind = {k: v for k, v in kc.items() if k}
    return WorkCounts(
        total=total,
        done=done,
        active=active,
        blocked=blocked,
        pending=total - done - active - blocked,
        remaining=total - done,
        by_status=dict(by_status),
        by_category=by_category,
        by_kind=by_kind,
    )


def _composition(by_category: dict[str, int]) -> str:
    """A compact, deterministic "5 ui · 3 api" line for a dashboard activity string."""
    return " · ".join(f"{n} {cat}" for cat, n in sorted(by_category.items()))


def snapshot(
    items: Iterable[WorkItem],
    *,
    current: str | None = None,
    scheme: Scheme = DEFAULT_SCHEME,
    category_key: str | None = None,
    kind: str | None = None,
) -> WorkSnapshot:
    """One record a workflow drops into its label/activity context: the current item id,
    the counts, a ``progress`` "done/total", a ``composition`` line, and a ``kinds`` line
    ("5 epic · 30 story") — the shape a dashboard reads uniformly no matter which workflow
    produced it. ``kind`` scopes it to one list in a mixed worklist (``None`` = every
    kind). Stateless twin of :meth:`WorkList.snapshot`, for a workflow whose store isn't a
    :class:`Backend` (it hands the items in directly). Nothing here names a verb — the
    workflow's ``activity:`` template supplies "reviewing"."""
    c = counts(items, scheme=scheme, category_key=category_key, kind=kind)
    return WorkSnapshot(
        current=current or "",
        progress=f"{c.done}/{c.total}",
        remaining=c.remaining,
        composition=_composition(c.by_category),
        kinds=_composition(c.by_kind),
        counts=c,
    )


class Backend(Protocol):
    """Where a worklist's items live. Two methods, both speaking :class:`WorkItem`."""

    def load(self) -> list[WorkItem]: ...

    def save(self, items: Sequence[WorkItem]) -> None: ...


@dataclass
class JsonBackend:
    """A worklist stored as a JSON array of items at ``path`` — the zero-dependency
    default. Writes are atomic (tmp + ``os.replace``) so a crash mid-save can never
    leave a half-written queue, mirroring ``ArtifactWriter.write_checkpoint``."""

    path: Path
    # The JSON key holding the item list, when the file is an object rather than a bare
    # array (lets a workflow keep sibling metadata in the same file). "" = bare array.
    items_key: str = ""

    def load(self) -> list[WorkItem]:
        p = Path(self.path)
        if not p.exists():
            return []
        data = json.loads(p.read_text() or "[]")
        if self.items_key:
            data = data.get(self.items_key, [])
        return [WorkItem.model_validate(d) for d in (data or [])]

    def save(self, items: Sequence[WorkItem]) -> None:
        # `exclude_unset` so a round trip adds nothing: the file belongs to the workflow,
        # and writing back this model's defaults would stamp `"order": null` and an empty
        # `payload` onto every item the workflow never gave one.
        rows = [it.model_dump(exclude_unset=True) for it in items]
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if self.items_key:
            existing = json.loads(p.read_text()) if p.exists() else {}
            existing = existing if isinstance(existing, dict) else {}
            existing[self.items_key] = rows
            payload: Any = existing
        else:
            payload = rows
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

    def items(self, kind: str | None = None) -> list[WorkItem]:
        """The stored items, optionally just those of one ``kind`` (``None`` = every
        kind) — the read side of holding many lists in one worklist."""
        return _of_kind(self.backend.load(), kind)

    def select_next(
        self, skip: Iterable[str] = (), kind: str | None = None
    ) -> WorkItem | None:
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
            if it.id == item_id and (kind is None or it.kind == kind):
                it.status = status
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
            if not (it.id == item_id and (kind is None or it.kind == kind))
        ]
        if len(kept) != len(items):
            self.backend.save(kept)
            return True
        return False

    def counts(self, kind: str | None = None) -> WorkCounts:
        return counts(
            self.backend.load(),
            scheme=self.scheme,
            category_key=self.category_key,
            kind=kind,
        )

    def snapshot(
        self, current: str | None = None, kind: str | None = None
    ) -> WorkSnapshot:
        """This worklist's :func:`snapshot` — the label/activity-ready record, scoped to one
        ``kind`` (``None`` = every kind). See the module-level function; this just binds it
        to the backend's current items."""
        return snapshot(
            self.backend.load(),
            current=current,
            scheme=self.scheme,
            category_key=self.category_key,
            kind=kind,
        )
