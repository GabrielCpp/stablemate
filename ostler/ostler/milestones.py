"""A milestone folder: which one is approved, and whether it is ready to be."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from urllib.parse import unquote

from ostler import graph as graph_mod
from ostler import links as links_mod
from ostler import markdown, reach, registry
from ostler.finding import Finding
from ostler.model import Graph, Milestone, read_doc, required_section_problems

APPROVED = "approved"
BLOCKING_STATUSES = frozenset({"approved", "authored", "delivered"})
SKIPPED_STATUSES = frozenset({"superseded"})

JOURNEY_LEVEL = 3
SERVICES_LABEL = "services"
MOCKUPS_DIR = "mockups"

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_URL_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)


class MilestoneSelectionError(ValueError):
    """The docs root has no approved milestone, or more than one."""


def journey_slug(title: str) -> str:
    """The file stem of a journey's mockup: its heading lowercased, runs of non-alphanumerics as `-`."""
    return _NON_ALNUM.sub("-", title.strip().lower()).strip("-")


def approved_milestones(graph: Graph) -> list[Milestone]:
    """Every milestone whose status is `approved`."""
    return [m for m in graph.milestones if m.status == APPROVED]


def approved_milestone(graph: Graph) -> Milestone:
    """The one approved milestone, or a `MilestoneSelectionError` naming every candidate."""
    approved = approved_milestones(graph)
    if len(approved) == 1:
        return approved[0]
    known = ", ".join(f"{m.name} ({m.status or 'no status'})" for m in graph.milestones) or "none"
    if not approved:
        raise MilestoneSelectionError(
            f"no milestone is approved, set `status: approved` on exactly one of: {known}")
    names = ", ".join(m.name for m in approved)
    raise MilestoneSelectionError(
        f"{len(approved)} milestones are approved ({names}), keep exactly one approved")


def check_layout(graph: Graph, f: list[Finding]) -> None:
    """Flat milestone files and a second approved milestone, both errors whatever the status."""
    mroot = graph.doc_roots.get("milestones")
    if mroot is None or not mroot.is_dir():
        return
    for path in sorted(mroot.glob("*.md")):
        if not path.is_file() or path.name in registry.RESERVED_FILES:
            continue
        try:
            fm = dict(read_doc(path).frontmatter or {})
        except OSError:
            continue
        if registry.base_type(registry.type_of(fm)) != "milestone":
            continue
        rel = _rel(graph, path)
        slug = path.stem
        f.append(Finding(
            "error", "legacy-milestone-file",
            f"{rel}: a milestone is a folder, move it to `docs/milestones/{slug}/milestone.md`",
            path=rel, line=1, ref=slug,
            suggestion=f"git mv {rel} docs/milestones/{slug}/milestone.md"))
    approved = approved_milestones(graph)
    if len(approved) > 1:
        names = ", ".join(m.name for m in approved)
        f.append(Finding(
            "error", "multiple-approved-milestones",
            f"{len(approved)} milestones are approved ({names}), and Author authors from exactly "
            f"one, so set every other to `proposed`, `authored`, `delivered` or `superseded`",
            path=_rel(graph, approved[0].path), line=1, ref=approved[0].name,
            related=[_rel(graph, m.path) for m in approved[1:]]))


def check_milestone(graph: Graph, milestone: Milestone, dump: dict | None = None) -> list[Finding]:
    """The readiness findings of one milestone, error or warn by its status, none once superseded."""
    if milestone.status in SKIPPED_STATUSES:
        return []
    try:
        doc = read_doc(milestone.path)
    except OSError:
        return []
    rel = _rel(graph, milestone.path)
    found = [
        *_missing_sections(milestone, doc, rel),
        *_open_decisions(milestone, doc, rel),
        *_dangling_links(milestone, doc, rel),
        *_journey_findings(graph, milestone, doc, rel, dump),
    ]
    if milestone.status in BLOCKING_STATUSES:
        return found
    return [replace(fd, severity="warn") for fd in found]


def check_milestones(graph: Graph, f: list[Finding], dump: dict | None = None) -> None:
    """Layout, then the readiness check of every milestone."""
    check_layout(graph, f)
    for milestone in graph.milestones:
        f.extend(check_milestone(graph, milestone, dump))


def _missing_sections(milestone: Milestone, doc: markdown.MarkdownDoc, rel: str) -> list[Finding]:
    found: list[Finding] = []
    for spec, problem in required_section_problems(doc, registry.MILESTONE_SECTIONS):
        state = "absent" if problem == "missing" else "empty, it needs prose"
        found.append(Finding(
            "error", "milestone-missing-section",
            f"{rel}: the required `## {spec.heading}` section is {state}",
            path=rel, line=1, ref=milestone.name, suggestion=f"## {spec.heading}"))
    return found


def _open_decisions(milestone: Milestone, doc: markdown.MarkdownDoc, rel: str) -> list[Finding]:
    section = doc.find_section(registry.MILESTONE_OPEN_DECISIONS_HEADING)
    if section is None:
        return []
    return [Finding(
        "error", "milestone-open-decisions",
        f"{rel}: `## {registry.MILESTONE_OPEN_DECISIONS_HEADING}` exists, so a decision is still "
        f"open, settle it in the right section and delete this one",
        path=rel, line=doc.body_offset + section.line_start + 1, ref=milestone.name)]


def _dangling_links(milestone: Milestone, doc: markdown.MarkdownDoc, rel: str) -> list[Finding]:
    found: list[Finding] = []
    folder = milestone.path.parent
    for _text, href, line in markdown.iter_links(doc.body):
        target = href.strip().split("#", 1)[0].split("?", 1)[0]
        if not target or _URL_SCHEME.match(href.strip()):
            continue
        if not (folder / unquote(target)).resolve().exists():
            found.append(Finding(
                "error", "milestone-dangling-link",
                f"{rel}: the link `{href}` resolves to no file",
                path=rel, line=doc.body_offset + line, ref=href))
    return found


def _journey_findings(graph: Graph, milestone: Milestone, doc: markdown.MarkdownDoc, rel: str,
                      dump: dict | None) -> list[Finding]:
    journeys = doc.find_section(registry.MILESTONE_JOURNEYS_HEADING)
    if journeys is None:
        return []
    found: list[Finding] = []
    services_root = graph.doc_roots.get("services")
    ui_books: set[str] | None = None
    for journey in journeys.children:
        if journey.level != JOURNEY_LEVEL:
            continue
        title = journey.title.strip()
        line = doc.body_offset + journey.line_start + 1
        slug = journey_slug(title)
        bullet = journey.labelled(SERVICES_LABEL)
        books = _books_of(bullet.value) if bullet is not None else []
        if not books:
            found.append(Finding(
                "error", "milestone-journey-services",
                f"{rel}: the journey `{title}` has no `- services: <book>, <book>` bullet",
                path=rel, line=line, ref=slug, suggestion="- services: <book>, <book>"))
            continue
        unknown = [b for b in books if services_root is None or not (services_root / b).is_dir()]
        for book in unknown:
            found.append(Finding(
                "error", "milestone-journey-services",
                f"{rel}: the journey `{title}` names the book `{book}`, which does not exist "
                f"under docs/services",
                path=rel, line=line, ref=slug))
        known = [b for b in books if b not in unknown]
        if not known or (milestone.path.parent / MOCKUPS_DIR / f"{slug}.html").is_file():
            continue
        if ui_books is None:
            ui_books = _ui_books(graph, dump)
        screen_books = [b for b in known if b in ui_books]
        if screen_books:
            found.append(Finding(
                "error", "milestone-missing-mockup",
                f"{rel}: the journey `{title}` goes through the {', '.join(screen_books)} UI "
                f"book but {MOCKUPS_DIR}/{slug}.html is missing",
                path=rel, line=line, ref=slug, suggestion=f"{MOCKUPS_DIR}/{slug}.html"))
    return found


def _books_of(value: str) -> list[str]:
    return [b for b in (part.strip().strip("`").strip() for part in value.split(",")) if b]


def _ui_books(graph: Graph, dump: dict | None) -> set[str]:
    """The books whose runbook driver is `web` or `mobile`."""
    if dump is None:
        try:
            dump = graph_mod.build(graph, resolver=links_mod.LinkResolver(graph))
        except (OSError, ValueError, RuntimeError, KeyError):
            return set()
    surfaces = {n["surface"] for n in dump["nodes"] if n["surface"]}
    return {s for s in surfaces if reach.surface_driver(dump, s) in reach.SCREEN_DRIVERS}


def _rel(graph: Graph, path: Path) -> str:
    return path.resolve().relative_to(graph.root.resolve()).as_posix()
