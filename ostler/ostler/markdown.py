"""Markdown(+YAML frontmatter) parsing."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from functools import lru_cache

import yaml
from markdown_it import MarkdownIt
from markdown_it.token import Token
from markdown_it import rules_inline
from markdown_it.tree import SyntaxTreeNode
from mdit_py_plugins.front_matter import front_matter_plugin

_FENCE = "---"

_MD = MarkdownIt("commonmark").enable("table").use(front_matter_plugin)


def _remembering_source_pos(rule):
    """Wrap an inline rule so the ``link_open`` it pushes records where in the source it began."""

    def wrapped(state, silent):
        start, mark = state.pos, len(state.tokens)
        ok = rule(state, silent)
        if ok and not silent:
            for tok in state.tokens[mark:]:
                if tok.type == "link_open":
                    tok.meta["srcpos"] = start
                    break
        return ok

    return wrapped


_MD.inline.ruler.at("link", _remembering_source_pos(rules_inline.link))
_MD.inline.ruler.at("autolink", _remembering_source_pos(rules_inline.autolink))


def _normalize(text: str) -> str:
    """Line endings as the parser sees them — token line spans index *these* lines."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _iter_inline(tokens: Iterable[Token]) -> Iterator[tuple[Token, int]]:
    """Yield every ``inline`` token in a flat token stream, with the line its block starts on."""
    for tok in tokens:
        if tok.type == "inline" and tok.map:
            yield tok, tok.map[0]


def iter_links(text: str) -> Iterator[tuple[str, str, int]]:
    """Yield ``(text, href, line)`` for every markdown link **outside code**; ``line`` is 1-based."""
    yield from _links(text)


_CACHED_TEXTS = 1 << 16


@lru_cache(maxsize=_CACHED_TEXTS)
def _links(text: str) -> tuple[tuple[str, str, int], ...]:
    if "[" not in text and "<" not in text:
        return ()
    return tuple(_scan_links(text))


def _scan_links(text: str) -> Iterator[tuple[str, str, int]]:
    for tok, start in _iter_inline(_MD.parse(_normalize(text))):
        depth, line = 0, start
        label: list[str] = []
        href = ""
        for child in tok.children or ():
            if child.type == "link_open":
                if not depth:
                    href, label = str(child.attrGet("href") or ""), []
                    pos = child.meta.get("srcpos")
                    line = start + (tok.content[:pos].count("\n") if pos else 0)
                depth += 1
            elif child.type == "link_close":
                depth -= 1
                if not depth:
                    yield "".join(label), href, line + 1
            elif depth:
                label.append("\n" if child.type in ("softbreak", "hardbreak") else child.content)


@lru_cache(maxsize=_CACHED_TEXTS)
def _inline_children(text: str) -> tuple[Token, ...]:
    """The inline tokens of *text*, shared by every reader: callers only read them."""
    return tuple(_MD.parseInline(_normalize(text))[0].children or ())


_TRAILING_DIGEST = re.compile(r"^(\s*@[0-9a-f]{12})(.*)$", re.DOTALL)


def leading_code_spans(text: str) -> list[str]:
    """The inline-code spans a value *opens* with, comma-separated; ``[]`` if it opens with prose."""
    spans: list[str] = []
    for child in _inline_children(text):
        if child.type == "code_inline":
            spans.append(child.content)
        elif child.type == "text":
            content = child.content
            if spans:
                digest_match = _TRAILING_DIGEST.match(content)
                if digest_match:
                    spans[-1] += digest_match.group(1).strip()
                    content = digest_match.group(2)
            if not content.strip(" \t,"):
                continue
            break
        elif child.type in ("softbreak", "hardbreak"):
            continue
        else:
            break
    return spans


def all_code_spans(text: str) -> list[str]:
    """Every inline-code span in a value, wherever it sits, in order."""
    return [
        child.content
        for child in _inline_children(text)
        if child.type == "code_inline"
    ]


def label_colon_index(text: str) -> int:
    """Index of the first ``:`` outside every inline code span, or ``-1`` if there is none."""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == ":":
            return i
        if ch == "`":
            run_start = i
            while i < n and text[i] == "`":
                i += 1
            run_len = i - run_start
            close = _closing_backtick_run(text, i, run_len)
            i = close + run_len if close is not None else run_start + 1
        else:
            i += 1
    return -1


def _closing_backtick_run(text: str, start: int, run_len: int) -> int | None:
    """Index of the next backtick run of exactly *run_len*, or ``None`` if there is none."""
    i, n = start, len(text)
    while i < n:
        if text[i] == "`":
            j = i
            while j < n and text[j] == "`":
                j += 1
            if j - i == run_len:
                return i
            i = j
        else:
            i += 1
    return None


def prose_text(text: str) -> str:
    """A value's prose: link *text* without its href, code spans measured as nothing."""
    out: list[str] = []
    for child in _inline_children(text):
        if child.type == "code_inline":
            continue
        if child.type in ("softbreak", "hardbreak"):
            out.append("\n")
        elif child.type == "text":
            out.append(child.content)
    return "".join(out).strip()


def code_line_spans(text: str) -> list[tuple[int, int]]:
    """0-indexed ``[start, end)`` line spans of every code block — fenced or indented."""
    return [(tok.map[0], tok.map[1]) for tok in _MD.parse(_normalize(text))
            if tok.type in ("fence", "code_block") and tok.map]


@dataclass
class References:
    links: list[tuple[str, str]] = field(default_factory=list)

    @property
    def doc_hrefs(self) -> list[str]:
        """Link targets that address a document in *this* repo — the citation channel."""
        out: list[str] = []
        for _text, href in self.links:
            h = href.strip()
            if not h or h.startswith("#") or "://" in h or h.startswith("mailto:"):
                continue
            if h not in out:
                out.append(h)
        return out


def extract_refs(text: str) -> References:
    return References(
        links=[(label, href) for label, href, _line in iter_links(text)],
    )


_EMPHASIS = "*_` "


@dataclass
class Bullet:
    text: str
    line_start: int
    line_end: int
    children: list["Bullet"] = field(default_factory=list)

    @property
    def label(self) -> str:
        """Key of a ``- key: value`` bullet, lowercased with emphasis markers stripped ("" if none)."""
        idx = label_colon_index(self.text)
        return self.text[:idx].strip().strip(_EMPHASIS).lower() if idx != -1 else ""

    @property
    def value(self) -> str:
        """Everything after the first ``:`` outside a code span of a ``- key: value`` bullet."""
        idx = label_colon_index(self.text)
        return self.text[idx + 1:].strip() if idx != -1 else ""

    @property
    def bracketed(self) -> tuple[str, str]:
        """``("id", "rest")`` for a ``- [id] rest`` bullet; ``("", text)`` when unbracketed."""
        if not self.text.startswith("["):
            return "", self.text
        ident, sep, rest = self.text[1:].partition("]")
        return (ident.strip(), rest.strip()) if sep else ("", self.text)

    @property
    def refs(self) -> References:
        return extract_refs(self.text)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class Table:
    """A GFM pipe table: header cells, body rows, and its source line span."""

    headers: list[str]
    rows: list[list[str]]
    line_start: int
    line_end: int

    @property
    def records(self) -> list[dict[str, str]]:
        """Rows keyed by header."""
        return [
            {h: (row[i] if i < len(row) else "") for i, h in enumerate(self.headers)}
            for row in self.rows
        ]

    def column(self, header: str) -> list[str]:
        """Every cell under ``header`` (case-insensitive), or ``[]`` if there is no such column."""
        want = header.strip().lower()
        for i, h in enumerate(self.headers):
            if h.strip().lower() == want:
                return [row[i] if i < len(row) else "" for row in self.rows]
        return []


@dataclass
class Section:
    level: int
    title: str
    line_start: int
    line_end: int
    body_lines: list[str] = field(default_factory=list, repr=False)
    children: list["Section"] = field(default_factory=list)
    bullets: list[Bullet] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.body_lines[self.line_start:self.line_end])

    @property
    def body(self) -> str:
        """The section's text **without its own heading line** (the preamble has none)."""
        return "\n".join(self.body_lines[self._content_start:self.line_end])

    @property
    def is_empty(self) -> bool:
        """True when the section carries no prose of its own **or in its sub-sections**."""
        heading_lines = {s.line_start for s in self.walk() if s.level}
        end = min(self.line_end, len(self.body_lines))
        return not any(self.body_lines[i].strip()
                       for i in range(self._content_start, end)
                       if i not in heading_lines)

    @property
    def _content_start(self) -> int:
        """First body-relative line after the heading (level 0 = preamble: no heading)."""
        return self.line_start + (1 if self.level else 0)

    @property
    def refs(self) -> References:
        return extract_refs(self.text)

    def labelled(self, label: str) -> "Bullet | None":
        """The first ``- **Label**: value`` bullet in this section or its sub-sections."""
        want = label.strip().lower()
        for section in self.walk():
            for top in section.bullets:
                for bullet in top.walk():
                    if bullet.label == want:
                        return bullet
        return None

    def find(self, title: str, *, recursive: bool = True) -> "Section | None":
        for s in self.children:
            if s.title.strip() == title.strip():
                return s
            if recursive and (hit := s.find(title, recursive=True)):
                return hit
        return None

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class MarkdownDoc:
    frontmatter: dict | None
    raw_frontmatter: str
    body: str
    _sections: list[Section] | None = field(default=None, repr=False)

    @property
    def has_frontmatter(self) -> bool:
        return self.frontmatter is not None

    @property
    def body_offset(self) -> int:
        """File lines preceding the body (opening fence + frontmatter + closing fence); 0 if none."""
        if not self.has_frontmatter:
            return 0
        return self.raw_frontmatter.count("\n") + 2

    def render(self) -> str:
        if not self.has_frontmatter:
            return self.body
        return f"{_FENCE}\n{self.raw_frontmatter}{_FENCE}\n{self.body}"

    @property
    def sections(self) -> list[Section]:
        """Root-level sections (lazily parsed)."""
        if self._sections is None:
            self._sections = _build_sections(self.body)
        return self._sections

    def walk_sections(self):
        for root in self.sections:
            yield from root.walk()

    def walk_bullets(self) -> list[Bullet]:
        """Every bullet in the body, nested ones included, in **source order**."""
        found = [b for s in self.walk_sections() for top in s.bullets for b in top.walk()]
        return sorted(found, key=lambda b: b.line_start)

    def walk_tables(self) -> list[Table]:
        """Every table in the body, in source order."""
        return sorted((t for s in self.walk_sections() for t in s.tables),
                      key=lambda t: t.line_start)

    def find_section(self, title: str) -> Section | None:
        for root in self.sections:
            if root.title.strip() == title.strip():
                return root
            if hit := root.find(title):
                return hit
        return None

    def section(self, title: str) -> Section:
        """The section titled ``title``."""
        found = self.find_section(title)
        if found is None:
            have = sorted({s.title for s in self.walk_sections() if s.title})
            raise KeyError(f"no section titled {title!r}; document has {have}")
        return found

    def find_bullet(self, label: str) -> Bullet | None:
        """The first ``- **Label**: value`` bullet anywhere in the body."""
        for root in self.sections:
            if hit := root.labelled(label):
                return hit
        return None

    def replace_body(self, lines: list[str]) -> None:
        """Swap in a new body, dropping the cached section parse the new text invalidates."""
        self.body = "\n".join(lines)
        self._sections = None

    @property
    def refs(self) -> References:
        return extract_refs(self.body)


def split(text: str) -> MarkdownDoc:
    """Split Markdown text into frontmatter + body, tolerant of files with neither."""
    text = _normalize(text)
    tokens = _MD.parse(text)
    if not tokens or tokens[0].type != "front_matter":
        return MarkdownDoc(frontmatter=None, raw_frontmatter="", body=text)

    fm = tokens[0]
    if fm.map is None:
        return MarkdownDoc(frontmatter=None, raw_frontmatter="", body=text)

    raw_fm = fm.content + "\n" if fm.content else ""
    body = "\n".join(text.split("\n")[fm.map[1]:])
    try:
        data = yaml.safe_load(raw_fm) or {}
    except yaml.YAMLError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return MarkdownDoc(frontmatter=data, raw_frontmatter=raw_fm, body=body)


def _inline_text(node: SyntaxTreeNode) -> str:
    for child in node.children:
        if child.type == "inline":
            return child.content
    return ""


def _parse_bullets(node: SyntaxTreeNode) -> list[Bullet]:
    """Collect list items (with nesting) from a list node."""
    items: list[Bullet] = []
    for item in node.children:
        if item.type != "list_item":
            continue
        text = ""
        children: list[Bullet] = []
        for child in item.children:
            if child.type == "paragraph" and not text:
                text = _inline_text(child)
            elif child.type in ("bullet_list", "ordered_list"):
                children.extend(_parse_bullets(child))
        span = item.map or [0, 0]
        items.append(Bullet(text=text, line_start=span[0], line_end=span[1], children=children))
    return items


def _parse_tables(tokens) -> list[Table]:
    """Collect every pipe table from a flat token stream."""
    tables: list[Table] = []
    cells: list[str] | None = None
    for i, tok in enumerate(tokens):
        if tok.type == "table_open":
            span = tok.map or [0, 0]
            tables.append(Table(headers=[], rows=[], line_start=span[0], line_end=span[1]))
        elif tok.type == "tr_open":
            cells = []
        elif tok.type in ("th_open", "td_open") and cells is not None:
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            cells.append(nxt.content.strip() if nxt is not None and nxt.type == "inline" else "")
        elif tok.type == "tr_close" and cells is not None and tables:
            if tables[-1].headers:
                tables[-1].rows.append(cells)
            else:
                tables[-1].headers = cells
            cells = None
    return tables


def _top_level_bullets(tree: SyntaxTreeNode) -> list[Bullet]:
    bullets: list[Bullet] = []
    for node in tree.children:
        if node.type in ("bullet_list", "ordered_list"):
            bullets.extend(_parse_bullets(node))
    return bullets


def _build_sections(body: str) -> list[Section]:
    lines = body.split("\n")
    tokens = _MD.parse(body)
    tree = SyntaxTreeNode(tokens)

    headings: list[Section] = []
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open" and tok.map:
            level = int(tok.tag[1])
            title = tokens[i + 1].content if i + 1 < len(tokens) and tokens[i + 1].type == "inline" else ""
            headings.append(Section(level=level, title=title, line_start=tok.map[0],
                                    line_end=len(lines), body_lines=lines))

    for idx, sec in enumerate(headings):
        for nxt in headings[idx + 1:]:
            if nxt.level <= sec.level:
                sec.line_end = nxt.line_start
                break

    roots: list[Section] = []
    stack: list[Section] = []
    for sec in headings:
        while stack and stack[-1].level >= sec.level:
            stack.pop()
        (stack[-1].children if stack else roots).append(sec)
        stack.append(sec)

    first_start = headings[0].line_start if headings else len(lines)
    if first_start > 0:
        preamble = Section(level=0, title="", line_start=0, line_end=first_start, body_lines=lines)
        roots.insert(0, preamble)

    flat = [s for r in roots for s in r.walk()]

    def _container(line_start: int) -> Section | None:
        containing = [s for s in flat if s.line_start <= line_start < s.line_end]
        return max(containing, key=lambda s: s.line_start) if containing else None

    fallback = roots[0] if roots else None

    for bullet in _top_level_bullets(tree):
        container = _container(bullet.line_start) or fallback
        if container is not None:
            container.bullets.append(bullet)

    for table in _parse_tables(tokens):
        container = _container(table.line_start) or fallback
        if container is not None:
            container.tables.append(table)

    return roots
