"""A component that sits inside another through `parent:` is observed in the state its parent's own fixture arranges, after every fixture that state needs."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ostler.qa.context import build_context

SCREEN = "docs/features/acme/gui/screens/items.md"
NODE = f"okf:{SCREEN}#title-field"

ITEMS = "\n".join([
    "---", "type: screen", "title: Items", "---", "# Items", "",
    "- route: /items", "- params: none", "",
    "## Components", "",
    "### create-dialog",
    "- fixture: [Dialog open](../../fixtures/dialog-open.md)",
    "- role: dialog", "- name: New item",
    "- states: shown after the create button is pressed", "- code: app/items.py::render_dialog", "",
    "### title-field",
    "- role: textbox", "- name: Title",
    "- states: takes the typed title",
    "- fixture: [Signed in](../../fixtures/signed-in.md)",
    "- parent: [create-dialog](#create-dialog)",
    "- code: app/items.py::render_dialog", "",
])

SIGNED_IN = "\n".join([
    "---", "type: fixture", "title: Signed in", "---", "# Signed in", "",
    "## Steps", "", "### sign-in", "", "- kind: seed", "- run: true", "",
])

DIALOG_OPEN = "\n".join([
    "---", "type: fixture", "title: Dialog open", "---", "# Dialog open", "",
    "- needs:", "  - [Signed in](signed-in.md)", "",
    "## Steps", "", "### open-dialog", "", "- kind: seed",
    "- open: [Items](../gui/screens/items.md)",
    '- arrange: click("../gui/screens/items.md#create-dialog")', "",
])


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _arranged(tmp_path: Path, items: str) -> dict[str, list[str]]:
    for path, text in {SCREEN: items, "docs/features/acme/fixtures/signed-in.md": SIGNED_IN,
                       "docs/features/acme/fixtures/dialog-open.md": DIALOG_OPEN,
                       "app/items.py": "def render_dialog():\n    return 'old'\n"}.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text, encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app/items.py").write_text("def render_dialog():\n    return 'new'\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})

    return {item["id"]: [row["name"] for row in item.get("fixturesDeclared", [])] for item in packet["obligations"]}


def test_a_field_inside_a_dialog_is_checked_with_the_dialog_open(tmp_path: Path) -> None:
    arranged = _arranged(tmp_path, ITEMS)

    assert arranged[f"{NODE}:name:1"] == ["dialog-open"]
    assert arranged[f"{NODE}:states:1"] == ["signed-in", "dialog-open"]


def test_a_field_with_no_parent_inherits_nothing(tmp_path: Path) -> None:
    arranged = _arranged(tmp_path, ITEMS.replace("- parent: [create-dialog](#create-dialog)\n", ""))

    assert arranged[f"{NODE}:name:1"] == []
    assert arranged[f"{NODE}:states:1"] == ["signed-in"]
