"""An optional text field that states no length still gets an input class the run plays."""

from __future__ import annotations

from datetime import date

from ostler.book import Field, Model, Str
from ostler.book.inputs import SCREEN, field_classes

MODEL = Model(date(2026, 11, 16))


def kinds(place: str, spec: Field) -> list[str]:
    return [c.kind for c in field_classes(place, "variant", spec, MODEL, None)]


def test_an_optional_text_field_with_no_length_on_a_screen_is_tried_with_a_blank_value():
    assert kinds(SCREEN, Field(Str(), required=False)) == ["blank"]


def test_the_blank_value_of_an_optional_field_is_one_the_book_accepts():
    only = field_classes(SCREEN, "variant", Field(Str(), required=False), MODEL, None)[0]
    assert only.valid and only.value == "   "


def test_an_optional_text_field_with_a_length_keeps_the_classes_it_had():
    assert kinds(SCREEN, Field(Str(max_len=20), required=False)) == ["too long"]


def test_a_required_text_field_keeps_the_classes_it_had():
    assert kinds(SCREEN, Field(Str())) == ["blank", "missing"]
