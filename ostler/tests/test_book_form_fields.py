"""The fields of a generated form read as a list: each entry a field's accessible name and its ARIA role."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any, Iterator

import pytest

from book_todo import run_book
from ostler.book import Browser, Screen, T, no_repeat
from ostler.book.wanted import request
from ostler.book.listing import account
from ostler.book.screen import Form as Fields, Lists, Select
from test_book_web import _run, _stack, _stop

@pytest.fixture
def todo_web() -> Iterator:
    stack = _stack()
    yield stack
    _stop(stack)


DEFINITION = {"fields": [
    {"label": "Name", "type": "text"}, {"label": "Budget", "type": "number"}, {"label": "Billable", "type": "flag"}]}
ROLE = {"text": "textbox", "number": "spinbutton", "flag": "checkbox"}


def drawn(definition: dict) -> list[tuple[str, str]]:
    """each field of the definition, with its label and kind, in the definition's order"""
    return [(field["label"], ROLE[field["type"]]) for field in definition["fields"]]


def without_the_last(definition: dict) -> list[tuple[str, str]]:
    """each field of the definition but the last, with its label and kind"""
    return drawn(definition)[:-1]


def screen_of(derived=drawn) -> Any:
    class Project(Screen):
        fields = Fields("project-form", T(en="Project", fr="Projet"), "the fields of the project",
                        lists=Lists(given=request("GET", "/definition"), derived=derived, entries=(no_repeat(),)))

    return Project


def control(index: int, field: dict, kind: str | None) -> str:
    label = f'<label for="f{index}">{field["label"]}</label>'
    wanted = kind or field["type"]
    if wanted == "number":
        return label + f'<input id="f{index}" type="number">'
    if wanted == "flag":
        return label + f'<input id="f{index}" type="checkbox">'
    return label + f'<input id="f{index}" type="text">'


@contextmanager
def _form_page(definition: dict | None = None, wrong_kind: str | None = None, nameless: bool = False, query: str = "") -> Iterator[Browser]:
    body = (
        '<!doctype html><html><body><form id="project" aria-label="Project" data-testid="project-form"></form><script>'
        f"fetch('/definition{query}').then(r => r.json()).then(d => {{"
        "const form = document.getElementById('project');"
        "d.fields.forEach((f, i) => { form.insertAdjacentHTML('beforeend', f.html); });"
        "form.dataset.ready = 'yes'; });</script></body></html>")
    given = definition or DEFINITION
    served = {"fields": [{**field, "html": control(i, field, wrong_kind if i == 1 else None)} for i, field in enumerate(given["fields"])]}
    if nameless:
        served["fields"].append({"label": "", "type": "text", "html": '<input type="text">'})

    def answer(route: Any) -> None:
        if urlsplit(route.request.url).path == "/definition":
            route.fulfill(content_type="application/json", body=json.dumps(served))
        else:
            route.fulfill(content_type="text/html", body=body)

    found = Browser("http://form.test", "en", lang_query=None)
    found.start()
    found.context.route("**/*", answer)
    try:
        yield found
    finally:
        found.stop()


def _read(browser: Browser, screen: Any) -> None:
    browser.feeding((screen,))
    browser.open("/")
    browser.page.wait_for_selector('[data-testid="project-form"][data-ready="yes"]')
    browser.fields(screen.fields)


def test_a_form_whose_fields_are_what_the_book_derives_passes_and_is_counted_as_read():
    screen = screen_of()
    with _form_page() as browser:
        _read(browser, screen)
        assert browser.list_faults() == []
        assert browser.lists_read() == {"Project.fields"}
        assert browser.claims_judged() == {"Project.fields": {"derived", "entries"}}


def test_a_form_reads_its_fields_as_name_and_role_in_document_order():
    screen = screen_of()
    with _form_page() as browser:
        _read(browser, screen)
        assert browser.fields(screen.fields) == [("Name", "textbox"), ("Budget", "spinbutton"), ("Billable", "checkbox")]
        assert browser.labels(screen.fields) == ["Name", "Budget", "Billable"]


def test_a_wrong_derivation_fails_the_step_and_the_note_names_both_sequences_of_label_and_kind():
    screen = screen_of(without_the_last)
    with _form_page() as browser:
        _read(browser, screen)
        assert browser.list_faults() == [
            "the list Project.fields shows [('Name', 'textbox'), ('Budget', 'spinbutton'), ('Billable', 'checkbox')], "
            "the book derives [('Name', 'textbox'), ('Budget', 'spinbutton')]"]


def test_a_field_drawn_with_the_wrong_kind_fails_the_step_and_the_note_names_both_kinds():
    screen = screen_of()
    with _form_page(wrong_kind="text") as browser:
        _read(browser, screen)
        assert browser.list_faults() == [
            "the list Project.fields shows [('Name', 'textbox'), ('Budget', 'textbox'), ('Billable', 'checkbox')], "
            "the book derives [('Name', 'textbox'), ('Budget', 'spinbutton'), ('Billable', 'checkbox')]"]


def test_a_control_with_no_accessible_name_is_read_with_an_empty_label_and_is_a_fault():
    screen = screen_of()
    with _form_page(nameless=True) as browser:
        _read(browser, screen)
        faults = browser.list_faults()
        assert "the list Project.fields has 1 control(s) with no accessible name: [('', 'textbox')]" in faults


def test_a_label_shared_by_two_fields_breaks_the_rule_of_no_repeat():
    repeated = {"fields": [*DEFINITION["fields"], DEFINITION["fields"][0]]}
    screen = screen_of()
    with _form_page(repeated) as browser:
        _read(browser, screen)
        assert browser.list_faults() == ["the list Project.fields breaks \"no repeat\": 'Name' is shown 2 times"]


def test_a_form_found_by_role_group_is_read_as_well():
    screen = screen_of()
    with _form_page() as browser:
        browser.feeding((screen,))
        browser.open("/")
        browser.page.wait_for_selector('[data-testid="project-form"][data-ready="yes"]')
        browser.page.evaluate("document.getElementById('project').setAttribute('role', 'group')")
        assert browser.fields(screen.fields) == [("Name", "textbox"), ("Budget", "spinbutton"), ("Billable", "checkbox")]


def test_the_account_names_a_form_no_journey_read_as_stated_and_never_read_and_one_that_states_nothing_as_named_only():
    class Pages(Screen):
        read = Fields("read", "Read", lists=Lists(given=request("GET", "/definition"), derived=drawn))
        idle = Fields("idle", "Idle", lists=Lists(given=request("GET", "/definition"), derived=drawn))
        free = Fields("free", "Free")
        who = Select("who", "Who", lists=Lists(given=request("GET", "/users"), derived=drawn))

    assert account((Pages,), frozenset({"Pages.read"})) == [
        "Lists", "stated and read:", "- Pages.read", "stated and never read:", "- Pages.idle", "- Pages.who",
        "named only:", "- Pages.free"]


def test_the_details_form_of_the_web_book_passes_the_step_that_reads_it(todo_web, tmp_path: Path):
    done = _run(todo_web, tmp_path, "AWeekOfChores")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "- ListPage.details" in done.stdout.split("stated and never read:")[0]


@pytest.mark.parametrize("bug, said", [
    ("wrong-kind", "the list ListPage.details shows [('Project name', 'textbox'), ('Budget', 'textbox')"),
    ("repeated-field", "the list ListPage.details breaks \"no repeat\": 'Project name' is shown 2 times"),
])
def test_a_page_that_draws_the_details_form_wrongly_fails_the_step_that_reads_it(bug: str, said: str, tmp_path: Path):
    stack = _stack(bug)
    try:
        done = _run(stack, tmp_path, "AWeekOfChores")
    finally:
        _stop(stack)
    assert done.returncode == 1, done.stdout + done.stderr
    assert said in done.stdout


def test_check_finds_nothing_wrong_with_the_web_book_that_states_a_form(todo_web):
    api, page = todo_web
    done = run_book(["check", "services.web"], api.port, web=page.port)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "check: 0 findings" in done.stdout
