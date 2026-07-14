"""The `VetReport` shape, the `docs/specs/<slug>/vet.md` Concept read-modify-write, and the
dry-run-by-default file-write plan `ostler vet` applies with `--write`.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .. import markdown
from .manifest import DomElement
from .register import MatchedPair, MatchResult
from .regions import RegionBox


class VetSummary(BaseModel):
    status: Literal["clean", "disagreements"]
    matchedCount: int
    missingCount: int
    unexpectedCount: int
    unlabeledCount: int


class VetReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slug: str
    state: str
    screenshot: str
    manifest: str
    regions: str
    cdp_url: str | None = Field(default=None, alias="cdpUrl")
    manifest_errors: list[str] = Field(default_factory=list, alias="manifestErrors")
    config: dict
    summary: VetSummary
    matched: list[MatchedPair]
    missing: list[DomElement]
    unexpected: list[RegionBox]
    unlabeled: list[RegionBox]


def build_report(*, slug: str, state: str, screenshot: str, manifest: str, regions: str,
                  cdp_url: str | None, manifest_errors: list[str], iou_threshold: float,
                  match_result: MatchResult) -> VetReport:
    status: Literal["clean", "disagreements"] = (
        "disagreements"
        if match_result.missing or match_result.unexpected or match_result.unlabeled
        else "clean"
    )
    summary = VetSummary(
        status=status,
        matchedCount=len(match_result.matched),
        missingCount=len(match_result.missing),
        unexpectedCount=len(match_result.unexpected),
        unlabeledCount=len(match_result.unlabeled),
    )
    return VetReport(
        slug=slug, state=state, screenshot=screenshot, manifest=manifest, regions=regions,
        cdp_url=cdp_url, manifest_errors=manifest_errors,
        config={"iouThreshold": iou_threshold}, summary=summary,
        matched=match_result.matched, missing=match_result.missing,
        unexpected=match_result.unexpected, unlabeled=match_result.unlabeled,
    )


# ---------------------------------------------------------------------------
# docs/specs/<slug>/vet.md Concept — type: spec.vet, one `## State: <name>` section per state
# ---------------------------------------------------------------------------
def _state_frontmatter_entry(report: VetReport) -> dict:
    return {
        "status": report.summary.status,
        "matchedCount": report.summary.matchedCount,
        "missingCount": report.summary.missingCount,
        "unexpectedCount": report.summary.unexpectedCount,
        "unlabeledCount": report.summary.unlabeledCount,
        "report": f"vet/{report.state}-report.json",
    }


def _state_section_lines(title: str, report: VetReport) -> list[str]:
    lines = [
        f"## {title}", "",
        f"- status: {report.summary.status}",
        f"- screenshot: {report.screenshot}",
        f"- manifest: {report.manifest}",
        f"- matched: {report.summary.matchedCount}",
        f"- missing: {report.summary.missingCount}",
        f"- unexpected: {report.summary.unexpectedCount}",
        f"- unlabeled: {report.summary.unlabeledCount}",
        "",
    ]
    if report.matched:
        lines += ["### Matched (documented components registered on screen)", ""]
        lines += [f"- `{p.dom.name or p.dom.selector}` — iou {p.iou:.2f}"
                 f"{f' — crop: {p.crop}' if p.crop else ''}" for p in report.matched]
        lines.append("")
    if report.missing:
        lines += ["### Missing (expected, not rendered)", ""]
        lines += [f"- `{dom.selector}` (role: {dom.role or 'unlabeled'})" for dom in report.missing]
        lines.append("")
    if report.unexpected:
        lines += ["### Unexpected (rendered, not expected)", ""]
        lines += [f"- role `{r.role}` at {r.bbox.x:.0f},{r.bbox.y:.0f} "
                 f"(`{', '.join(r.selectors)}`)" for r in report.unexpected]
        lines.append("")
    if report.unlabeled:
        lines += ["### Unlabeled (rendered, no accessibility role — needs VLM review)", ""]
        lines += [f"- at {r.bbox.x:.0f},{r.bbox.y:.0f} (`{', '.join(r.selectors)}`)"
                 f"{f' — crop: {r.crop}' if r.crop else ''}" for r in report.unlabeled]
        lines.append("")
    return lines


def _replace_or_append_section(doc: markdown.MarkdownDoc, title: str, new_lines: list[str]) -> str:
    section = doc.find_section(title)
    lines = doc.body.split("\n")
    if section is not None:
        lines[section.line_start:section.line_end] = new_lines
        return "\n".join(lines)
    while lines and lines[-1] == "":
        lines.pop()
    lines += [""] + new_lines
    return "\n".join(lines) + "\n"


def build_vet_concept(existing_raw: str | None, report: VetReport) -> str:
    """Read-modify-write `vet.md`: accumulates one frontmatter entry + body section per
    `--state`, replacing in place on re-run of the same state. Top-level `status` is
    `disagreements` if *any* recorded state is."""
    raw = existing_raw or f"---\ntype: spec.vet\nslug: {report.slug}\n---\n# Vet: {report.slug}\n"
    doc = markdown.split(raw)
    fm = doc.frontmatter or {"type": "spec.vet", "slug": report.slug}
    fm["type"] = "spec.vet"
    fm["slug"] = report.slug
    states = fm.get("states") or {}
    states[report.state] = _state_frontmatter_entry(report)
    fm["states"] = states
    fm["status"] = ("disagreements"
                    if any(s["status"] == "disagreements" for s in states.values())
                    else "clean")
    doc.raw_frontmatter = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)

    title = f"State: {report.state}"
    doc.body = _replace_or_append_section(doc, title, _state_section_lines(title, report))
    return doc.render()


# ---------------------------------------------------------------------------
# Dry-run-by-default file-write plan (own small classes: writes into a `vet/` subdir that
# may not exist yet, and optionally writes binary crop files — unlike edit.EditPlan/FileChange).
# ---------------------------------------------------------------------------
@dataclass
class VetFileWrite:
    path: Path
    content: str | bytes

    def diff(self) -> str:
        if isinstance(self.content, bytes):
            if self.path.is_file() and self.path.read_bytes() == self.content:
                return ""
            return f"write {self.path.as_posix()} ({len(self.content)} bytes)\n"
        old = self.path.read_text(encoding="utf-8") if self.path.is_file() else ""
        if old == self.content:
            return ""
        rel = self.path.as_posix()
        return "".join(difflib.unified_diff(
            old.splitlines(keepends=True), self.content.splitlines(keepends=True),
            fromfile=f"a/{rel}", tofile=f"b/{rel}",
        ))

    def apply(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(self.content, bytes):
            self.path.write_bytes(self.content)
        else:
            self.path.write_text(self.content, encoding="utf-8")


@dataclass
class VetPlan:
    writes: list[VetFileWrite]
    error: str = ""

    def render(self) -> str:
        if self.error:
            return f"error: {self.error}"
        parts = [d for w in self.writes if (d := w.diff())]
        return "".join(parts) if parts else "no changes"

    def apply(self) -> None:
        for w in self.writes:
            w.apply()
