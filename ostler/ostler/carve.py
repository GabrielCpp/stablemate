"""`ostler edit carve-endpoints`: a server page's endpoints, each moved to its own page with the invocations that call it."""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ostler import crud, markdown, registry
from ostler.edit import EditPlan, FileChange, _doc_files
from ostler.links import is_doc_link
from ostler.model import Graph, _inline_type, anchor_of, document_anchors, read_doc

_HREF = re.compile(r"\]\(([^)\s]+)\)")
_LOCATOR = re.compile(r"""locator=(["'])([^"'#]*#[^"']*)\1""")
_ATX = re.compile(r"^(#{1,6})(?=\s|$)")
_INVOCATIONS = "Invocations"

Address = tuple[Path, str]


class CarveError(Exception):
    pass


@dataclass
class CarvePlan(EditPlan):
    summary: list[str] = field(default_factory=list)

    def render(self) -> str:
        if self.error:
            return f"error: {self.error}"
        return "\n".join(self.summary) + "\n"


@dataclass
class _Unit:
    section: markdown.Section
    kind: str
    page: str
    shift: int
    excluded: list[tuple[int, int]] = field(default_factory=list)

    @property
    def span(self) -> tuple[int, int]:
        return self.section.line_start, self.section.line_end


@dataclass
class _Page:
    name: str
    title: str
    path: Path
    body: list[str]
    origin: dict[int, int]
    added: list[str]


def _typed_sections(doc: markdown.MarkdownDoc) -> list[tuple[markdown.Section, str]]:
    found: list[tuple[markdown.Section, str]] = []

    def visit(section: markdown.Section, container: str | None) -> None:
        title = section.title.strip()
        if not title:
            return
        child_container = registry.UI_HEADING_TO_TYPE.get(title)
        if child_container is not None:
            for sub in section.children:
                visit(sub, child_container)
            return
        ntype, _ = _inline_type(title)
        found.append((section, ntype or container or "untyped"))
        for sub in section.children:
            visit(sub, None)

    for root in doc.sections:
        visit(root, None)
    return found


def _target(source: Path, path_part: str) -> Path:
    return source if path_part == "" else Path(os.path.normpath(source.parent / path_part))


def _on_targets(section: markdown.Section, server: Path, endpoints: dict[str, _Unit]) -> set[str]:
    hits: set[str] = set()
    for bullet in section.bullets:
        if bullet.label != "on":
            continue
        for _, href, _ in markdown.iter_links(bullet.text):
            path_part, _, anchor = href.strip().partition("#")
            if is_doc_link(href) and _target(server, path_part) == server and anchor in endpoints:
                hits.add(anchor)
    return hits


def _units(doc: markdown.MarkdownDoc, server: Path) -> list[_Unit]:
    anchors = document_anchors(doc)
    typed = _typed_sections(doc)
    endpoints: dict[str, _Unit] = {}
    for section, ntype in typed:
        if ntype == "endpoint":
            name = anchor_of(_inline_type(section.title.strip())[1])
            if not name:
                raise CarveError(f"endpoint heading {section.title.strip()!r} gives no page name")
            endpoints[anchors[section.line_start]] = _Unit(section, "endpoint", name, section.level - 1)
    units = list(endpoints.values())
    for section, ntype in typed:
        if ntype == "invocation":
            hits = _on_targets(section, server, endpoints)
            if len(hits) == 1:
                units.append(_Unit(section, "invocation", endpoints[hits.pop()].page,
                                   section.level - 3))
    for unit in units:
        start, end = unit.span
        unit.excluded = [o.span for o in units
                         if o is not unit and start < o.span[0] and o.span[1] <= end]
    return sorted(units, key=lambda u: u.span[0])


def _shifted(line: str, shift: int) -> str:
    match = _ATX.match(line)
    if match is None:
        raise CarveError(f"heading {line.strip()!r} is not an ATX heading")
    level = len(match.group(1)) - shift
    if not 1 <= level <= 6:
        raise CarveError(f"heading {line.strip()!r} would land at level {level}")
    return "#" * level + line[match.end():]


def _unit_lines(lines: list[str], unit: _Unit, headings: set[int]) -> list[tuple[int, str]]:
    start, end = unit.span
    out: list[tuple[int, str]] = []
    for i in range(start, end):
        if any(a <= i < b for a, b in unit.excluded):
            continue
        out.append((i, _shifted(lines[i], unit.shift) if i in headings else lines[i]))
    return out


def _trim(block: list[tuple[int, str]]) -> list[tuple[int, str]]:
    while block and not block[0][1].strip():
        block = block[1:]
    while block and not block[-1][1].strip():
        block = block[:-1]
    return block


def _build_page(lines: list[str], endpoint: _Unit, invocations: list[_Unit], headings: set[int],
                server: Path, server_title: str) -> _Page:
    body: list[str] = []
    origin: dict[int, int] = {}

    def put(old: int | None, text: str) -> None:
        if old is not None:
            origin[old] = len(body)
        body.append(text)

    own = _trim(_unit_lines(lines, endpoint, headings))
    put(*own[0])
    rest = _trim(own[1:])
    server_bullet = f"- server: [{server_title}]({server.name})"
    put(None, "")
    put(None, server_bullet)
    if rest and not rest[0][1].lstrip().startswith(("- ", "* ")):
        put(None, "")
    for old, text in rest:
        put(old, text)
    added = [server_bullet]
    if invocations:
        put(None, "")
        put(None, f"## {_INVOCATIONS}")
        added.append(_INVOCATIONS)
        for unit in invocations:
            put(None, "")
            for old, text in _trim(_unit_lines(lines, unit, headings)):
                put(old, text)
    put(None, "")
    title = _inline_type(endpoint.section.title.strip())[1]
    return _Page(endpoint.page, title, server.parent / f"{endpoint.page}.md", body, origin, added)


def _endpoints_section(doc: markdown.MarkdownDoc) -> markdown.Section:
    heading = registry.UI_TYPES_BY_NAME["endpoint"].heading
    for section in doc.walk_sections():
        if section.title.strip() == heading:
            return section
    raise CarveError(f"the server page has no `## {heading}` section to list its endpoint pages")


def _own_end(section: markdown.Section) -> int:
    return min((c.line_start for c in section.children), default=section.line_end)


def _slim_server(doc: markdown.MarkdownDoc, lines: list[str], units: list[_Unit]
                 ) -> tuple[list[str], dict[int, int], list[str], list[str]]:
    remove: set[int] = set()
    for unit in units:
        remove.update(range(*unit.span))
    host = _endpoints_section(doc)
    endpoint_units = [u for u in units if u.kind == "endpoint"]
    direct = [u for u in endpoint_units if any(u.section is c for c in host.children)]
    ordered = direct + [u for u in endpoint_units if u not in direct]
    links = [f"- [{u.page}]({u.page}.md)" for u in ordered]
    insert_at = direct[0].span[0] if direct else _own_end(host)

    dropped: list[str] = []
    for section in doc.walk_sections():
        title = section.title.strip()
        if (title in registry.UI_HEADING_TO_TYPE and section is not host and section.children
                and all(c.line_start in remove for c in section.children)
                and not any(lines[i].strip() for i in range(section.line_start + 1, _own_end(section)))):
            remove.update(range(section.line_start, _own_end(section)))
            dropped.append(title)

    body: list[str] = []
    where: dict[int, int] = {}
    skip_blank = False

    def emit_links() -> None:
        last = next((t for t in reversed(body) if t.strip()), "")
        if last.startswith("- ["):
            while not body[-1].strip():
                body.pop()
            for i in [i for i, at in where.items() if at >= len(body)]:
                del where[i]
        elif body and body[-1].strip():
            body.append("")
        body.extend(links)
        body.append("")

    for i, text in enumerate(lines):
        if i == insert_at:
            emit_links()
            skip_blank = True
        if i in remove:
            continue
        if skip_blank and not text.strip():
            continue
        skip_blank = False
        where[i] = len(body)
        body.append(text)
    if insert_at >= len(lines):
        emit_links()
    while body and not body[-1].strip():
        body.pop()
    body.append("")
    return body, where, links, dropped


def _heading_anchors(body: list[str]) -> dict[int, str]:
    return document_anchors(markdown.split("\n".join(body)))


def _address_map(server: Path, old: dict[int, str], placements: list[tuple[Path, dict[int, int], list[str], set[int]]]
                 ) -> dict[Address, Address]:
    moved: dict[Address, Address] = {}
    for path, origin, body, roots in placements:
        new = _heading_anchors(body)
        tracked = {origin[o] for o in old if o in origin}
        if not tracked <= set(new):
            raise CarveError(f"{path.name}: a moved heading no longer parses as a heading")
        for o, anchor in old.items():
            if o in origin:
                moved[(server, anchor)] = (path, "" if o in roots else new[origin[o]])
    return moved


def _rewrite(text: str, origin: Path, location: Path, server: Path,
             moved: dict[Address, Address]) -> str:
    def moved_href(href: str) -> str | None:
        if not is_doc_link(href):
            return None
        path_part, _, anchor = href.partition("#")
        if _target(origin, path_part) != server:
            return None
        new_path, new_anchor = moved.get((server, anchor), (server, anchor))
        if new_path == location:
            part = "" if new_anchor else location.name
        elif new_path == server and location == origin:
            part = path_part
        else:
            part = Path(os.path.relpath(new_path, location.parent)).as_posix()
        return f"{part}#{new_anchor}" if new_anchor else part

    def swap(match: re.Match[str]) -> str:
        href = moved_href(match.group(1))
        return match.group(0) if href is None else f"]({href})"

    def swap_locator(match: re.Match[str]) -> str:
        href = moved_href(match.group(2))
        quote = match.group(1)
        return match.group(0) if href is None else f"locator={quote}{href}{quote}"

    return _LOCATOR.sub(swap_locator, _HREF.sub(swap, text))


def references(text: str) -> list[str]:
    """Every in-book address the text points at: its links' targets and its checks' locators."""
    return [href for _, href, _ in markdown.iter_links(text)] + [m.group(2) for m in _LOCATOR.finditer(text)]


def _claims(lines: list[str]) -> Counter[str]:
    found: Counter[str] = Counter()
    for line in lines:
        stripped = line.strip()
        if stripped:
            found[_HREF.sub("]()", stripped.lstrip("#").strip())] += 1
    return found


def _broken(files: list[Path], texts: dict[Path, str], moved: dict[Address, Address]) -> Counter[Address]:
    anchors: dict[Path, set[str]] = {}

    def anchors_of(path: Path) -> set[str]:
        if path not in anchors:
            if path in texts:
                anchors[path] = set(document_anchors(markdown.split(texts[path])).values())
            else:
                anchors[path] = set(document_anchors(read_doc(path)).values())
        return anchors[path]

    broken: Counter[Address] = Counter()
    for path in files:
        text = texts[path] if path in texts else path.read_text(encoding="utf-8")
        for href in references(text):
            if not is_doc_link(href):
                continue
            path_part, _, anchor = href.strip().partition("#")
            target = _target(path, path_part)
            if not (target in texts or target.is_file()):
                broken[moved.get((target, anchor), (target, anchor))] += 1
            elif anchor and anchor not in anchors_of(target):
                broken[moved.get((target, anchor), (target, anchor))] += 1
    return broken


def _render(fm: dict, body: list[str]) -> str:
    return f"---\n{crud.dump_frontmatter(fm)}---\n" + "\n".join(body)


def _carve(graph: Graph, server: Path) -> CarvePlan:
    raw = server.read_text(encoding="utf-8")
    doc = markdown.split(raw)
    fm = doc.frontmatter or {}
    if registry.type_of(fm) != "server":
        raise CarveError(f"{server.name} is not a server page")
    lines = doc.body.split("\n")
    headings = {s.line_start for s in doc.walk_sections() if s.level}
    units = _units(doc, server)
    endpoints = [u for u in units if u.kind == "endpoint"]
    if not endpoints:
        raise CarveError(f"{server.name} holds no endpoint to carve")
    names = Counter(u.page for u in endpoints)
    if clash := sorted(n for n, c in names.items() if c > 1):
        raise CarveError(f"two endpoints would share a page: {', '.join(clash)}")
    if taken := sorted(n for n in names if (server.parent / f"{n}.md").exists()):
        raise CarveError(f"a page already exists for: {', '.join(taken)}")

    h1 = next((s for s in doc.sections if s.level == 1), None)
    server_title = str(fm.get("title") or (h1.title.strip() if h1 else server.stem))
    pages = [_build_page(lines, ep, [u for u in units if u.kind == "invocation" and u.page == ep.page],
                         headings, server, server_title) for ep in endpoints]
    body, where, links, dropped = _slim_server(doc, lines, units)

    old = document_anchors(doc)
    placements = [(p.path, p.origin, p.body, {ep.span[0]}) for p, ep in zip(pages, endpoints)]
    placements.append((server, where, body, set()))
    moved = _address_map(server, old, placements)

    before_claims = _claims(lines)
    after_claims = _claims(body) + sum((_claims(p.body) for p in pages), Counter())
    declared_added = _claims(links) + _claims([line for p in pages for line in p.added])
    declared_removed = Counter(dropped)
    lost = (before_claims - after_claims) - declared_removed
    gained = (after_claims - before_claims) - declared_added
    if lost or gained:
        sample = [f"-{k}" for k in list(lost)[:3]] + [f"+{k}" for k in list(gained)[:3]]
        raise CarveError(f"the carve would not conserve the page's claims: {sample}")

    texts: dict[Path, str] = {}
    head = f"---\n{doc.raw_frontmatter}---\n" if doc.has_frontmatter else ""
    texts[server] = head + _rewrite("\n".join(body), server, server, server, moved)
    for page in pages:
        fm_page = {"type": "endpoint", "slug": page.name, "title": page.title}
        texts[page.path] = _rewrite(_render(fm_page, page.body), server, page.path, server, moved)
    changes = [FileChange(server, raw, texts[server])]
    changes += [FileChange(p.path, "", texts[p.path]) for p in pages]
    book = [p for p in (f.resolve() for f in _doc_files(graph)) if p != server]
    for path in book:
        old_text = path.read_text(encoding="utf-8")
        if server.name not in old_text:
            continue
        new_text = _rewrite(old_text, path, path, server, moved)
        if new_text != old_text:
            texts[path] = new_text
            changes.append(FileChange(path, old_text, new_text))

    linking = [p for p in book if p.suffix == ".md" and server.name in p.read_text(encoding="utf-8")]
    before = _broken([server, *linking], {}, moved)
    after = _broken([server, *linking, *(p.path for p in pages)], texts, {})
    if fresh := after - before:
        sample = [f"{p.name}#{a}" if a else p.name for p, a in list(fresh)[:5]]
        raise CarveError(f"the carve would break {sum(fresh.values())} link(s), to {sample}")

    rel = server.relative_to(graph.root.resolve()).as_posix()
    summary = [
        f"carve {rel}: {len(pages)} endpoint page(s), "
        f"{sum(1 for u in units if u.kind == 'invocation')} invocation(s) moved with them",
        f"  server: {len(raw.encode())} -> {len(texts[server].encode())} bytes",
        f"  claims: conserved ({sum(before_claims.values())} lines)",
        f"  links: {sum(after.values())} broken after, {sum(before.values())} before",
        f"  other pages relinked: {len(changes) - 1 - len(pages)}",
    ]
    if dropped:
        summary.append(f"  emptied headings dropped: {', '.join(dropped)}")
    return CarvePlan(changes, [], summary=summary)


def _server_path(graph: Graph, server: str) -> Path:
    candidate = Path(server)
    for path in (graph.root / server, graph.doc_roots["features"] / server, candidate):
        if path.is_file():
            return path.resolve()
    raise CarveError(f"no such server page: {server}")


def carve_endpoints(graph: Graph, server: str) -> CarvePlan:
    """Move each endpoint of the *server* page to its own page, rewriting every link the move touches."""
    try:
        return _carve(graph, _server_path(graph, server))
    except CarveError as exc:
        return CarvePlan([], [], error=str(exc))
