"""A bullet below one that states there is no claim binds past it, so its arrangement is not lost with that bullet."""

from __future__ import annotations

from ostler import registry

NO_KEYBOARD = "none, because opening the screen fires it and no control is pressed."


def _rows(*keyed: tuple[str, str]) -> list[tuple[str, str, int]]:
    return [(key, value, position) for position, (key, value) in enumerate(keyed)]


def test_an_arrangement_below_a_no_claim_bullet_arranges_the_node() -> None:
    rows = _rows(
        ("trigger", "load"),
        ("keyboard", NO_KEYBOARD),
        ("fixture", "new-customer"),
        ("arrange", 'visit(path="/dashboard")'),
        ("does", "shows the caller's own email address"),
        ("verify", 'visible(locator="#table")'),
    )

    fixtures = registry.attributed_fixtures("interaction", rows, {})
    acts = registry.attributed_acts("interaction", rows, {})

    assert fixtures == (["new-customer"], {})
    assert acts == (['visit(path="/dashboard")'], {})


def test_a_check_below_a_no_claim_bullet_observes_the_claim_above_it() -> None:
    rows = _rows(
        ("does", "shows the caller's own email address"),
        ("keyboard", NO_KEYBOARD),
        ("verify", 'visible(locator="#table")'),
    )

    _contract, per_claim = registry.attributed_checks("interaction", rows, {})

    assert per_claim == {("does", 1): ['visible(locator="#table")']}
