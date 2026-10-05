"""Which element `by_role` addresses when several carry the name it was given."""

from __future__ import annotations

from dataclasses import dataclass

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")


@dataclass
class _Found:
    page: _Page
    name: str
    exact: bool

    @property
    def names(self) -> tuple[str, ...]:
        if self.exact:
            return tuple(each for each in self.page.shown if each == self.name)
        return tuple(each for each in self.page.shown if self.name.lower() in each.lower())

    def count(self) -> int:
        return len(self.names)


@dataclass
class _Page:
    """A page of same-role elements, matched by name the way a browser does: contained unless `exact`.

    The elements in *loading* appear once the page's loads finish.
    """

    shown: tuple[str, ...]
    loading: tuple[str, ...] = ()

    def get_by_role(self, _role: str, *, name: str, exact: bool = False) -> _Found:
        return _Found(self, name, exact)

    def wait_for_load_state(self, _state: str, *, timeout: int) -> None:
        self.shown, self.loading = self.shown + self.loading, ()


@dataclass(frozen=True)
class _Qa:
    browser_page: _Page


def _by_role(names: tuple[str, ...], name: str, loading: tuple[str, ...] = ()) -> tuple[str, ...]:
    return harness.Qa.by_role(_Qa(_Page(names, loading)), "textbox", name=name).names


def test_a_name_another_element_contains_addresses_the_element_that_carries_it_whole() -> None:
    assert _by_role(("New Password", "Confirm New Password"), "New Password") == ("New Password",)


def test_a_name_one_element_contains_still_addresses_that_element() -> None:
    """A required field's label reads `Email *`, and the book's `Email` is still that field."""
    assert _by_role(("Email *", "Password *"), "Email") == ("Email *",)


def test_a_list_that_renders_after_the_call_still_addresses_the_element_that_carries_the_name_whole() -> None:
    assert _by_role((), "Notre processus", loading=("Notre processus", "Monter Notre processus")) == (
        "Notre processus",)


def test_a_name_no_element_carries_whole_stays_ambiguous() -> None:
    assert _by_role(("Save draft", "Save copy"), "Save") == ("Save draft", "Save copy")
