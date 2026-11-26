"""A milestone folder: which one is approved, and whether it is ready to be."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from urllib.parse import unquote

from ostler import markdown, registry
from ostler._vendor.stablemate_core import books
from ostler.finding import Finding
from ostler.model import Graph, Milestone, read_doc, required_section_problems

APPROVED = "approved"
BLOCKING_STATUSES = frozenset({"approved", "authored", "delivered"})
SKIPPED_STATUSES = frozenset({"superseded"})

JOURNEY_LEVEL = 3
SERVICES_LABEL = "services"
MOCKUPS_DIR = "mockups"
BOOKS_DIR = "services"
BOOK_FILE = "service.py"
SCREENS_DIR = "screens"

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_URL_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)


class MilestoneSelectionError(ValueError):
    """The docs root has no approved milestone, or more than one."""


def journey_slug(title: str) -> str:
    """The file stem of a journey's mockup: its heading lowercased, runs of non-alphanumerics as `-`."""
    return _NON_ALNUM.sub("-", title.strip().lower()).strip("-")


def service_books(graph: Graph, code: Path | None = None) -> set[str]:
    """The names of the service books: each folder under `services/` that holds a `service.py`, only those of the repositories *code* knows when it is a checkout outside the artifacts folder."""
    return set(_book_homes(graph, code))


def ui_services(graph: Graph, names: Iterable[str], code: Path | None = None) -> set[str]:
    """The books among *names* that have screens."""
    wanted = set(names)
    if not wanted:
        return set()
    screened = {
        name for name, homes in _book_homes(graph, code).items()
        if any((home / SCREENS_DIR).is_dir() or (home / f"{SCREENS_DIR}.py").is_file() for home in homes)
    }
    return wanted & screened


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
            f"{rel}: a milestone is a folder, move it to `{mroot}/{slug}/milestone.md`",
            path=rel, line=1, ref=slug,
            suggestion=f"mkdir -p {mroot}/{slug} && mv {path} {mroot}/{slug}/milestone.md"))
    unnumbered = [m for m in graph.milestones if registry.epic_seq(m.path.parent.name) is None]
    first = registry.next_epic_seq(m.path.parent.name for m in graph.milestones)
    for position, milestone in enumerate(unnumbered):
        rel = _rel(graph, milestone.path.parent)
        numbered = registry.epic_dir_name(first + position, milestone.path.parent.name)
        f.append(Finding(
            "warn", "milestone-folder-unnumbered",
            f"{rel}: a milestone folder carries its order as a number, as an epic's does",
            path=_rel(graph, milestone.path), line=1, ref=milestone.name,
            suggestion=f"git mv {rel} {_rel(graph, milestone.path.parent.parent)}/{numbered}"))
    approved = approved_milestones(graph)
    if len(approved) > 1:
        names = ", ".join(m.name for m in approved)
        f.append(Finding(
            "error", "multiple-approved-milestones",
            f"{len(approved)} milestones are approved ({names}), and Author authors from exactly "
            f"one, so set every other to `proposed`, `authored`, `delivered` or `superseded`",
            path=_rel(graph, approved[0].path), line=1, ref=approved[0].name,
            related=[_rel(graph, m.path) for m in approved[1:]]))


def check_milestone(graph: Graph, milestone: Milestone) -> list[Finding]:
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
        *_journey_findings(graph, milestone, doc, rel),
    ]
    if milestone.status in BLOCKING_STATUSES:
        return found
    return [replace(fd, severity="warn") for fd in found]


def check_milestones(graph: Graph, f: list[Finding]) -> None:
    """Layout, the milestones this checkout does not read, then the readiness check of every milestone."""
    check_layout(graph, f)
    check_unread(graph, f)
    for milestone in graph.milestones:
        f.extend(check_milestone(graph, milestone))
        f.extend(check_epic_list(graph, milestone))


def check_unread(graph: Graph, f: list[Finding]) -> None:
    """The milestones of other products, when the product read from here holds none: an error for each approved one."""
    mroot = graph.doc_roots.get("milestones")
    if mroot is None or mroot.is_dir():
        return
    for path in sorted(mroot.parent.parent.glob(f"*/{mroot.name}/*/{registry.MILESTONE_FILE}")):
        try:
            fm = dict(read_doc(path).frontmatter or {})
        except OSError:
            continue
        if registry.base_type(registry.type_of(fm)) != "milestone":
            continue
        rel = _rel(graph, path)
        product = path.parent.parent.parent.name
        f.append(Finding(
            "error" if str(fm.get("status") or "") in BLOCKING_STATUSES else "warn", "milestone-not-read",
            f"{rel}: this milestone of product `{product}` is not read from here, where the product is "
            f"`{mroot.parent.name}`, so nothing checked it and Author will not find it. Run from the "
            f"code checkout whose manifest sets `book.product: {product}`",
            path=rel, line=1, ref=path.parent.name))


def check_epic_list(graph: Graph, milestone: Milestone) -> list[Finding]:
    """The epic list Author writes: by id, and shown in `## Epics`; error or warn by status, none once superseded."""
    if milestone.status in SKIPPED_STATUSES:
        return []
    try:
        doc = read_doc(milestone.path)
    except OSError:
        return []
    found = _epic_list_findings(graph, milestone, doc, _rel(graph, milestone.path))
    if milestone.status in BLOCKING_STATUSES:
        return found
    return [replace(fd, severity="warn") for fd in found]


def _missing_sections(milestone: Milestone, doc: markdown.MarkdownDoc, rel: str) -> list[Finding]:
    found: list[Finding] = []
    for spec, problem in required_section_problems(doc, registry.MILESTONE_SECTIONS):
        state = "absent" if problem == "missing" else "empty, it needs prose"
        found.append(Finding(
            "error", "milestone-missing-section",
            f"{rel}: the required `## {spec.heading}` section is {state}",
            path=rel, line=1, ref=milestone.name, suggestion=f"## {spec.heading}"))
    return found


def epics_section_lines(graph: Graph, milestone: Milestone) -> list[str]:
    """The body ostler writes under a milestone's `## Epics`: one numbered line per epic, in coding order."""
    lines: list[str] = []
    for position, ref in enumerate(milestone.epic_refs, 1):
        epic = graph.epic_by_ref(ref)
        if epic is None:
            lines.append(f"{position}. `{ref}`, which names no epic")
        else:
            lines.append(f"{position}. {epic.title or epic.slug} (`{epic.eid or epic.name}`)")
    return lines


def _epic_list_findings(graph: Graph, milestone: Milestone, doc: markdown.MarkdownDoc,
                        rel: str) -> list[Finding]:
    """An epic listed by name instead of its id, and a `## Epics` section that is not the list."""
    if graph.profile != "full":
        return []
    found: list[Finding] = []
    fix = f"ostler milestone epics {milestone.name}"
    for ref in milestone.epic_refs:
        epic = graph.epic_by_ref(ref)
        if epic is not None and epic.eid and ref != epic.eid:
            found.append(Finding(
                "error", "milestone-epic-by-name",
                f"{rel}: `epics:` lists '{ref}' by name, list the epic by its id {epic.eid}",
                path=rel, line=1, ref=ref, suggestion=fix))
    section = doc.find_section(registry.MILESTONE_EPICS_HEADING)
    stated = [] if section is None else [
        line.strip() for line in section.body.splitlines() if line.strip()]
    expected = epics_section_lines(graph, milestone)
    if stated != expected:
        state = "absent" if section is None else "not the `epics:` list"
        found.append(Finding(
            "error", "milestone-epics-section",
            f"{rel}: the `## {registry.MILESTONE_EPICS_HEADING}` section is {state}, "
            f"so a reader cannot see which epics deliver the milestone",
            path=rel, line=1 if section is None else doc.body_offset + section.line_start + 1,
            ref=milestone.name, suggestion=fix))
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


def _journey_findings(graph: Graph, milestone: Milestone, doc: markdown.MarkdownDoc, rel: str) -> list[Finding]:
    journeys = doc.find_section(registry.MILESTONE_JOURNEYS_HEADING)
    if journeys is None:
        return []
    found: list[Finding] = []
    known_books = service_books(graph)
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
        unknown = [b for b in books if b not in known_books]
        for book in unknown:
            found.append(Finding(
                "error", "milestone-journey-services",
                f"{rel}: the journey `{title}` names the book `{book}`, which does not exist "
                f"under {BOOKS_DIR}/",
                path=rel, line=line, ref=slug))
    return found


def _books_of(value: str) -> list[str]:
    return [b for b in (part.strip().strip("`").strip() for part in value.split(",")) if b]


def _book_homes(graph: Graph, code: Path | None = None) -> dict[str, list[Path]]:
    """Each service book by name, with every folder that holds one of its `service.py` files: under `services/`, or under each repository folder of the artifacts folder, only those *code* knows when it is a checkout outside the artifacts folder."""
    home = Path(books.book_home(graph.root))
    base = home / BOOKS_DIR
    if not base.is_dir():
        return {}
    found: dict[str, list[Path]] = {}
    if books.namespaced(home):
        known = None if code is None or books.namespaced(code) else set(books.book_checkouts(code))
        for repository in sorted(d for d in base.iterdir() if d.is_dir() and not (d / BOOK_FILE).is_file()
                                 and (known is None or d.name in known)):
            for name, homes in _homes_under(repository).items():
                found.setdefault(name, []).extend(homes)
        return found
    return _homes_under(base)


def _homes_under(base: Path) -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = {}
    for folder in sorted(d for d in base.iterdir() if d.is_dir()):
        homes = [folder] if (folder / BOOK_FILE).is_file() else sorted(f.parent for f in folder.glob(f"*/{BOOK_FILE}"))
        if homes:
            found[folder.name] = homes
    return found


def _rel(graph: Graph, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(graph.root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()
