"""The compile defects a caller must repair before a touched book page is ready for QA."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ostler.qa.compile import compile_plan_gaps
from ostler.qa.outcome import QaOutcome
from ostler.qa.plan_source import Gap

DISCHARGED_GAPS = frozenset({"precondition-discharged-by-arrangement"})
NODE_OBLIGATION_SUFFIXES = (":contract", ":end-state")
UNDECLARED_GAP = "no-verify-declared"
_OBLIGATION_PAGE = re.compile(r"^okf:(?P<page>[^#:]+\.md)(?:#(?P<anchor>[^:]+))?")


def obligation_page(obligation_id: str) -> str:
    """The repo-relative page an obligation id names, empty when the id names none."""
    match = _OBLIGATION_PAGE.match(obligation_id)
    return match.group("page") if match else ""


def obligation_node(obligation_id: str) -> str:
    """The page and anchor an obligation id names, or the page alone when it names no anchor."""
    match = _OBLIGATION_PAGE.match(obligation_id)
    if not match:
        return ""
    return f"{match.group('page')}#{match.group('anchor')}" if match.group("anchor") else match.group("page")


def gap_page(gap: Gap) -> str:
    """The page a gap's fix goes on: its owner's page, else the page its obligation names."""
    return gap.owner.partition("#")[0] or obligation_page(gap.obligation_id)


def is_defect(gap: Gap) -> bool:
    """Whether a compile gap blocks readiness rather than recording discharged or placeholder debt."""
    if gap.kind in DISCHARGED_GAPS:
        return False
    return not (gap.kind == UNDECLARED_GAP and gap.obligation_id.endswith(NODE_OBLIGATION_SUFFIXES))


def defect_gaps(gaps: Iterable[Gap], pages: Iterable[str]) -> list[Gap]:
    """The blocking gaps on the given pages, in compile order."""
    touched = set(pages)
    return [gap for gap in gaps if is_defect(gap) and gap_page(gap) in touched]


def format_gap(gap: Gap) -> str:
    """The caller-visible `<code> <obligation>: <message>` line for one blocking gap."""
    return f"{gap.kind} {gap.obligation_id}: {gap.detail}"


def cmd_compile_gaps(spec_dir: Path, *, story: str = "", pages: Iterable[str]) -> QaOutcome:
    """Read the blocking compile gaps on a story's touched pages from its refreshed context packet."""
    context_file = spec_dir / "qa-okf-context.json"
    try:
        raw = json.loads(context_file.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{context_file} does not hold a context packet object")
        compiled = compile_plan_gaps(raw, story=story or "story")
    except (OSError, ValueError) as exc:
        return QaOutcome(
            ok=False,
            message=f"error: {exc}",
            status="invalid",
            data={"status": "invalid", "problems": [str(exc)]},
        )
    gaps = defect_gaps(compiled.gaps, pages)
    data: dict[str, Any] = {
        "gaps": [
            {
                "severity": "error",
                "code": gap.kind,
                "message": gap.detail,
                "ref": gap.obligation_id,
                "page": gap_page(gap),
            }
            for gap in gaps
        ]
    }
    if gaps:
        return QaOutcome(ok=False, message="\n".join(format_gap(gap) for gap in gaps), data=data)
    return QaOutcome(ok=True, message="no defect gaps on the touched pages", data=data)
