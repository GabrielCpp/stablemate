"""`ostler edit carve-fragments`: a page past the size limit, its largest sections' subsections moved onto fragment pages beside it."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ostler import markdown, registry
from ostler.carve import CarveError, CarvePlan, _address_map, _broken, _claims, _render, _rewrite, _trim, references
from ostler.edit import FileChange, _doc_files
from ostler.links import is_doc_link
from ostler.model import Graph, document_anchors
from ostler.page_size import PAGE_SIZE_LIMIT


@dataclass
class _Fragment:
    name: str
    title: str
    path: Path
    body: list[str]
    origin: dict[int, int]
    added: list[str]


def _bytes(lines: list[str], start: int, end: int) -> int:
    return sum(len(line.encode()) + 1 for line in lines[start:end])


def _units(section: markdown.Section, anchors: dict[int, str]) -> list[tuple[int, int]]:
    """The section's subsections, joined into contiguous runs wherever one points at another by `#anchor`."""
    kids = section.children
    owner = {line: i for i, kid in enumerate(kids)
             for line, _a in anchors.items() if kid.line_start <= line < kid.line_end}
    by_anchor = {a: owner[line] for line, a in anchors.items() if line in owner}
    reach = list(range(len(kids)))
    for i, kid in enumerate(kids):
        for href in references(kid.text):
            path_part, _, anchor = href.strip().partition("#")
            j = by_anchor.get(anchor) if is_doc_link(href) and not path_part else None
            if j is not None:
                lo, hi = min(i, j), max(i, j)
                reach[lo] = max(reach[lo], hi)
    runs: list[tuple[int, int]] = []
    i = 0
    while i < len(kids):
        end = reach[i]
        j = i
        while j < end:
            j += 1
            end = max(end, reach[j])
        runs.append((kids[i].line_start, kids[end].line_end))
        i = end + 1
    return runs


def _apart(units: list[tuple[int, int]], section: markdown.Section, lines: list[str],
           budget: int) -> list[tuple[int, int]]:
    """The units, with each one too large for a fragment split back into its own subsections."""
    spans: list[tuple[int, int]] = []
    for start, end in units:
        if _bytes(lines, start, end) <= budget:
            spans.append((start, end))
        else:
            spans += [(k.line_start, k.line_end) for k in section.children if start <= k.line_start < end]
    return spans


def _pack(units: list[tuple[int, int]], lines: list[str], budget: int, title: str) -> list[list[tuple[int, int]]]:
    groups: list[list[tuple[int, int]]] = []
    size = 0
    for start, end in units:
        unit = _bytes(lines, start, end)
        if unit > budget:
            raise CarveError(f"a subsection of `{title}` holds {unit // 1024} KiB on its own, past what "
                             f"one fragment page can hold; split it by hand")
        if not groups or size + unit > budget:
            groups.append([])
            size = 0
        groups[-1].append((start, end))
        size += unit
    return groups


def _build(lines: list[str], spans: list[tuple[int, int]], name: str, title: str, heading: str,
           host: Path, host_title: str) -> _Fragment:
    body: list[str] = []
    origin: dict[int, int] = {}
    host_bullet = f"- host: [{host_title}]({host.name})"
    body += [f"# {title}", "", host_bullet, "", heading, ""]
    for start, end in spans:
        for old, text in _trim([(i, lines[i]) for i in range(start, end)]):
            origin[old] = len(body)
            body.append(text)
        body.append("")
    return _Fragment(name, title, host.parent / f"{name}.md", body, origin, [f"# {title}", host_bullet, heading])


def _slim(lines: list[str], moved: dict[int, list[str]], removed: set[int]) -> tuple[list[str], dict[int, int]]:
    body: list[str] = []
    where: dict[int, int] = {}
    skip_blank = False
    for i, text in enumerate(lines):
        if i in moved:
            if body and body[-1].strip():
                body.append("")
            body.extend(moved[i])
            body.append("")
            skip_blank = True
        if i in removed:
            continue
        if skip_blank and not text.strip():
            continue
        skip_blank = False
        where[i] = len(body)
        body.append(text)
    while body and not body[-1].strip():
        body.pop()
    body.append("")
    return body, where


def _chosen(top: list[markdown.Section], lines: list[str], size: int) -> list[markdown.Section]:
    chosen: list[markdown.Section] = []
    held = sorted((s for s in top if s.children), key=lambda s: -_bytes(lines, s.children[0].line_start, s.line_end))
    for section in held:
        if size <= PAGE_SIZE_LIMIT:
            break
        chosen.append(section)
        size -= _bytes(lines, section.children[0].line_start, section.line_end)
    return sorted(chosen, key=lambda s: s.line_start)


def _carve(graph: Graph, host: Path) -> CarvePlan:
    raw = host.read_text(encoding="utf-8")
    rel = host.relative_to(graph.root.resolve()).as_posix()
    if len(raw.encode()) <= PAGE_SIZE_LIMIT:
        return CarvePlan([], [], summary=[f"{rel}: {len(raw.encode())} bytes, within the limit"])
    doc = markdown.split(raw)
    fm = doc.frontmatter or {}
    if registry.type_of(fm) == "fragment":
        raise CarveError(f"{host.name} is a fragment already; move part of it back onto its host's other fragments by hand")
    lines = doc.body.split("\n")
    h1 = next((s for s in doc.sections if s.level == 1), None)
    host_title = str(fm.get("title") or (h1.title.strip() if h1 else host.stem))
    top = h1.children if h1 is not None else doc.sections
    chosen = _chosen(top, lines, len(raw.encode()))
    if not chosen:
        raise CarveError(f"{host.name} has no section with subsections to move onto a fragment page")

    old = document_anchors(doc)
    fragments: list[_Fragment] = []
    links: dict[int, list[str]] = {}
    removed: set[int] = set()
    for section in chosen:
        heading = f"{'#' * section.level} {section.title.strip()}"
        title = f"{host_title}: {section.title.strip()}"
        overhead = len(f"---\ntype: fragment\nslug: {host.stem}\ntitle: {title}\n---\n# {title}\n\n"
                       f"- host: [{host_title}]({host.name})\n\n{heading}\n\n".encode()) + 256
        budget = PAGE_SIZE_LIMIT - overhead
        groups = _pack(_apart(_units(section, old), section, lines, budget), lines, budget, section.title.strip())
        stem = f"{host.stem}-{old[section.line_start]}"
        names = [stem] if len(groups) == 1 else [f"{stem}-{old[g[0][0]]}" for g in groups]
        built = [_build(lines, g, n, title, heading, host, host_title) for g, n in zip(groups, names)]
        fragments += built
        links[section.children[0].line_start] = [f"- [{f.name}]({f.name}.md)" for f in built]
        removed.update(range(section.children[0].line_start, section.line_end))
    if taken := sorted(f.name for f in fragments if f.path.exists()):
        raise CarveError(f"a page already exists for: {', '.join(taken)}")
    body, where = _slim(lines, links, removed)

    none: set[int] = set()
    placements = [(f.path, f.origin, f.body, none) for f in fragments]
    placements.append((host, where, body, none))
    moved = _address_map(host, old, placements)

    before_claims = _claims(lines)
    after_claims = _claims(body) + sum((_claims(f.body) for f in fragments), Counter())
    declared = _claims([line for group in links.values() for line in group])
    declared += _claims([line for f in fragments for line in f.added])
    lost = before_claims - after_claims
    gained = (after_claims - before_claims) - declared
    if lost or gained:
        sample = [f"-{k}" for k in list(lost)[:3]] + [f"+{k}" for k in list(gained)[:3]]
        raise CarveError(f"the carve would not conserve the page's claims: {sample}")

    texts: dict[Path, str] = {}
    head = f"---\n{doc.raw_frontmatter}---\n" if doc.has_frontmatter else ""
    texts[host] = head + _rewrite("\n".join(body), host, host, host, moved)
    for frag in fragments:
        fm_frag = {"type": "fragment", "slug": frag.name, "title": frag.title}
        texts[frag.path] = _rewrite(_render(fm_frag, frag.body), host, frag.path, host, moved)
    if (left := len(texts[host].encode())) > PAGE_SIZE_LIMIT:
        raise CarveError(f"{host.name} would still hold {left // 1024} KiB with every section's subsections "
                         f"moved, past the {PAGE_SIZE_LIMIT // 1024} KiB limit; shorten its intros by hand")
    changes = [FileChange(host, raw, texts[host])]
    changes += [FileChange(f.path, "", texts[f.path]) for f in fragments]
    book = [p for p in (f.resolve() for f in _doc_files(graph)) if p != host]
    for path in book:
        old_text = path.read_text(encoding="utf-8")
        if host.name not in old_text:
            continue
        new_text = _rewrite(old_text, path, path, host, moved)
        if new_text != old_text:
            texts[path] = new_text
            changes.append(FileChange(path, old_text, new_text))

    linking = [p for p in book if p.suffix == ".md" and host.name in p.read_text(encoding="utf-8")]
    before = _broken([host, *linking], {}, moved)
    after = _broken([host, *linking, *(f.path for f in fragments)], texts, {})
    if fresh := after - before:
        sample = [f"{p.name}#{a}" if a else p.name for p, a in list(fresh)[:5]]
        raise CarveError(f"the carve would break {sum(fresh.values())} link(s), to {sample}")

    summary = [
        f"carve {rel}: {len(fragments)} fragment page(s) from {len(chosen)} section(s)",
        f"  host: {len(raw.encode())} -> {len(texts[host].encode())} bytes",
        f"  claims: conserved ({sum(before_claims.values())} lines)",
        f"  links: {sum(after.values())} broken after, {sum(before.values())} before",
        f"  other pages relinked: {len(changes) - 1 - len(fragments)}",
    ]
    return CarvePlan(changes, [], summary=summary)


def _page_path(graph: Graph, page: str) -> Path:
    candidate = Path(page)
    for path in (graph.root / page, graph.doc_roots["features"] / page, candidate):
        if path.is_file():
            return path.resolve()
    raise CarveError(f"no such page: {page}")


def carve_fragments(graph: Graph, page: str) -> CarvePlan:
    """Move the subsections of the *page*'s largest sections onto fragment pages until it fits the size limit."""
    try:
        return _carve(graph, _page_path(graph, page))
    except CarveError as exc:
        return CarvePlan([], [], error=str(exc))
