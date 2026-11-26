"""The worked example in the ostler-book skill holds each fixture file as the fixture has it."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "base-library/library/skills/ostler/ostler-book/references/worked-example.md"
SERVICES = ROOT / "ostler/tests/fixtures/book_todo/services"
SECTION = re.compile(r"^### (\S+\.py)\n\n```python\n(.*?)```\n", re.M | re.S)


def test_every_file_in_the_worked_example_is_the_fixture_file():
    sections = SECTION.findall(EXAMPLE.read_text())
    assert len(sections) >= 10
    for path, text in sections:
        assert text == (SERVICES / path).read_text(), path


def test_every_heading_in_the_worked_example_carries_a_fence():
    headings = re.findall(r"^### .*$", EXAMPLE.read_text(), re.M)
    assert len(headings) == len(SECTION.findall(EXAMPLE.read_text()))
