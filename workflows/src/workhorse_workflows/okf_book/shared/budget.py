"""Every turn is packed under a token budget before it is dispatched, and what does not fit is counted.

The one exception: a file over the budget goes alone. It is the only file its turn reads, and it is
read whole, because a turn shown part of a file answers about code it never saw. A file past
`ALONE_CEILING_TOKENS` is too large even for a turn of its own, and is left out like any other.
A file's body counts as a file the turn reads, whether the turn opens it or is shown it.
Other text a turn is told, such as names or problems, never goes alone: what does not fit is left out.
A prompt that loads a skill is charged the skill's reserved cost, because the harness resolves the
skill and the turn reads it whole.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

TURN_BUDGET_TOKENS = 30_000
ALONE_CEILING_TOKENS = 100_000
CHARS_PER_TOKEN = 4
SKILL_TOKENS = 8_000
PROBLEMS_BUDGET_TOKENS = 3_000
PROBLEM_TOKENS = 500
CHECK_OUTPUT_BUDGET_TOKENS = 3 * PROBLEMS_BUDGET_TOKENS
PACKAGE_DIR = Path(__file__).parents[1]
_SKILL_LOAD = "skill_load_ref("
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


def _pack(items: Iterable[tuple[str, int]], budget: int, *, alone: bool) -> Packed:
    kept: list[str] = []
    left_out = 0
    spent = 0
    for name, tokens in items:
        over = spent + tokens > budget
        if tokens > ALONE_CEILING_TOKENS or (over and (kept or not alone)):
            left_out += 1
            continue
        kept.append(name)
        spent += tokens
    return Packed(tuple(kept), left_out, spent)


def pack_read(items: Iterable[tuple[str, int]], budget: int) -> Packed:
    """Files a turn reads, as `(name, tokens)`, kept in order while they fit. A first one over the budget goes alone, up to the ceiling."""
    return _pack(items, budget, alone=True)


def pack_told(items: Iterable[tuple[str, int]], budget: int) -> Packed:
    """Text a turn is told, as `(name, tokens)`, kept in order while it fits. None goes alone past the budget."""
    return _pack(items, budget, alone=False)


def file_tokens(root: Path, paths: Iterable[str]) -> list[tuple[str, int]]:
    """Each repo-relative file with the tokens reading it and listing its path cost."""
    return [(path, estimated_tokens((root / path).stat().st_size + len(path) + len(_BULLET_MARKUP))) for path in paths]


def name_tokens(names: Iterable[str]) -> list[tuple[str, int]]:
    """Each name with the tokens listing it costs."""
    return [(name, estimated_tokens(len(name) + len(_BULLET_MARKUP))) for name in names]


def total_text_tokens(texts: Iterable[str]) -> int:
    """What listing each text as a bullet costs."""
    return sum(estimated_tokens(len(text) + len(_BULLET_MARKUP)) for text in texts)


def clip(text: str, budget: int) -> str:
    """The text cut to what `budget` tokens hold."""
    return text[: max(budget, 0) * CHARS_PER_TOKEN]


def pack_problems(problems: Iterable[str], budget: int = PROBLEMS_BUDGET_TOKENS) -> Packed:
    """The problems a turn is told, each clipped to its share, kept in order while they fit `budget`."""
    return pack_told(name_tokens(clip(problem, PROBLEM_TOKENS) for problem in problems), budget)


def prompt_tokens(prompt: str) -> int:
    """What a prompt of this package costs before any argument is rendered into it, with each skill it loads."""
    text = (PACKAGE_DIR / prompt).read_text(encoding="utf-8")
    return estimated_tokens(len(text)) + text.count(_SKILL_LOAD) * SKILL_TOKENS


@dataclass(frozen=True, slots=True)
class PageBody:
    """A repo-relative page and its whole text, which a turn is shown rather than told to read."""

    page: str
    body: str

    def template_arg(self) -> dict[str, str]:
        return {"page": self.page, "body": self.body}


def page_bodies(root: Path, pages: Iterable[str]) -> tuple[PageBody, ...]:
    """Each repo-relative page with its whole text."""
    return tuple(PageBody(page, (root / page).read_text(encoding="utf-8")) for page in pages)
