"""The judgement of a list a surface has read: the texts it shows and the entry it has selected, against what the
book says it holds. A surface reads the list its own way and names the feed its way. This module knows neither."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ostler.book.asked import Asked, Unasked
from ostler.book.screen import Component, Lists, Screen


class Unfed(Exception):
    """The data a list is derived from cannot be had, and why: the whole text is the fault."""


Feed = Callable[[Component, str], tuple[Any, str]]


class ListJudge:
    def __init__(self) -> None:
        self.screens: tuple[type[Screen], ...] = ()
        self.faults: list[str] = []
        self.read: dict[str, set[str]] = {}
        self.picked: set[str] = set()
        self.expected: dict[str, tuple[Any, ...]] = {}
        self.asked: dict[str, Any] = {}

    def feeding(self, screens: tuple[type[Screen], ...]) -> None:
        self.screens = screens

    def taken(self) -> list[str]:
        """The differences found since the last time this was asked."""
        faults, self.faults = self.faults, []
        return faults

    def lists_read(self) -> frozenset[str]:
        return frozenset(self.read)

    def claims_judged(self) -> dict[str, frozenset[str]]:
        return {name: frozenset(claims) for name, claims in self.read.items()}

    def forget_picks(self) -> None:
        self.picked.clear()

    def expecting(self, expectations: Mapping[str, tuple[Any, ...]], asked: Mapping[str, Any] | None = None) -> None:
        self.expected = dict(expectations)
        self.asked = dict(asked or {})

    def named(self, component: Component, lang: str) -> str:
        for screen in self.screens:
            for name, found in screen.attributes():
                if found is component:
                    return f"{screen.__name__}.{name}"
        return component.found_by(lang)

    def judge(self, component: Component, shown: list[Any], selected: str, lang: str, feed: Feed) -> None:
        lists = component.lists
        assert lists is not None
        name = self.named(component, lang)
        judged = self.read.setdefault(name, set())
        if lists.derived is not None:
            judged.add("derived")
            self.derived(component, name, shown, lang, feed)
        texts = [entry[0] if isinstance(entry, tuple) else entry for entry in shown]
        unnamed = [entry for entry in shown if isinstance(entry, tuple) and not entry[0]]
        if unnamed:
            self.faults.append(f"the list {name} has {len(unnamed)} control(s) with no accessible name: {unnamed}")
        self.entries(lists, name, texts, lang)
        if lists.entries:
            judged.add("entries")
        self.picked_entry(lists, name, selected, lang)
        if name not in self.picked and (lists.picked is not None and (not callable(lists.picked) or len(self.expected.get(name, ())) > 2)):
            judged.add("picked")
        self.picked.add(name)
        belong, never = self.expected.get(name, ([], []))[:2]
        if lists.always is not None and name in self.expected:
            judged.add("always")
        if lists.never is not None and name in self.expected:
            judged.add("never")
        missing = [text for text in dict.fromkeys(belong) if text not in texts]
        if missing:
            self.faults.append(f"the list {name} misses {missing}, which belong in it")
        forbidden = [text for text in dict.fromkeys(never) if text in texts]
        if forbidden:
            self.faults.append(f"the list {name} shows {forbidden}, which must never be in it")

    def entries(self, lists: Lists, name: str, shown: list[str], lang: str) -> None:
        head = lists.labels(lang)
        entries = shown[len(head):] if shown[:len(head)] == head else shown
        for rule in lists.entries:
            said = (rule.__doc__ or "").strip().splitlines()[0]
            try:
                broken = rule(entries)
            except Exception as crash:
                self.faults.append(f"the list {name} cannot judge \"{said}\": {type(crash).__name__}: {crash}")
                continue
            self.faults += [f"the list {name} breaks \"{said}\": {why}" for why in broken]

    def picked_entry(self, lists: Lists, name: str, selected: str, lang: str) -> None:
        if name in self.picked or lists.picked is None:
            return
        expected = self.expected.get(name, ())
        wanted = lists.label_picked(lang) if not callable(lists.picked) else expected[2] if len(expected) > 2 else None
        if wanted is not None and selected != wanted:
            self.faults.append(f"the list {name} has {selected!r} selected before the pick, the book says {wanted!r}")

    def derived(self, component: Component, name: str, shown: list[Any], lang: str, feed: Feed) -> None:
        lists = component.lists
        assert lists is not None and lists.given is not None and lists.derived is not None
        try:
            body, url = (self.answer(lists.given, name), "") if isinstance(lists.given, Asked) else feed(component, name)
        except Unfed as unfed:
            self.faults.append(str(unfed))
            return
        derived = [*lists.labels(lang), *(tuple(entry) if isinstance(entry, list) else entry for entry in lists.derive(body, url))]
        if shown != derived:
            self.faults.append(f"the list {name} shows {shown}, the book derives {derived}")

    def answer(self, given: Asked, name: str) -> Any:
        said = f"the list {name} is asked of {given.text}"
        if name not in self.asked:
            raise Unfed(f"{said}, and no step asked it before this pick")
        fed = self.asked[name]
        if isinstance(fed, Unasked):
            raise Unfed(f"{said}, and {fed.why}")
        return fed


class ListReader:
    """What a surface that reads lists tells the run about them: the faults found, the lists read and the claims judged,
    and what to expect of the picks of the next step. The surface holds its `ListJudge` as `lists`."""

    lists: ListJudge

    def list_faults(self) -> list[str]:
        """The differences found between a list and what the book says it holds since the last time this was asked."""
        return self.lists.taken()

    def lists_read(self) -> frozenset[str]:
        """The lists, by screen and attribute, a pick has judged."""
        return self.lists.lists_read()

    def claims_judged(self) -> dict[str, frozenset[str]]:
        """For each list a pick has judged, the claims it judged: derived, always, never, entries, picked."""
        return self.lists.claims_judged()

    def expecting(self, expectations: Mapping[str, tuple[Any, ...]], asked: Mapping[str, Any] | None = None) -> None:
        """Hands over, for each list by screen and attribute, the texts it must show and the texts it must not, and
        when the list's picked entry is a function, the label it returns, for the picks that follow. `asked` holds, for
        each list fed by a backend's call, the answer that call got as the person taking the step, or why it got none.
        An empty mapping drops them."""
        self.lists.expecting(expectations, asked)
