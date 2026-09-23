"""The context of the turn that lists a surface's entry points, packed under the turn budget."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from workhorse_workflows.okf_book.budget import TURN_BUDGET_TOKENS, Packed, estimated_tokens, file_tokens, name_tokens, pack_read, pack_told
from workhorse_workflows.okf_book.imports import reached_files
from workhorse_workflows.okf_book.stubs import entry_slugs
from workhorse_workflows.okf_book.surface import Surface

LISTING_PROMPT = "prompts/list-entry-points.md"
SLUG_LIST_BUDGET_TOKENS = 3_000


def prompt_tokens() -> int:
    """What the prompt's own text costs before any file is listed."""
    return estimated_tokens(len((Path(__file__).parent / LISTING_PROMPT).read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class ListingContext:
    """The surface, the files the turn reads nearest the entry first, and the entry slugs it may reuse."""

    surface: Surface
    files: Packed
    slugs: Packed

    def template_args(self) -> dict[str, object]:
        return {
            "service": self.surface.service,
            "kind": self.surface.kind.value,
            "entry": self.surface.entry,
            "files": self.files.kept,
            "files_left_out": self.files.left_out,
            "slugs": self.slugs.kept,
            "slugs_left_out": self.slugs.left_out,
        }

    def entry_fits(self) -> bool:
        """Whether the turn reads the entry file itself, which it cannot when the file is gone or past the ceiling."""
        return self.surface.entry in self.files.kept


def listing_context(root: Path, surface: Surface, budget: int = TURN_BUDGET_TOKENS) -> ListingContext:
    """Charge the prompt and the entry slugs first, then pack the files nearest the entry into what is left."""
    slugs = pack_told(name_tokens(entry_slugs(root, surface)), SLUG_LIST_BUDGET_TOKENS)
    files = pack_read(file_tokens(root, reached_files(root, [surface.entry])), max(budget - prompt_tokens() - slugs.tokens, 0))
    return ListingContext(surface, files, slugs)
