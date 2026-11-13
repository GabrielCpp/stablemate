"""The coder and its QA kit name no markdown book page, no page tool and no page-only command."""
from __future__ import annotations

from pathlib import Path

import pytest

from workhorse_workflows import coder
from workhorse_workflows.kit import qa

BANNED = (
    "docs/services",
    "okf:",
    "ostler-okf",
    "qa-stack.md",
    "qa-okf-context",
    "ostler doctor",
    "ostler scaffold",
    "ostler fmt",
    "qa context",
)
ROOTS = (Path(coder.__file__).parent, Path(qa.__file__).parent)
FILES = sorted(
    p
    for root in ROOTS
    for p in root.rglob("*")
    if p.suffix in {".py", ".md"} and "__pycache__" not in p.parts
)


@pytest.mark.parametrize("path", FILES, ids=lambda p: "/".join(p.parts[-3:]))
def test_a_coder_file_names_no_markdown_book_token(path: Path) -> None:
    hits = [
        f"{path}:{number}: {token}"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        for token in BANNED
        if token in line
    ]
    assert not hits, "\n".join(hits)


def test_the_sweep_covers_a_qa_prompt_and_a_kit_module() -> None:
    assert any(p.parent.name == "prompts" and p.parent.parent.name == "qa" for p in FILES)
    assert any(p.name == "runner.py" and p.parent.name == "qa" for p in FILES)
