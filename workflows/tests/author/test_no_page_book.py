"""The author names no markdown book page, no page tool and no page-only module."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from workhorse_workflows import author

BANNED = (
    "docs/services",
    "ostler-okf",
    "OKF",
    "docs/okf",
    "ostler scaffold",
    "ostler fmt",
    "ostler trace",
    "ostler graph",
    "ostler search",
    "ostler explain",
    "ostler checks",
    "ostler doctor --path",
    "qa context",
    "verify:",
    "services_dir",
    "services_root",
    "ui_nodes",
    "surfaces-referenced-by-story",
)
PAGE_MODULES = ("ostler.coverage", "ostler.graph", "ostler.reach", "ostler.links", "ostler.qa", "ostler.model.load")
ROOTS = (Path(author.__file__).parent,)
FILES = sorted(
    p
    for root in ROOTS
    for p in root.rglob("*")
    if p.suffix in {".py", ".md"} and "__pycache__" not in p.parts
)
PROSE_ONLY = ("okf:",)
PYTHON = [p for p in FILES if p.suffix == ".py"]


def _imported(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names |= {f"{node.module}.{alias.name}" for alias in node.names}
    return names


@pytest.mark.parametrize("path", FILES, ids=lambda p: "/".join(p.parts[-3:]))
def test_an_author_file_names_no_markdown_book_token(path: Path) -> None:
    hits = [
        f"{path}:{number}: {token}"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        for token in BANNED + (PROSE_ONLY if path.suffix == ".md" else ())
        if token in line
    ]
    assert not hits, "\n".join(hits)


@pytest.mark.parametrize("path", PYTHON, ids=lambda p: "/".join(p.parts[-3:]))
def test_the_author_imports_no_page_module(path: Path) -> None:
    hits = sorted(
        name
        for name in _imported(path)
        if any(name == page or name.startswith(page + ".") for page in PAGE_MODULES)
    )
    assert not hits, f"{path}: {hits}"


def test_the_sweep_covers_a_prompt_and_a_node() -> None:
    names = {"/".join(p.parts[-3:]) for p in FILES}
    assert "story_author/prompts/write-story.md" in names
    assert "pm/prompts/books.md" in names
    assert "shared/nodes/stories.py" in names
