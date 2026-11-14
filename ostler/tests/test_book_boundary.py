"""A book that names a record its neighbour owns, played against the stand-in todo app and the digest service in front of it."""

from __future__ import annotations

import pytest

from book_todo import module


def test_a_foreign_record_that_reads_a_field_its_record_lacks_is_refused_where_it_is_declared():
    from ostler.book import BookError, Foreign

    record = module("services.api.model.todo").TodoRecord
    with pytest.raises(BookError, match="nickname"):
        Foreign(record, owner="services.api", reads=("id", "nickname"))


def test_a_derivation_with_no_docstring_is_refused_where_it_is_declared():
    from ostler.book import BookError, Passes

    def derived(answer):
        return answer

    with pytest.raises(BookError, match="docstring"):
        Passes(asks=lambda step: None, derived=derived)


def test_the_id_of_a_needed_record_cannot_be_read_before_the_given_is_arranged():
    from ostler.book import BookError, Foreign, Needs

    record = module("services.api.model.todo").TodoRecord
    needed = Needs(Foreign(record, owner="services.api", reads=("id",)), "overdue")
    with pytest.raises(BookError, match="not arranged"):
        needed.id
    with pytest.raises(BookError, match="not arranged"):
        needed.record
