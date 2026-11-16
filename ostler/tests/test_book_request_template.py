"""`request` matches a path template with ids in it."""

from __future__ import annotations

from types import SimpleNamespace

from ostler.book.browser import answer, request


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
