"""Source read as syntax — the one parser every language front end goes through.

`inventory` used to answer "what does this file declare?" with a regex per language, and the
answers were wrong in both directions for the same reason: a regex matches *text*, and text
includes comments, string literals and whatever scope the match happened to land in. A
commented-out `export function ghost()` became a unit the book owed coverage for; a name
inside a template literal grounded a `code:` citation; and the shapes the pattern did not
spell — `export abstract class`, `export const {a, b} = …`, Go's grouped `type (…)` — were
invisible, so a *correct* citation failed grounding with no way to fix it.

**tree-sitter, not the native toolchain.** A real `go/ast` or `tsc` parse would mean ostler's
correctness depended on the *target* repo having Go or node installed and its tree being
buildable — and ostler runs inside agent containers and CI against repos it never builds,
while `okf-builder` reads working trees mid-edit. A missing toolchain forces a fallback, and a
fallback is a second grammar that disagrees with the first, which is the exact failure
`inventory` was extracted to end. tree-sitter ships as a prebuilt wheel, needs nothing from
the repo it reads, and recovers from a syntax error instead of refusing the file.

The split with `inventory` is deliberate: this module knows how to get a tree and walk it;
what counts as a *unit*, and which units are public, is language semantics and lives there.
"""
from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from tree_sitter import Node, Parser, Tree
from tree_sitter_language_pack import get_parser

#: The grammar each suffix is read with. Wider than `inventory.SOURCE_SUFFIXES` on purpose:
#: the QA diff mapper attributes changed lines in `.js`/`.jsx` too, while the coverage
#: inventory does not count them as units. `.tsx` needs its own grammar — the TypeScript one
#: reads `<Foo />` as a type assertion.
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
    """One parser per grammar, kept for the process. Loading a grammar is not free, and the
    coverage join asks for the same handful of languages once per file across a whole tree."""
    return get_parser(language)


def language_for(path: str | Path) -> str | None:
    """The grammar for *path*, or None when no front end can read it."""
    return LANGUAGES.get(Path(path).suffix)


@lru_cache(maxsize=16)
def _tree(language: str, text: str) -> Tree:
    """The last few files parsed, kept. `doctor` grounds every citation in a file separately
    and each one asks for that file's declarations, so a book with forty citations into one
    module used to re-read it forty times."""
    return _parser(language).parse(text.encode())


def parse(language: str, text: str) -> Node:
    """The root node of *text* read as *language*.

    Never raises on malformed input: tree-sitter's error recovery yields a tree with `ERROR`
    nodes around the part it could not read, and the rest stays usable. That is what makes a
    file mid-edit — the normal state of a tree `okf-builder` is walking — approximable rather
    than a hole in the inventory.
    """
    return _tree(language, text).root_node


def error_names(language: str, text: str) -> set[str]:
    """Every identifier inside a region the parser could not read.

    The counterpart to the recovery above, and the reason grounding does not get *stricter*
    when a file is broken. A half-typed `def render(self ->` parses to an `ERROR` node with no
    declaration in it, so a citation to `render` would flip to `missing-code-symbol` for as
    long as the edit is in flight — a red `doctor` caused by the working tree rather than by
    the book. The region the parser could not read is the region we have no knowledge about,
    so it grounds any name it mentions; everywhere else stays exact.
    """
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
    """Every named node in the subtree, root first, in source order.

    Iterative rather than recursive: a minified or deeply chained source file nests far enough
    to hit Python's recursion limit, and a `RecursionError` in the middle of `doctor` reads as
    a crash rather than as one unreadable file.
    """
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.named_children))


def text_of(node: Node | None) -> str:
    """The source *node* spans, decoded. An absent node spans nothing."""
    return "" if node is None else (node.text or b"").decode()


def field_text(node: Node, field: str) -> str:
    """The text of *node*'s `field` child — "" when the grammar did not fill it in, which is
    how an anonymous function or a declaration inside an `ERROR` region presents."""
    return text_of(node.child_by_field_name(field))


def lines_of(node: Node) -> tuple[int, int]:
    """*node*'s first and last line, 1-based and inclusive — a declaration's true extent.

    This is the property the line scan could not have: it read a declaration's *start* and
    guessed the end was wherever the next declaration began, so a hunk landing in a trailing
    comment was attributed to the function above it.
    """
    return node.start_point[0] + 1, node.end_point[0] + 1
