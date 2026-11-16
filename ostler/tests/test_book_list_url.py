"""A `derived` function may take the URL of the request whose answer fills the list, after the body."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest

from ostler.book import Screen, T
from ostler.book.browser import request
from ostler.book.errors import BookError
from ostler.book.screen import Form, Lists
from test_book_form_fields import _form_page, _read, drawn


def first_asked_for(definition: dict, url: str) -> list[tuple[str, str]]:
    """the first fields of the definition, as many as the request asks for"""
    count = int(dict(parse_qsl(urlsplit(url).query))["upto"])
    return drawn(definition)[:count]


def screen_of(derived: Any) -> Any:
    class Project(Screen):
        fields = Form("project-form", T(en="Project", fr="Projet"), "the fields of the project",
                      lists=Lists(given=request("GET", "/definition"), derived=derived))

    return Project


def test_a_derived_that_reads_the_request_url_passes_when_the_page_drew_what_the_url_asked_for():
    screen = screen_of(first_asked_for)
    with _form_page(query="?upto=3") as browser:
        _read(browser, screen)
        assert browser.list_faults() == []


def test_a_derived_that_reads_the_request_url_fails_the_step_when_the_page_drew_more():
    screen = screen_of(first_asked_for)
    with _form_page(query="?upto=2") as browser:
        _read(browser, screen)
        assert browser.list_faults() == [
            "the list Project.fields shows [('Name', 'textbox'), ('Budget', 'spinbutton'), ('Billable', 'checkbox')], "
            "the book derives [('Name', 'textbox'), ('Budget', 'spinbutton')]"]


def test_a_derived_of_the_body_alone_is_called_as_before():
    screen = screen_of(drawn)
    with _form_page(query="?upto=2") as browser:
        _read(browser, screen)
        assert browser.list_faults() == []


def test_a_derived_that_takes_three_arguments_is_refused_when_the_list_is_stated():
    def three(body: dict, url: str, more: str) -> list[Any]:
        """nothing"""
        return []

    with pytest.raises(BookError, match="derived"):
        Lists(given=request("GET", "/definition"), derived=three)
