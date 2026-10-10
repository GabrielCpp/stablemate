"""A generic backlog/worklist primitive — one place a run is *aware of what it is working through*, instead of every workflow re-deriving "select next / mark / prune / how many remain" against its own bespoke store."""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from collections.abc import Collection, Iterable, Iterator, Sequence
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class WorkItem(BaseModel):
    """One unit of work on a worklist — the type :class:`Backend` speaks."""

    model_config = ConfigDict(extra="allow")

    id: str = ""
    status: str = ""
    kind: str = ""
    order: int | float | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    digest: str = ""
    laps: int = 0


KindFilter = str | Collection[str] | None


class DigestMismatch(ValueError):
    """A stored item whose content no longer matches the digest it was filed with."""


def payload_digest(item: WorkItem) -> str:
    """The sha256 of an item's content: its id, kind, payload and extra fields, never its status, order, laps or digest."""
    content: dict[str, Any] = dict(item.model_extra or {})
    content.update(id=item.id, kind=item.kind, payload=item.payload)
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify(items: Iterable[WorkItem]) -> None:
    """Raise :class:`DigestMismatch` on the first item whose non-empty digest does not match its content."""
    for it in items:
        if it.digest and it.digest != payload_digest(it):
            raise DigestMismatch(f"work item {it.id!r} was edited after it was filed")


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


def _kinds(kind: KindFilter) -> frozenset[str] | None:
    """The set of kinds a filter names, or ``None`` for every kind."""
    if kind is None:
        return None
    if isinstance(kind, str):
        return frozenset({kind})
    return frozenset(kind)


def _of_kind(items: Iterable[WorkItem], kind: KindFilter) -> list[WorkItem]:
    """The items of one ``kind`` or a collection of kinds, or all of them when ``kind`` is ``None`` — the single filter that lets one worklist serve every list a run tracks."""
    seq = list(items)
    wanted = _kinds(kind)
    if wanted is None:
        return seq
    return [it for it in seq if it.kind in wanted]


def _candidates(
    items: Iterable[WorkItem],
    *,
    skip: Iterable[str] = (),
    scheme: Scheme = DEFAULT_SCHEME,
    kind: KindFilter = None,
    strict: bool = False,
) -> Iterator[WorkItem]:
    """Every item worth working, in working order — the ones already active first, so a run that crashed mid-item resumes on it rather than opening a second front.

    ``strict`` keeps the sequence: a pending item is a candidate only when every item before it is done.
    """
    skipped = set(skip)
    ordered = _ordered(_of_kind(items, kind))
    yield from (
        it for it in ordered if it.status in scheme.active and it.id not in skipped
    )
    if strict:
        first_open = next((it for it in ordered if it.status not in scheme.done), None)
        if (
            first_open is not None
            and first_open.status not in scheme.active
            and first_open.status not in scheme.blocked
            and first_open.id not in skipped
        ):
            yield first_open
        return
    yield from (
        it
        for it in ordered
        if it.status not in scheme.active
        and it.status not in scheme.done
        and it.status not in scheme.blocked
        and it.id not in skipped
    )


def select_next(
    items: Iterable[WorkItem],
    *,
    skip: Iterable[str] = (),
    scheme: Scheme = DEFAULT_SCHEME,
    kind: KindFilter = None,
    strict: bool = False,
) -> WorkItem | None:
    """The first item to work, or ``None`` when the queue is drained."""
    return next(
        _candidates(items, skip=skip, scheme=scheme, kind=kind, strict=strict), None
    )


def claim(
    items: Iterable[WorkItem],
    n: int,
    *,
    skip: Iterable[str] = (),
    scheme: Scheme = DEFAULT_SCHEME,
    kind: KindFilter = None,
    strict: bool = False,
) -> list[WorkItem]:
    """The next ``n`` items to work, or fewer when the queue is shorter than that — :func:`select_next` widened to a chunk, off the one ordering both read."""
    if n <= 0:
        return []
    return list(
        islice(
            _candidates(items, skip=skip, scheme=scheme, kind=kind, strict=strict), n
        )
    )


def counts(
    items: Iterable[WorkItem],
    *,
    scheme: Scheme = DEFAULT_SCHEME,
    category_key: str | None = None,
    kind: KindFilter = None,
) -> WorkCounts:
    """A count breakdown of the queue, scoped to one ``kind`` or a collection of kinds (``None`` = every kind)."""
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
    kind: KindFilter = None,
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
    """A worklist bound to a :class:`Backend`, with a :class:`Scheme` and optional ``category_key``.

    Every read verifies the stored digests, so an item whose content was edited after it was filed raises :class:`DigestMismatch`.
    """

    backend: Backend
    scheme: Scheme = DEFAULT_SCHEME
    category_key: str | None = None

    def _load(self) -> list[WorkItem]:
        items = self.backend.load()
        verify(items)
        return items

    def items(self, kind: KindFilter = None) -> list[WorkItem]:
        """The stored items, optionally just those of some kinds (``None`` = every kind) — the read side of holding many lists in one worklist."""
        return _of_kind(self._load(), kind)

    def add(self, items: Iterable[WorkItem]) -> list[WorkItem]:
        """File new items after the stored ones, each stamped with its digest, in one write; an id already stored or repeated in the batch raises ``ValueError`` and writes nothing."""
        stored = self._load()
        seen = {it.id for it in stored}
        batch = list(items)
        for it in batch:
            if it.id in seen:
                raise ValueError(f"work item {it.id!r} is already on the list")
            seen.add(it.id)
        for it in batch:
            it.digest = payload_digest(it)
        if batch:
            self.backend.save([*stored, *batch])
        return batch

    def select_next(
        self, skip: Iterable[str] = (), kind: KindFilter = None, strict: bool = False
    ) -> WorkItem | None:
        return select_next(
            self._load(), skip=skip, scheme=self.scheme, kind=kind, strict=strict
        )

    def claim(
        self,
        n: int,
        *,
        kind: KindFilter = None,
        skip: Iterable[str] = (),
        status: str = "active",
        strict: bool = False,
    ) -> list[WorkItem]:
        """Take up to ``n`` items, mark them ``status``, count one more lap on each, and persist once — an empty list is how a drained queue says so, and it writes nothing."""
        items = self._load()
        taken = claim(
            items, n, skip=skip, scheme=self.scheme, kind=kind, strict=strict
        )
        if not taken:
            return []
        for it in taken:
            it.status = status
            it.laps = it.laps + 1
        self.backend.save(items)
        return taken

    def settle(self, ids: Iterable[str], status: str, kind: KindFilter = None) -> int:
        """Set the status of every item named in ``ids``, in one write, and say how many rows it set."""
        wanted = set(ids)
        if not wanted:
            return 0
        kinds = _kinds(kind)
        items = self._load()
        changed = 0
        for it in items:
            if it.id in wanted and (kinds is None or it.kind in kinds):
                it.status = status
                changed += 1
        if changed:
            self.backend.save(items)
        return changed

    def mark(self, item_id: str, status: str, kind: KindFilter = None) -> bool:
        """Set one item's status."""
        kinds = _kinds(kind)
        items = self._load()
        hit = False
        for it in items:
            if it.id == item_id and (kinds is None or it.kind in kinds):
                it.status = status
                hit = True
        if hit:
            self.backend.save(items)
        return hit

    def prune(self, item_id: str, kind: KindFilter = None) -> bool:
        """Drop one item entirely."""
        kinds = _kinds(kind)
        items = self._load()
        kept = [
            it
            for it in items
            if not (it.id == item_id and (kinds is None or it.kind in kinds))
        ]
        if len(kept) != len(items):
            self.backend.save(kept)
            return True
        return False

    def counts(self, kind: KindFilter = None) -> WorkCounts:
        return counts(
            self._load(),
            scheme=self.scheme,
            category_key=self.category_key,
            kind=kind,
        )

    def snapshot(
        self, current: str | None = None, kind: KindFilter = None
    ) -> WorkSnapshot:
        """This worklist's :func:`snapshot` — the label/activity-ready record, scoped to some kinds (``None`` = every kind)."""
        return snapshot(
            self._load(),
            current=current,
            scheme=self.scheme,
            category_key=self.category_key,
            kind=kind,
        )
