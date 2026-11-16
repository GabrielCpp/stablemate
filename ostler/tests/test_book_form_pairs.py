"""An entries rule of a generated form may judge each field's name and role together."""

from __future__ import annotations

from typing import Any

from ostler.book import Screen, T, no_repeat
from ostler.book.browser import request
from ostler.book.entries import of_pairs
from ostler.book.screen import Form, Lists
from test_book_form_fields import _form_page, _read, drawn

TWICE = {"fields": [{"label": "Name", "type": "text"}, {"label": "Billable", "type": "flag"}, {"label": "Name", "type": "number"}]}


def checks_last(pairs: list[Any]) -> list[str]:
    """every checkbox comes after the other fields"""
    first = next((i for i, (_, role) in enumerate(pairs) if role == "checkbox"), len(pairs))
    return [f"{pair!r} follows a checkbox" for pair in pairs[first + 1:] if pair[1] != "checkbox"]


def screen_of(*rules: Any) -> Any:
    class Project(Screen):
        fields = Form("project-form", T(en="Project", fr="Projet"), "the fields of the project",
                      lists=Lists(given=request("GET", "/definition"), derived=drawn, entries=rules))

    return Project


def test_a_rule_that_judges_the_pairs_of_a_form_sees_the_name_and_the_role_of_each_field():
    with _form_page(TWICE) as browser:
        _read(browser, screen_of(of_pairs(checks_last)))
        assert browser.list_faults() == [
            "the list Project.fields breaks \"every checkbox comes after the other fields\": "
            "('Name', 'spinbutton') follows a checkbox"]


def test_a_repeat_of_a_name_with_another_role_is_no_repeat_of_the_pair():
    with _form_page(TWICE) as browser:
        _read(browser, screen_of(of_pairs(no_repeat())))
        assert browser.list_faults() == []


def test_a_rule_not_wrapped_still_judges_the_names_as_before():
    with _form_page(TWICE) as browser:
        _read(browser, screen_of(no_repeat()))
        assert browser.list_faults() == ["the list Project.fields breaks \"no repeat\": 'Name' is shown 2 times"]
