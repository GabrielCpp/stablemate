"""Which element `by_role` addresses when several carry the name it was given."""

from __future__ import annotations

from dataclasses import dataclass

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")


@dataclass(frozen=True)
class _Found:
    names: tuple[str, ...]

    def count(self) -> int:
        return len(self.names)


@dataclass(frozen=True)
class _Page:
    """A page of same-role elements, matched by name the way a browser does: contained unless `exact`."""

    names: tuple[str, ...]

    def get_by_role(self, _role: str, *, name: str, exact: bool = False) -> _Found:
        if exact:
            return _Found(tuple(each for each in self.names if each == name))
        return _Found(tuple(each for each in self.names if name.lower() in each.lower()))


@dataclass(frozen=True)
class _Qa:
    browser_page: _Page


def _by_role(names: tuple[str, ...], name: str) -> tuple[str, ...]:
    return harness.Qa.by_role(_Qa(_Page(names)), "textbox", name=name).names


def test_a_name_another_element_contains_addresses_the_element_that_carries_it_whole() -> None:
    assert _by_role(("New Password", "Confirm New Password"), "New Password") == ("New Password",)


def test_a_name_one_element_contains_still_addresses_that_element() -> None:
    """A required field's label reads `Email *`, and the book's `Email` is still that field."""
    assert _by_role(("Email *", "Password *"), "Email") == ("Email *",)


def test_a_name_no_element_carries_whole_stays_ambiguous() -> None:
    assert _by_role(("Save draft", "Save copy"), "Save") == ("Save draft", "Save copy")
