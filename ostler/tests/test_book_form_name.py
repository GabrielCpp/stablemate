"""A form with no accessible name is found by what a person sees of it, and the check names one found only by its id."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from ostler.book import Browser, Screen, T
from ostler.book.screen import Form


@contextmanager
def _page(inside: str, attributes: str = "") -> Iterator[Browser]:
    body = f'<!doctype html><html><body><form data-testid="project-form" {attributes}>{inside}</form></body></html>'
    found = Browser("http://form.test", "en", lang_query=None, timeout=1500)
    found.start()
    found.context.route("**/*", lambda route: route.fulfill(content_type="text/html", body=body))
    found.open("/")
    try:
        yield found
    finally:
        found.stop()


def screen_of(form: Any) -> Any:
    class Project(Screen):
        root = None
        project = form

    return Project


def test_a_form_with_no_accessible_name_is_found_by_the_heading_it_holds():
    form = Form(None, T(en="Project"), "the project")
    with _page('<h2>Project</h2><input aria-label="Name">') as browser:
        assert browser.visible(form)
        assert browser.locate(form).evaluate("el => el.querySelector('input').getAttribute('aria-label')") == "Name"


def test_a_form_with_no_accessible_name_is_found_by_the_name_of_its_submit_button():
    form = Form(None, T(en="Save project"), "the project")
    with _page('<input aria-label="Name"><button type="submit">Save project</button>') as browser:
        assert browser.visible(form)


def test_a_form_with_an_accessible_name_is_still_found_by_it():
    form = Form(None, T(en="Project"), "the project")
    with _page('<input aria-label="Name">', 'aria-label="Project"') as browser:
        assert browser.visible(form)


def test_a_form_found_only_by_its_id_is_an_accessibility_finding():
    form = Form("project-form", T(en="Project"), "the project")
    with _page("<h2>Project</h2>") as browser:
        assert browser.wrong_labels("en", (screen_of(form),)) == (
            "Project.project-form: the form has no accessible name 'Project', it is found only by its id: "
            "give it aria-label or aria-labelledby")


def test_a_form_found_by_its_id_that_has_its_accessible_name_is_no_finding():
    form = Form("project-form", T(en="Project"), "the project")
    with _page("<h2>Project</h2>", 'aria-label="Project"') as browser:
        assert browser.wrong_labels("en", (screen_of(form),)) is None
