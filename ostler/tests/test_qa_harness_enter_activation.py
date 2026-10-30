"""An `Enter` a non-native control's own handler consumes activates it, since a component library may run its click handler from that keydown and dispatch no click."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

elements = load_harness_module("ostler_qa_elements")
sync_api = pytest.importorskip("playwright.sync_api")

_PAGE = """
<ul role="menu">
  <li role="menuitem" tabindex="0" id="handled">Remove</li>
  <li role="menuitem" tabindex="0" id="ignored">Rename</li>
</ul>
<input id="field" aria-label="Name">
<p id="opened"></p>
<form onsubmit="event.preventDefault()"><input id="signup" aria-label="Email"><button>Go</button></form>
<input id="loose" aria-label="Search">
<script>
  const consume = (el, act) => el.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); act(); }
  });
  consume(document.getElementById('handled'), () => { document.getElementById('opened').textContent = 'dialog'; });
  consume(document.getElementById('field'), () => {});
</script>
"""


@pytest.fixture(scope="module")
def page() -> Iterator[Any]:
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:
            pytest.skip(f"no chromium to drive: {exc}")
        opened = browser.new_page()
        opened.set_content(_PAGE)
        yield opened
        browser.close()


def test_an_enter_the_menu_entry_handles_without_a_click_activates_it(page: Any) -> None:
    reading = elements.read_focus(page.locator("#handled"), {"activates": "Enter"})

    assert (reading.focused, reading.activated) == (True, True)
    assert page.locator("#opened").inner_text() == "dialog"


def test_an_enter_nothing_handles_does_not_activate_the_entry(page: Any) -> None:
    assert elements.read_focus(page.locator("#ignored"), {"activates": "Enter"}).activated is False


def test_an_enter_a_native_field_prevents_does_not_count_as_activation(page: Any) -> None:
    assert elements.read_focus(page.locator("#field"), {"activates": "Enter"}).activated is False


def test_an_enter_that_submits_the_form_a_field_belongs_to_activates_the_field(page: Any) -> None:
    assert elements.read_focus(page.locator("#signup"), {"activates": "Enter"}).activated is True


def test_a_field_outside_any_form_is_not_activated_by_enter(page: Any) -> None:
    assert elements.read_focus(page.locator("#loose"), {"activates": "Enter"}).activated is False
