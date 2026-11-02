"""Which element `by_role` addresses when several carry the name it was given."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")


@dataclass
class _Found:
    page: _Page
    name: str | re.Pattern[str]
    exact: bool

    @property
    def names(self) -> tuple[str, ...]:
        if isinstance(self.name, re.Pattern):
            return tuple(each for each in self.page.shown if self.name.search(each))
        if self.exact:
            return tuple(each for each in self.page.shown if each == self.name)
        return tuple(each for each in self.page.shown if self.name.lower() in each.lower())

    def count(self) -> int:
        return len(self.names)

    @property
    def first(self) -> _Found:
        return self

    def wait_for(self, *, state: str, timeout: int) -> None:
        self.page.shown, self.page.loading = self.page.shown + self.page.loading, ()


@dataclass
class _Page:
    """A page of same-role elements, matched by name the way a browser does: contained unless `exact`.

    The elements in *loading* appear once something waits for them. The page's network never goes idle.
    """

    shown: tuple[str, ...]
    loading: tuple[str, ...] = ()

    def get_by_role(self, _role: str, *, name: str | re.Pattern[str], exact: bool = False) -> _Found:
        return _Found(self, name, exact)

    def wait_for_load_state(self, _state: str, *, timeout: int) -> None:
        raise TimeoutError(f"Timeout {timeout}ms exceeded.")


@dataclass(frozen=True)
class _Qa:
    browser_page: _Page | _Options


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


def test_a_name_no_element_carries_whole_addresses_nothing() -> None:
    assert _by_role(("Save draft", "Save copy"), "Save") == ()


def test_a_longer_name_that_contains_the_name_is_another_element() -> None:
    """An absence claim on `Acme` must not find the row that reads `Acme (sales@acme.example.com)`."""
    assert _by_role(("Acme (sales@acme.example.com)",), "Acme") == ()


def test_a_name_matches_in_any_case_and_spacing() -> None:
    assert _by_role(("Sign  in",), "sign in") == ("Sign  in",)


def test_a_template_addresses_a_control_whose_name_fills_its_holes() -> None:
    found = harness.Qa.by_role(_Qa(_Page(("Modifier", "Modifier la version Français"))), "button",
                               template="Modifier la version {locale.name}")
    assert found.names == ("Modifier la version Français",)


def test_a_template_hole_matches_the_empty_text() -> None:
    assert harness.template_pattern("Supprimer {document.title}").match("Supprimer ")


def test_a_name_with_a_slash_leaves_no_bare_slash_to_end_playwrights_selector_pattern() -> None:
    for pattern in (harness.name_pattern("Wood / Framing"), harness.template_pattern("Wood / {category.name}")):
        assert "/" not in pattern.pattern.replace("\\/", "")
        assert pattern.match("Wood / Framing")


def test_a_name_of_only_holes_looks_inside_its_container() -> None:
    """A page-wide search would open the first combobox on the page, whichever control that is."""
    page = _Page(("Project switcher",))
    panel = _Page(("Exterior siding",))
    found = harness.Qa.by_role(_Qa(page), "combobox", template="{group.name}", within=panel)
    assert found.names == ("Exterior siding",)


class _Chooser:
    """A chooser that records what a person did to it, rendered as *tag*."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.acts: list[str] = []

    def evaluate(self, _script: str) -> str:
        return self.tag

    def select_option(self, option: str) -> None:
        self.acts.append(f"select {option}")

    def click(self) -> None:
        self.acts.append("open")


class _Options:
    """A page whose opened list records the option pressed."""

    def __init__(self, chooser: _Chooser) -> None:
        self.chooser = chooser
        self.pressed: str | re.Pattern[str] = ""

    def get_by_role(self, role: str, *, name: re.Pattern[str]) -> _Options:
        assert role == "option"
        self.pressed = name
        return self

    @property
    def first(self) -> _Options:
        return self

    def click(self) -> None:
        assert isinstance(self.pressed, re.Pattern)
        self.chooser.acts.append("press " + ("Vinyl siding" if self.pressed.match("Vinyl siding") else "other"))


def test_a_native_select_takes_the_option_directly() -> None:
    chooser = _Chooser("SELECT")
    harness.Qa.select(_Qa(_Options(chooser)), chooser, option="Vinyl siding")
    assert chooser.acts == ["select Vinyl siding"]


def test_any_other_chooser_opens_and_presses_the_option() -> None:
    chooser = _Chooser("DIV")
    harness.Qa.select(_Qa(_Options(chooser)), chooser, option="Vinyl siding")
    assert chooser.acts == ["open", "press Vinyl siding"]
