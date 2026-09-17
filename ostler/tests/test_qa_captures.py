"""The `capture:` bullet grammar, and the one property that makes it a module.

A declaration mints a name and a `$name` reference spells it. Those are the same name, so
they are held to the same grammar — `captures.parse_bullet` validates against `references`
rather than carrying a second copy of the spelling that drifts from it.
"""

from __future__ import annotations

from ostler.qa import captures, references


def test_a_well_formed_bullet_yields_a_name_and_a_source():
    parsed = captures.parse_bullet("claim-id from $.data.id")

    assert isinstance(parsed, captures.CaptureDecl)
    assert (parsed.name, parsed.source) == ("claim-id", "$.data.id")


def test_a_ui_locator_is_a_source_too():
    parsed = captures.parse_bullet("receipt from widget-list.md#receipt-number")

    assert isinstance(parsed, captures.CaptureDecl)
    assert parsed.source == "widget-list.md#receipt-number"


def test_a_bullet_with_no_from_is_refused_rather_than_dropped():
    """The refusal is a value. Dropped, this bullet is the same absent row as a node that
    declared no capture at all — and the cost surfaces on a *later* bullet whose `$name` then
    resolves against a fact nobody minted, against an author who wrote that one correctly."""
    parsed = captures.parse_bullet("claim_id $.id")

    assert isinstance(parsed, str)
    assert "names no source" in parsed


def test_an_empty_bullet_is_refused():
    assert captures.parse_bullet("   ") == "empty"


def test_a_name_no_reference_could_spell_is_refused():
    parsed = captures.parse_bullet("claim id! from $.id")

    assert isinstance(parsed, str)
    assert "not a name a `$` reference could spell" in parsed


def test_a_reference_spelled_on_the_declaring_side_is_refused_by_name():
    """Stripping the `$` quietly would admit two spellings for one concept on the side that
    mints it. The refusal names the repair instead."""
    parsed = captures.parse_bullet("$claim_id from $.id")

    assert isinstance(parsed, str)
    assert "claim_id" in parsed and "$claim_id" in parsed


def test_every_name_this_accepts_is_one_a_reference_resolves_to():
    """The property, stated as a test rather than as a docstring: no accepted declaration may
    mint a name `references` would not hand back from the `$name` a later bullet writes."""
    for value in ["a from $.x", "claim-id from $.x", "Claim_ID9 from $.x", "0th from $.x"]:
        parsed = captures.parse_bullet(value)
        assert isinstance(parsed, captures.CaptureDecl), value
        assert references.parse_reference(f"${parsed.name}") == references.CaptureRef(parsed.name)
