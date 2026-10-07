"""A control rendered once per item is addressed by its name template, never by the template's own text."""

from __future__ import annotations

from ostler.qa.compile_playwright import page_locator_expr
from ostler.qa.obligation import Locators


def test_a_name_with_holes_compiles_to_a_template_locator() -> None:
    locators = Locators(role=("button",), name=("Modifier la version {locale.name}",))
    assert page_locator_expr(locators) == 'qa.by_role("button", template="Modifier la version {locale.name}")'


def test_a_name_without_holes_stays_a_literal_name() -> None:
    locators = Locators(role=("button",), name=("Publier",))
    assert page_locator_expr(locators) == 'qa.by_role("button", name="Publier")'
