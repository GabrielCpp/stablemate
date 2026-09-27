"""The lines of a cited file a claim rests on: the declaration it names, the key it names in a yaml file, or the whole file.

A writer checks a claim against what its citation names, so a citation of one declaration in a large
file costs the turn that declaration, not the file. A citation that names no symbol, or one this
cannot find, costs the whole file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ostler.inventory import extents

from workhorse_workflows.okf_book.main.nodes.turn_budget import CHARS_PER_TOKEN
from workhorse_workflows.okf_book.shared.citations import Citation

YAML_SUFFIXES = frozenset({".yaml", ".yml"})


@dataclass(frozen=True, slots=True)
class CitedLines:
    """The part of one file a citation names, repo-relative, and its tokens. `span` is `(first, last)`, 1-based and inclusive, or None for the whole file."""

    path: str
    span: tuple[int, int] | None
    tokens: int

    @property
    def label(self) -> str:
        return self.path if self.span is None else f"{self.path}:{self.span[0]}-{self.span[1]}"


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _is_content(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def _block_end(lines: list[str], start: int, stop: int, indent: int) -> int:
    end = start
    for index in range(start + 1, stop):
        if _is_content(lines[index]):
            if _indent(lines[index]) <= indent:
                break
            end = index
    return end


def _yaml_key(line: str) -> str:
    return line.strip().partition(":")[0].strip().strip("'\"")


def yaml_lines(text: str, dotted: str) -> tuple[int, int] | None:
    """The lines of the block a dotted key path names in a yaml file, 1-based and inclusive, or None when no key matches.

    A key may itself hold a dot, such as a path, so each step takes the key that the rest of the
    dotted path starts with, followed by a dot or the end.
    """
    lines = text.splitlines()
    start, stop, found = 0, len(lines), None
    rest = dotted
    while rest:
        children = [index for index in range(start, stop) if _is_content(lines[index])]
        if not children:
            return None
        indent = _indent(lines[children[0]])
        match = next(
            (
                index
                for index in children
                if _indent(lines[index]) == indent
                and (rest == _yaml_key(lines[index]) or rest.startswith(_yaml_key(lines[index]) + "."))
            ),
            None,
        )
        if match is None:
            return None
        key = _yaml_key(lines[match])
        end = _block_end(lines, match, stop, indent)
        found = (match + 1, end + 1)
        rest = rest[len(key) + 1 :]
        start, stop = match + 1, end + 1
    return found


def _symbol_lines(path: Path, text: str, symbol: str) -> tuple[int, int] | None:
    if path.suffix in YAML_SUFFIXES:
        return yaml_lines(text, symbol)
    return next(((first, last) for first, last, name in extents(path, text) if name == symbol), None)


def _tokens(chars: int) -> int:
    return -(-chars // CHARS_PER_TOKEN)


@dataclass
class CitedFiles:
    """Reads each cited file of a repository once, and gives the part of it a citation names."""

    root: Path
    _texts: dict[str, str] = field(default_factory=dict)

    def _text(self, path: str) -> str:
        if path not in self._texts:
            self._texts[path] = (self.root / path).read_text(encoding="utf-8", errors="replace")
        return self._texts[path]

    def cited(self, citation: Citation) -> CitedLines | None:
        """The lines `citation` names and their tokens, or None when it names no file of the repository."""
        path = self.root / citation.path
        if not path.is_file():
            return None
        text = self._text(citation.path)
        span = _symbol_lines(path, text, citation.symbol) if citation.symbol else None
        if span is None:
            return CitedLines(citation.path, None, _tokens(path.stat().st_size))
        first, last = span
        chars = sum(len(line) + 1 for line in text.splitlines()[first - 1 : last])
        return CitedLines(citation.path, span, _tokens(chars))
