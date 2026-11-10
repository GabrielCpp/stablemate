"""The status of an answer in the words of its protocol."""

from __future__ import annotations

from ostler.book.status import Code, refused, succeeded


def test_a_code_is_found_by_its_name():
    assert Code("NOT_FOUND") is Code.NOT_FOUND


def test_a_code_is_found_by_its_number():
    assert Code.numbered(0) is Code.OK
    assert Code.numbered(5) is Code.NOT_FOUND
    assert Code.numbered(16) is Code.UNAUTHENTICATED


def test_a_gateway_status_is_not_a_code():
    assert not isinstance(404, Code)


def test_a_code_other_than_ok_is_refused():
    assert refused(Code.NOT_FOUND)
    assert refused(Code.UNAVAILABLE)
    assert not refused(Code.OK)


def test_ok_is_the_only_code_that_succeeded():
    assert succeeded(Code.OK)
    assert not succeeded(Code.NOT_FOUND)


def test_a_number_from_400_is_refused():
    assert refused(400)
    assert refused(503)
    assert not refused(200)
    assert not refused(204)


def test_a_number_in_the_200s_succeeded():
    assert succeeded(200)
    assert succeeded(204)
    assert not succeeded(302)
    assert not succeeded(404)
