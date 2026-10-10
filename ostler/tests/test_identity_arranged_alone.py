"""`identity-arranged-alone` — a `fixture:` under an element's `role:` or `name:` arranges that claim and none of the others about the element."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import write

DASH = "docs/features/web/gui/screens/dashboard.md"

HEAD = """\
---
type: screen
slug: dashboard
title: Dashboard
---
# Dashboard

- route: `/`
- requires: none
- params: none

## Components

### import-dialog
"""


def _findings(repo: Path, body: str) -> list[doctor.Finding]:
    write(repo / DASH, HEAD + body)
    return [f for f in doctor.run(load(repo)).findings if f.code == "identity-arranged-alone"]


def test_a_fixture_under_the_name_leaves_every_other_claim_unarranged(repo: Path) -> None:
    [found] = _findings(repo, (
        "- role: dialog\n"
        "- name: Import a file\n"
        '- verify: visible(locator="#import-dialog", text="Import a file")\n'
        "- fixture: import-dialog-open\n"
        "- keyboard: Escape closes the dialog\n"
        '- verify: focusable(locator="#import-dialog", activates="Escape")\n'))
    assert found.severity == "error"
    assert found.ref.endswith("#name:1")
    assert "`keyboard:1`" in found.message
    assert "above the node's first claim" in (found.suggestion or "")


def test_a_fixture_above_every_claim_arranges_them_all(repo: Path) -> None:
    assert _findings(repo, (
        "- fixture: import-dialog-open\n"
        "- role: dialog\n"
        "- name: Import a file\n"
        "- keyboard: Escape closes the dialog\n"
        '- verify: focusable(locator="#import-dialog", activates="Escape")\n')) == []


def test_a_fixture_under_one_state_arranges_that_state_alone(repo: Path) -> None:
    assert _findings(repo, (
        "- role: dialog\n"
        "- name: Import a file\n"
        "- states: shows the quota error once the import is refused\n"
        "- fixture: import-quota-exhausted\n"
        '- verify: visible(locator="#import-dialog", text="quota")\n')) == []


DIALOG = (
    "- role: dialog\n"
    "- name: Import a file\n"
    '- verify: visible(locator="#import-dialog", text="Import a file")\n'
    "\n## Interactions\n\n### close-import\n"
    "- on: [import-dialog](#import-dialog)\n"
    '- trigger: press(key="Escape")\n'
    "- role: dialog\n"
    "- name: Import a file\n"
    "- keyboard: Escape closes the dialog\n"
    '- verify: focusable(locator="#import-dialog", activates="Escape")\n'
)


def test_a_fixture_under_the_keyboard_leaves_the_interaction_unarranged(repo: Path) -> None:
    [found] = _findings(repo, DIALOG + (
        "- fixture: import-dialog-open\n"
        "- does:\n"
        "  - closes the dialog.\n"
        '- verify: hidden(locator="#import-dialog")\n'))
    assert found.ref.endswith("#close-import#keyboard:1")
    assert "`does:1`" in found.message
    assert "`- fixture: import-dialog-open`" in (found.suggestion or "")


def test_an_arrange_under_the_keyboard_leaves_the_interaction_unarranged(repo: Path) -> None:
    [found] = _findings(repo, DIALOG + (
        '- arrange: visit(path="/")\n'
        "- does:\n"
        "  - closes the dialog.\n"
        '- verify: hidden(locator="#import-dialog")\n'))
    assert found.message.startswith(f"{DASH}#close-import: `arrange: ")
    assert "`does:1`" in found.message
