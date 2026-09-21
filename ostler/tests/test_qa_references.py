"""The `@node.key`/`$name` reference grammar `fixture:`/`needs:`/paths/`verify:` all share."""

from __future__ import annotations

from ostler.qa.references import CaptureRef, NodeRef, find_references, parse_reference


def test_a_node_ref_is_found_in_free_text() -> None:
    assert find_references("path is @seeded-acme.id here") == [NodeRef("seeded-acme", "id")]


def test_a_capture_ref_is_found_in_free_text() -> None:
    assert find_references("expect $captured to equal 1") == [CaptureRef("captured")]


def test_an_email_address_in_a_route_or_verify_arg_is_not_a_node_ref() -> None:
    """`user@example.com` is a literal a book can legitimately assert, not a `@node.key` reference — the `@` here is preceded by a word character, which the grammar never is."""
    assert find_references("verify email equals user@example.com") == []


def test_an_email_address_does_not_mask_a_real_reference_elsewhere_in_the_text() -> None:
    text = "notify user@example.com once @seeded-acme.id exists"
    assert find_references(text) == [NodeRef("seeded-acme", "id")]


def test_a_dollar_amount_directly_after_a_word_character_is_not_a_capture_ref() -> None:
    """The same guard applies to `$`: a template variable embedded mid-identifier (e.g."""
    assert find_references("price.total$captured") == []


def test_parse_reference_still_refuses_a_value_that_is_not_entirely_one_reference() -> None:
    assert parse_reference("user@example.com") is None
    assert parse_reference("@seeded-acme.id") == NodeRef("seeded-acme", "id")
    assert parse_reference("$captured") == CaptureRef("captured")
