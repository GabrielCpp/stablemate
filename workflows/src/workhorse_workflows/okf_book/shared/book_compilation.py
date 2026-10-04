"""Compiling the named services' books into a QA plan, and reading the page and node an obligation id names.

The compile keeps only the obligations the named books' pages state, and every gap that is a
defect. Two gaps are no defect at all: a precondition the arrangement already discharges, and the
placeholder obligation every node mints for itself, which owes a check only through the claims
under it.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter, model_validator

from ostler import index
from ostler.qa.compile import Plan, compile_plan_gaps
from ostler.qa.context import book_context, validate_context, write_context
from ostler.qa.plan_source import Gap
from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR
from workhorse_workflows.okf_book.shared.production import production_files

BOOK_STORY = "book"
DISCHARGED_GAPS = frozenset({"precondition-discharged-by-arrangement"})
NODE_OBLIGATION_SUFFIXES = (":contract", ":end-state")
UNDECLARED_GAP = "no-verify-declared"
_OBLIGATION_PAGE = re.compile(r"^okf:(?P<page>[^#:]+\.md)(?:#(?P<anchor>[^:]+))?")


def obligation_page(obligation_id: str) -> str:
    """The repo-relative page an obligation id names, empty when the id names none."""
    match = _OBLIGATION_PAGE.match(obligation_id)
    return match.group("page") if match else ""


def obligation_node(obligation_id: str) -> str:
    """The page and anchor of the node an obligation id names, `page#anchor`, or the page alone when it names no anchor."""
    match = _OBLIGATION_PAGE.match(obligation_id)
    if not match:
        return ""
    return f"{match.group('page')}#{match.group('anchor')}" if match.group("anchor") else match.group("page")


def gap_page(gap: Gap) -> str:
    """The repo-relative page a gap's fix goes on: its owner's page, else the page its obligation names, empty when it names none."""
    return gap.owner.partition("#")[0] or obligation_page(gap.obligation_id)


def is_defect(gap: Gap) -> bool:
    """False for a discharged precondition and for a node's own placeholder obligation with no check."""
    if gap.kind in DISCHARGED_GAPS:
        return False
    return not (gap.kind == UNDECLARED_GAP and gap.obligation_id.endswith(NODE_OBLIGATION_SUFFIXES))


@dataclass(frozen=True, slots=True)
class BookCompilation:
    """What compiling the books gave: the plan, when one compiled, every defect gap either way, and the obligations that arrange each fixture."""

    plan: Plan | None
    gaps: tuple[Gap, ...]
    obligations: tuple[str, ...] = ()
    arranging: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def planned(self) -> bool:
        return self.plan is not None


_JSON_FIELDS = TypeAdapter(dict[str, JsonValue])
_FIXTURES_DECLARED = TypeAdapter(list[dict[str, JsonValue]])


class _Obligation(BaseModel):
    """One obligation of a QA context, named by the page and node it checks. Ostler's other fields ride along as extras."""

    model_config = ConfigDict(frozen=True, extra="allow")

    id: str

    @model_validator(mode="after")
    def _extras_are_json(self) -> _Obligation:
        _ = _JSON_FIELDS.validate_python(self.model_extra or {})
        return self

    @property
    def fixtures(self) -> tuple[str, ...]:
        """The names of the fixtures the obligation arranges."""
        declared = _FIXTURES_DECLARED.validate_python((self.model_extra or {}).get("fixturesDeclared", []))
        return tuple(str(fixture["name"]) for fixture in declared if "name" in fixture)


class _ServicesContext(BaseModel):
    """The QA context of some services' books, which is written for the run and compiled into a plan.

    The fields are the ones every context carries. Ostler's own fields ride along as extras, untouched.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    version: Literal[1, 2]
    available: bool
    obligations: tuple[_Obligation, ...]

    def write(self, spec: Path) -> None:
        _ = write_context(self.model_dump(mode="json"), spec)

    def compile(self) -> BookCompilation:
        compiled = compile_plan_gaps(self.model_dump(mode="json"), story=BOOK_STORY)
        gaps = tuple(gap for gap in compiled.gaps if is_defect(gap))
        obligations = tuple(obligation.id for obligation in self.obligations)
        arranging: dict[str, tuple[str, ...]] = {}
        for obligation in self.obligations:
            for fixture in obligation.fixtures:
                arranging[fixture] = (*arranging.get(fixture, ()), obligation.id)
        plan = compiled if isinstance(compiled, Plan) else None
        return BookCompilation(plan=plan, gaps=gaps, obligations=obligations, arranging=arranging)


def compile_services(root: Path, services: Iterable[str], spec: Path | None = None) -> BookCompilation:
    """Compile the named services' books, each with its production files as its source.

    Only the obligations those books' pages state are compiled. Another book's pages still inform
    the context, but its scenarios are not this run's. The QA context is written into `spec` first,
    when one is given. The pages parse through ostler's index, so a compile after an earlier one
    reparses only the pages written since.
    """
    sources = {service: sorted(production_files(root, service)) for service in services}
    with index.session(root):
        packet = book_context(root, source_roots=sources, books=[(FEATURES_DIR / service).as_posix() for service in sources])
    problems = validate_context(packet)
    if problems:
        raise ValueError(f"the books' QA context is malformed: {'; '.join(problems)}")
    context = _ServicesContext.model_validate(packet)
    if spec is not None:
        context.write(spec)
    return context.compile()
