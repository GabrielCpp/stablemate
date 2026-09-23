"""Every turn is packed under a token budget before it is dispatched, and what does not fit is counted.

The one exception: a file over the budget goes alone. It is the only file its turn reads, and it is
read whole, because a turn shown part of a file answers about code it never saw. A file past
`ALONE_CEILING_TOKENS` is too large even for a turn of its own, and is left out like any other.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

TURN_BUDGET_TOKENS = 30_000
ALONE_CEILING_TOKENS = 100_000
CHARS_PER_TOKEN = 4
_BULLET_MARKUP = "- ``\n"


def estimated_tokens(size: int) -> int:
    """The tokens `size` characters cost, rounded up."""
    return -(-size // CHARS_PER_TOKEN)


@dataclass(frozen=True, slots=True)
class Packed:
    """The items a turn reads, in their given order, and how many the budget left out."""

    kept: tuple[str, ...]
    left_out: int
    tokens: int


def pack(items: Iterable[tuple[str, int]], budget: int) -> Packed:
    """Keep `(name, tokens)` items in order while they fit. A first item over the budget goes alone, up to the ceiling."""
    kept: list[str] = []
    left_out = 0
    spent = 0
    for name, tokens in items:
        if tokens > ALONE_CEILING_TOKENS or (kept and spent + tokens > budget):
            left_out += 1
            continue
        kept.append(name)
        spent += tokens
    return Packed(tuple(kept), left_out, spent)


def file_tokens(root: Path, paths: Iterable[str]) -> list[tuple[str, int]]:
    """Each repo-relative file with the tokens reading it and listing its path cost."""
    return [(path, estimated_tokens((root / path).stat().st_size + len(path) + len(_BULLET_MARKUP))) for path in paths]


def name_tokens(names: Iterable[str]) -> list[tuple[str, int]]:
    """Each name with the tokens listing it costs."""
    return [(name, estimated_tokens(len(name) + len(_BULLET_MARKUP))) for name in names]
