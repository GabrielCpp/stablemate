"""`request` matches a path template with ids in it."""

from __future__ import annotations

from types import SimpleNamespace

from ostler.book import Environment, PageSurface, Screen
from ostler.book.browser import action, answer, refusal, request


def sent(method: str, url: str) -> SimpleNamespace:
    return SimpleNamespace(method=method, url=url)


def test_a_template_with_an_id_matches_the_request_that_carries_one():
    wanted = request("PATCH", "/api/projects/{id}/variants/{variant}")
    assert wanted(sent("PATCH", "http://app.test/api/projects/12/variants/7"))


def test_a_template_matches_what_follows_it_as_a_bare_path_does():
    wanted = request("GET", "/api/projects/{id}")
    assert wanted(sent("GET", "http://app.test/api/projects/12/variants"))


def test_a_template_stands_for_one_segment_and_not_for_none_or_two():
    wanted = request("GET", "/api/projects/{id}/variants")
    assert not wanted(sent("GET", "http://app.test/api/projects/variants"))
    assert not wanted(sent("GET", "http://app.test/api/projects/12/13/variants"))


def test_a_template_still_judges_the_verb_the_other_paths_and_the_query():
    wanted = request("GET", "/api/projects/{id}", page="2")
    assert not wanted(sent("POST", "http://app.test/api/projects/12?page=2"))
    assert not wanted(sent("GET", "http://app.test/api/orders/12?page=2"))
    assert not wanted(sent("GET", "http://app.test/api/projects/12"))
    assert wanted(sent("GET", "http://app.test/api/projects/12?page=2"))


def test_answer_matches_the_answer_to_a_template():
    wanted = answer("GET", "/api/projects/{id}")
    assert wanted(SimpleNamespace(request=sent("GET", "http://app.test/api/projects/12")))


def posted(url: str = "http://app.test/tickets/7?/assign") -> SimpleNamespace:
    return sent("POST", url)


def test_a_form_action_matches_the_request_and_the_answer_to_it():
    wanted = action("/tickets/[id]", "assign")
    assert wanted(posted())
    assert wanted(SimpleNamespace(request=posted()))
    assert not wanted(posted("http://app.test/tickets/7?/close"))


def test_answer_matches_a_bare_request_as_well_as_its_answer():
    wanted = answer("GET", "/api/projects/{id}")
    assert wanted(sent("GET", "http://app.test/api/projects/12"))


def test_a_refusal_judges_an_answer_and_never_a_bare_request():
    wanted = refusal("GET", "/api/projects/{id}")
    asked = sent("GET", "http://app.test/api/projects/12")
    assert not wanted(asked)
    assert wanted(SimpleNamespace(request=asked, status=404))
    assert not wanted(SimpleNamespace(request=asked, status=200))


def test_a_screen_that_sends_a_form_action_does_not_make_it_a_stray():
    class Tickets(Screen):
        sends = (action("/tickets/[id]", "assign"),)

    class Fake(PageSurface):
        def drive(self, environment: Environment, lang: str) -> SimpleNamespace:
            return SimpleNamespace(taken=lambda: [posted(), sent("GET", "http://app.test/api/other")])

    surface = Fake(Environment("local", {}), (Tickets,))
    assert surface.strays() == ["GET /api/other"]
