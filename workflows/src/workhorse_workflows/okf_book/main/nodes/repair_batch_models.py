"""What the repair is planned as: the pages one turn repairs, the batches they are sent in, and the parts too large for any turn."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.main.nodes.journey import JourneyPages
from workhorse_workflows.okf_book.main.nodes.page_sections import HEAD_SECTION_ID

class PageRepair(BaseModel):
    """One page to repair, repo-relative, each problem the check reports on it, and the parts of files it cites.

    A page too large for one writer names the `###` sections the turn repairs, `HEAD_SECTION_ID` for the lines
    under no `###` heading. With none named, the turn repairs the whole page.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    page: str
    problems: tuple[str, ...]
    sources: tuple[str, ...] = ()
    sections: tuple[str, ...] = ()

    def joined(self, other: PageRepair) -> PageRepair:
        """This repair and another of the same page's sections, as one."""
        return self.model_copy(
            update={
                "problems": (*self.problems, *other.problems),
                "sources": tuple(dict.fromkeys((*self.sources, *other.sources))),
                "sections": (*self.sections, *other.sections),
            }
        )


class RepairBatch(BaseModel):
    """The pages one repair turn is sent, the journey pages it may also change, the new flow page it may write, and the tokens of those pages and the files they cite."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pages: tuple[PageRepair, ...]
    tokens: int
    journey: JourneyPages | None = None
    new_flow_page: str = ""

    @property
    def page_paths(self) -> tuple[str, ...]:
        return tuple(repair.page for repair in self.pages)

    def owns(self, path: str) -> bool:
        """Whether the turn may change the path: one of its pages, a journey page, or the new flow page planned for it."""
        if path in self.page_paths:
            return True
        return self.journey is not None and (self.journey.owns(path) or path == self.new_flow_page)

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(source for repair in self.pages for source in repair.sources))


class OversizedPart(BaseModel):
    """A problem page, or one `###` section of it, no turn is sent, since it, the files it cites and what the writer reads of the journey pages its fix goes on cost more than one writer reads."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page: str
    tokens: int
    ceiling: int
    with_journey: bool = False
    section: str | None = None

    @property
    def subject(self) -> str:
        """The page, or the section of it, no turn was sent."""
        if self.section is None:
            return self.page
        return f"{self.page}, the lines under no ### heading" if self.section == HEAD_SECTION_ID else f"{self.page}, ### {self.section}"

    @property
    def reason(self) -> str:
        counted = ", the files it cites and the journey pages its fix goes on" if self.with_journey else " and the files it cites"
        part = "page" if self.section is None else "section"
        split = f"split the {part} or the flow pages" if self.with_journey else f"split the {part}"
        return (
            f"{self.subject}{counted} cost {self.tokens} tokens, over the {self.ceiling} one writer reads, "
            + f"so no repair turn was sent it: {split}"
        )


class PackedRepairs(BaseModel):
    """The batches the repair turns are sent, and the pages too large for any of them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    batches: tuple[RepairBatch, ...]
    oversized_parts: tuple[OversizedPart, ...] = ()
