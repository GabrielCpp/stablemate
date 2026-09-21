"""Source read as syntax — the one parser every language front end goes through."""
from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from importlib import metadata
from pathlib import Path

from tree_sitter import Node, Parser, Tree
from tree_sitter_language_pack import get_parser

GRAMMAR_DISTRIBUTIONS = ("tree-sitter", "tree-sitter-language-pack")

LANGUAGES = {
    ".go": "go",
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "typescript",
    ".jsx": "tsx",
    ".php": "php",
    ".twig": "twig",
}


@lru_cache(maxsize=None)
def _parser(language: str) -> Parser:
    """One parser per grammar, kept for the process."""
    return get_parser(language)


@lru_cache(maxsize=1)
def grammar_version() -> str:
    """What the grammars in this environment are, as one string a caller can put in a key."""
    return " ".join(_distribution_version(name) for name in GRAMMAR_DISTRIBUTIONS)


def _distribution_version(name: str) -> str:
    try:
        return f"{name}={metadata.version(name)}"
    except metadata.PackageNotFoundError:  # pragma: no cover - source checkout
        return f"{name}=unknown"


def language_for(path: str | Path) -> str | None:
    """The grammar for *path*, or None when no front end can read it."""
    return LANGUAGES.get(Path(path).suffix)


@lru_cache(maxsize=4096)
def _tree(language: str, text: str) -> Tree:
    """The last few files parsed, kept."""
    return _parser(language).parse(text.encode())


def parse(language: str, text: str) -> Node:
    """The root node of *text* read as *language*."""
    return _tree(language, text).root_node


def error_names(language: str, text: str) -> set[str]:
    """Every identifier inside a region the parser could not read."""
    root = parse(language, text)
    if not root.has_error:
        return set()
    names = {
        text_of(inner)
        for node in walk(root) if node.type == "ERROR"
        for inner in walk(node) if inner.type.endswith("identifier")
    }
    return names - {""}


def walk(node: Node) -> Iterator[Node]:
    """Every named node in the subtree, root first, in source order."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.named_children))


def text_of(node: Node | None) -> str:
    """The source *node* spans, decoded."""
    if node is None:
        return ""
    try:
        return (node.text or b"").decode()
    except (MemoryError, ValueError, OSError):
        return ""


def field_text(node: Node, field: str) -> str:
    """The text of *node*'s `field` child — "" when the grammar did not fill it in, which is how an anonymous function or a declaration inside an `ERROR` region presents."""
    return text_of(node.child_by_field_name(field))


def lines_of(node: Node) -> tuple[int, int]:
    """*node*'s first and last line, 1-based and inclusive — a declaration's true extent."""
    return node.start_point[0] + 1, node.end_point[0] + 1
