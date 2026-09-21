"""A generic backlog/worklist primitive — one place a run is *aware of what it is working through*, instead of every workflow re-deriving "select next / mark / prune / how many remain" against its own bespoke store."""
from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field


class WorkItem(BaseModel):
    """One unit of work on a worklist — the type :class:`Backend` speaks."""

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
    """The label/activity-ready summary — see :func:`snapshot`."""

    current: str
    progress: str
    remaining: int
    composition: str
    kinds: str
    counts: WorkCounts


@dataclass(frozen=True)
class Scheme:
    """Which status strings mean what, so a workflow keeps its own vocabulary."""

    done: frozenset[str] = frozenset({"done"})
    active: frozenset[str] = frozenset({"active"})
    blocked: frozenset[str] = frozenset({"blocked"})


DEFAULT_SCHEME = Scheme()


def _ordered(items: Iterable[WorkItem]) -> list[WorkItem]:
    """Items in working order."""
    seq = list(items)
    if any(it.order is not None for it in seq):
        return sorted(seq, key=lambda it: (it.order or 0,))
    return seq


def _of_kind(items: Iterable[WorkItem], kind: str | None) -> list[WorkItem]:
    """The items of one ``kind``, or all of them when ``kind`` is ``None`` — the single filter that lets one worklist serve every list a run tracks."""
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
    """The first item to work, or ``None`` when the queue is drained."""
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
    """A count breakdown of the queue, scoped to one ``kind`` (``None`` = every kind)."""
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
    """One record a workflow drops into its label/activity context: the current item id, the counts, a ``progress`` "done/total", a ``composition`` line, and a ``kinds`` line ("5 epic · 30 story") — the shape a dashboard reads uniformly no matter which workflow produced it."""
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
    """Where a worklist's items live."""

    def load(self) -> list[WorkItem]: ...

    def save(self, items: Sequence[WorkItem]) -> None: ...


@dataclass
class JsonBackend:
    """A worklist stored as a JSON array of items at ``path`` — the zero-dependency default."""

    path: Path
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
    """A worklist bound to a :class:`Backend`, with a :class:`Scheme` and optional ``category_key``."""

    backend: Backend
    scheme: Scheme = DEFAULT_SCHEME
    category_key: str | None = None

    def items(self, kind: str | None = None) -> list[WorkItem]:
        """The stored items, optionally just those of one ``kind`` (``None`` = every kind) — the read side of holding many lists in one worklist."""
        return _of_kind(self.backend.load(), kind)

    def select_next(
        self, skip: Iterable[str] = (), kind: str | None = None
    ) -> WorkItem | None:
        return select_next(
            self.backend.load(), skip=skip, scheme=self.scheme, kind=kind
        )

    def mark(self, item_id: str, status: str, kind: str | None = None) -> bool:
        """Set one item's status."""
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
        """Drop one item entirely."""
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
        """This worklist's :func:`snapshot` — the label/activity-ready record, scoped to one ``kind`` (``None`` = every kind)."""
        return snapshot(
            self.backend.load(),
            current=current,
            scheme=self.scheme,
            category_key=self.category_key,
            kind=kind,
        )
