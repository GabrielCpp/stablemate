"""Which status or alert the harness finds by the name a book gives it."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")
settle = load_harness_module("ostler_qa_settle")


@dataclass(frozen=True)
class _Region:
    label: str
    text: str


@dataclass
class _Found:
    regions: tuple[_Region, ...]

    def filter(self, *, has_text: str) -> _Found:
        return _Found(tuple(each for each in self.regions if has_text.lower() in each.text.lower()))

    def or_(self, other: _Found) -> _Found:
        return _Found(self.regions + tuple(each for each in other.regions if each not in self.regions))

    def count(self) -> int:
        return len(self.regions)

    def nth(self, index: int) -> _Found:
        return _Found((self.regions[index],))

    def is_visible(self) -> bool:
        return bool(self.regions)

    @property
    def first(self) -> _Found:
        return self

    def wait_for(self, *, state: str, timeout: int) -> None:
        return None


@dataclass
class _Page:
    """A page of live regions, each named by its `aria-label` and announcing its text."""

    regions: tuple[_Region, ...]

    def get_by_role(self, _role: str, *, name: re.Pattern[str] | None = None, **_states: bool) -> _Found:
        if name is None:
            return _Found(self.regions)
        return _Found(tuple(each for each in self.regions if each.label and name.search(each.label)))


@dataclass(frozen=True)
class _Qa:
    browser_page: _Page


def _by_role(page: _Page, name: str) -> int:
    return harness.Qa.by_role(_Qa(page), "status", name=name).count()


def _settle_shown(page: _Page, name: str) -> int:
    return int(settle.shown(page, {"role": "status", "name": name}))


FINDERS = {"by_role": _by_role, "settle": _settle_shown}

NOTICE = _Region(label="No widgets on file", text="No widgets are on file yet.")


def test_a_status_is_found_by_the_label_it_carries() -> None:
    for finder, find in FINDERS.items():
        assert find(_Page((NOTICE,)), "No widgets on file") == 1, finder


def test_a_status_without_a_label_is_found_by_the_text_it_announces() -> None:
    for finder, find in FINDERS.items():
        assert find(_Page((_Region(label="", text="Saved."),)), "Saved") == 1, finder


def test_a_status_neither_label_nor_text_names_is_not_found() -> None:
    for finder, find in FINDERS.items():
        assert find(_Page((NOTICE,)), "Nothing running low") == 0, finder
