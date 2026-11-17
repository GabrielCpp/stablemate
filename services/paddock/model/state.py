"""The benchmark root a person works in: the watched files it holds and the rounds its workspace keeps."""

from __future__ import annotations

from datetime import date

from ostler.book import Collection, State, Unique

from .files import BROKEN_BENCHMARK, BROKEN_HOME, CONFIG, DATA_HEAD, EMPTY_ROOT, FileRecord, FileRows
from .rounds import Round


class Root(FileRows, State):
    files = Collection(FileRecord, Unique("path"))
    rounds = Collection(Round, Unique("key"))

    def __init__(self, today: date):
        super().__init__(today)
        self.files.items[CONFIG] = FileRecord.holding(CONFIG)


def home_unreadable(s: Root) -> bool:
    return BROKEN_HOME in s.files[CONFIG].holds


def root_is_empty(s: Root) -> bool:
    return EMPTY_ROOT in s.files[CONFIG].holds


def has_broken_sibling(s: Root) -> bool:
    return BROKEN_BENCHMARK in s.files


def data_committed(s: Root) -> bool:
    return DATA_HEAD in s.files


def rounds_of(s: Root, task: str | None) -> list[Round]:
    return sorted((r for r in s.rounds if r.task == task), key=lambda r: r.n)


def stage(model: Root) -> str:
    """How far the root has come: the scene it is in."""
    if home_unreadable(model):
        return "home-config-broken"
    if root_is_empty(model):
        return "empty-root"
    if not data_committed(model):
        return "uncommitted"
    if has_broken_sibling(model):
        return "a-broken-benchmark"
    if any(r.open for r in model.rounds):
        return "interrupted"
    return "ran" if len(model.rounds) else "ready"
