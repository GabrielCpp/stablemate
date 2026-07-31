"""Markdown(+YAML frontmatter) parsing.

Everything here goes through the **parser** — ``markdown-it-py`` for the document,
``front_matter_plugin`` for the frontmatter fence, ``yaml`` for its payload. No regex
matches a markdown or YAML construct: see the ``stablemate-structured-parsing`` skill for
why (in short, a regex that "finds" a link also finds one inside a code fence, and a
regex that fences off frontmatter silently finds *none* in a CRLF file).

Two layers, deliberately kept separate:

* **Byte-exact layer** — ``split`` returns a :class:`MarkdownDoc` whose ``raw_frontmatter`` and
  ``body`` are the original text. Edits operate here so round-tripping never reflows the file.
  The one normalization is line endings: CRLF/CR become LF, matching what the parser sees, so
  a Windows-authored doc has frontmatter at all (the regex this replaced saw none).
* **Hierarchical view** — :attr:`MarkdownDoc.sections` lazily parses the body into a tree of
  :class:`Section` (by heading level), :class:`Bullet` (list items, nested) and :class:`Table`.
  Every node keeps its **source line span** into ``body`` so a semantic node can always be
  mapped back to exact bytes for editing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml
from markdown_it import MarkdownIt
from markdown_it import rules_inline
from markdown_it.tree import SyntaxTreeNode
from mdit_py_plugins.front_matter import front_matter_plugin

_FENCE = "---"

#: A repo-relative path mentioned in prose. Not a markdown construct — no grammar to parse,
#: so this one stays a regex (declared in scripts/check_parsers.py).
KNOWLEDGE_PATH_RE = re.compile(r"docs/knowledge/[^\s)\]'\"`]+\.(?:json|md)")

#: `table` is off in the bare commonmark preset, so a table used to arrive as an
#: undifferentiated paragraph; the library's docs are full of them. `front_matter_plugin`
#: makes a leading `---` fence a token of its own rather than a setext-h2 underline.
_MD = MarkdownIt("commonmark").enable("table").use(front_matter_plugin)


def _remembering_source_pos(rule):
    """Wrap an inline rule so the ``link_open`` it pushes records where in the source it began.

    Inline tokens carry no line map — only the containing block does — and the obvious
    workaround, walking a cursor forward over the children and counting newlines, cannot work:
    CommonMark converts a line ending *inside a code span* to a space, so a wrapped
    `` `a REFERENCES b(id) ON\\nDELETE CASCADE` `` arrives as one ``code_inline`` token whose
    content holds no newline at all. Every link after it in the paragraph then reads one line
    early — 332 of them across one real book. The parser knows the offset; this asks it.
    """

    def wrapped(state, silent):
        start, mark = state.pos, len(state.tokens)
        ok = rule(state, silent)
        if ok and not silent:
            # Not ``tokens[mark]``: text accrues in ``state.pending`` and is flushed as its own
            # token just before ``link_open``, so the link is the first *link_open* from here.
            for tok in state.tokens[mark:]:
                if tok.type == "link_open":
                    tok.meta["srcpos"] = start
                    break
        return ok

    return wrapped


# `link` covers both `[text](href)` and the reference forms; `autolink` covers `<https://…>`.
_MD.inline.ruler.at("link", _remembering_source_pos(rules_inline.link))
_MD.inline.ruler.at("autolink", _remembering_source_pos(rules_inline.autolink))


def _normalize(text: str) -> str:
    """Line endings as the parser sees them — token line spans index *these* lines."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _iter_inline(tokens):
    """Yield every ``inline`` token in a flat token stream, with its block line span."""
    for tok in tokens:
        if tok.type == "inline" and tok.map:
            yield tok


def iter_links(text: str):
    """Yield ``(text, href, line)`` for every markdown link **outside code**; ``line`` is 1-based.

    A link inside a fenced block or an inline-code span is not a ``link_open`` token, so the
    exclusion is structural rather than the blank-out-the-code-first approximation it replaces
    (which could not tell ``strategies[idx](x)`` in a snippet from a link).
    """
    for tok in _iter_inline(_MD.parse(_normalize(text))):
        depth, line = 0, tok.map[0]
        label: list[str] = []
        href = ""
        for child in tok.children or ():
            if child.type == "link_open":
                if not depth:
                    href, label = child.attrGet("href") or "", []
                    # `srcpos` indexes the block's own source, which is what the inline rules
                    # were handed, so the newlines before it are the lines before it.
                    pos = child.meta.get("srcpos")
                    line = tok.map[0] + (tok.content[:pos].count("\n") if pos else 0)
                depth += 1
            elif child.type == "link_close":
                depth -= 1
                if not depth:
                    yield "".join(label), href, line + 1
            elif depth:
                # A break inside a link's own text is part of that text: `[Document\nparser]`
                # reads "Document parser", not "Documentparser".
                label.append("\n" if child.type in ("softbreak", "hardbreak") else child.content)


def leading_code_spans(text: str) -> list[str]:
    """The inline-code spans a value *opens* with, comma-separated; ``[]`` if it opens with prose.

    ``code:`` bullets cite targets as `` `path::symbol` `` runs. Reading them off
    ``code_inline`` tokens rather than a backtick regex is what makes ``` ``a `b` c`` ``` and
    a backslash-escaped fence come out right, and it is the parser that decides where a span
    ends rather than the next backtick character.
    """
    spans: list[str] = []
    for child in _MD.parseInline(_normalize(text))[0].children or ():
        if child.type == "code_inline":
            spans.append(child.content)
        elif child.type == "text" and not child.content.strip(" \t,"):
            continue  # the separator between two spans
        elif child.type in ("softbreak", "hardbreak"):
            # A wrapped bullet. The newline between two spans is whitespace like any other,
            # but the parser hands it back as its own token rather than as text — so reading
            # only `text` for the separator closed the run at the line break and silently
            # dropped every target after the first, which is how a long `code:` bullet lost
            # its second citation and a real ungrounded symbol stopped being reported.
            continue
        else:
            break     # prose — the run is over (and never started, if spans is empty)
    return spans


def code_line_spans(text: str) -> list[tuple[int, int]]:
    """0-indexed ``[start, end)`` line spans of every code block — fenced or indented.

    For the mutating commands, which rewrite *prose* and must leave a snippet alone: a
    wikilink or a status line inside a fence is sample text, not the document's own.
    """
    return [tok.map for tok in _MD.parse(_normalize(text))
            if tok.type in ("fence", "code_block") and tok.map]


@dataclass
class References:
    knowledge_paths: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)  # (text, href)

    @property
    def doc_hrefs(self) -> list[str]:
        """Link targets that address a document in *this* repo — the citation channel.

        A story cites an OKF node by linking its id, and a UI node's id **is** a
        repo-relative path (optionally ``path#anchor``), so every such citation arrives here
        as an ordinary markdown link. External URLs and bare in-page anchors are not
        citations of a document and are dropped; everything else is left verbatim for the
        caller to resolve against the citing file (see ``Graph.resolve_doc_ref``).
        """
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
        knowledge_paths=sorted(set(KNOWLEDGE_PATH_RE.findall(text))),
        links=[(label, href) for label, href, _line in iter_links(text)],
    )


_EMPHASIS = "*_` "  # inline formatting around a bullet's key — decoration, not part of the key


@dataclass
class Bullet:
    text: str
    line_start: int          # 0-indexed, body-relative
    line_end: int            # exclusive
    children: list["Bullet"] = field(default_factory=list)

    @property
    def label(self) -> str:
        """Key of a ``- key: value`` bullet, lowercased with emphasis markers stripped ("" if none).

        ``- **Status**: Done`` and ``- status: Done`` are the same field wearing different
        formatting. The parser is the right place to know that, so a caller can ask for a
        labelled bullet instead of pattern-matching the rendered line.
        """
        key, sep, _ = self.text.partition(":")
        return key.strip().strip(_EMPHASIS).lower() if sep else ""

    @property
    def value(self) -> str:
        """Everything after the first ``:`` of a ``- key: value`` bullet."""
        return self.text.partition(":")[2].strip()

    @property
    def bracketed(self) -> tuple[str, str]:
        """``("id", "rest")`` for a ``- [id] rest`` bullet; ``("", text)`` when unbracketed.

        The backlog and the epics queue are both lists of these. Reading the id off a
        *parsed* bullet is what keeps a ``- [x] …`` line inside a fenced example, or an
        indented continuation line that merely looks like one, out of the queue.
        """
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
    """A GFM pipe table: header cells, body rows, and its source line span.

    Tables are how the library's docs carry most of their tabular contract (placeholder
    tables, parser-per-format tables, matrices). Before ``table`` was enabled the parser
    handed every one of them back as an undifferentiated paragraph, so a caller wanting a
    row had no option but to split on ``|`` itself.
    """

    headers: list[str]
    rows: list[list[str]]
    line_start: int          # 0-indexed, body-relative
    line_end: int            # exclusive

    @property
    def records(self) -> list[dict[str, str]]:
        """Rows keyed by header. Short rows pad, long rows truncate — as the renderer does."""
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
    level: int               # heading level 1-6; 0 = preamble before the first heading
    title: str
    line_start: int          # 0-indexed, body-relative (the heading line)
    line_end: int            # exclusive
    body_lines: list[str] = field(default_factory=list, repr=False)
    children: list["Section"] = field(default_factory=list)
    bullets: list[Bullet] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.body_lines[self.line_start:self.line_end])

    @property
    def body(self) -> str:
        """The section's text **without its own heading line** (the preamble has none).

        ``text`` includes the heading, which makes "does this section say anything?"
        unanswerable without re-splitting the string — the gap that had every caller
        writing its own scan.
        """
        return "\n".join(self.body_lines[self._content_start:self.line_end])

    @property
    def is_empty(self) -> bool:
        """True when the section carries no prose of its own **or in its sub-sections**.

        Sub-section heading lines are not content: a ``## Context`` whose only body is an
        empty ``### Background`` is still unwritten, and a scaffold that is nothing but
        headings must not read as filled.
        """
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
        """File lines preceding the body (opening fence + frontmatter + closing fence); 0 if none.

        Add it to a body-relative (0-indexed) line to get the file-absolute (0-indexed) line —
        used to give a section/bullet node an absolute source location for located findings.
        """
        if not self.has_frontmatter:
            return 0
        return self.raw_frontmatter.count("\n") + 2

    def render(self) -> str:
        if not self.has_frontmatter:
            return self.body
        return f"{_FENCE}\n{self.raw_frontmatter}{_FENCE}\n{self.body}"

    @property
    def sections(self) -> list[Section]:
        """Root-level sections (lazily parsed). A leading preamble, if any, is the first root."""
        if self._sections is None:
            self._sections = _build_sections(self.body)
        return self._sections

    def walk_sections(self):
        for root in self.sections:
            yield from root.walk()

    def walk_bullets(self) -> list[Bullet]:
        """Every bullet in the body, nested ones included, in **source order**.

        Sections nest by heading level, so walking them yields tree order rather than file
        order; a list that *is* an ordering (the backlog, the epics queue) needs the latter.
        """
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
    """Split Markdown text into frontmatter + body, tolerant of files with neither.

    The fence is located by ``front_matter_plugin``, not by scanning for a ``---`` line.
    That difference is not cosmetic: the line scan returned *no frontmatter at all* for a
    CRLF file, for a file whose closing fence carried a trailing space, and for one with no
    newline after the closing fence — three silent total losses. It also read an **indented**
    ``---`` as the terminator, splitting a document in the wrong place.
    """
    text = _normalize(text)
    tokens = _MD.parse(text)
    if not tokens or tokens[0].type != "front_matter":
        # A bare `---` with nothing to close it is a horizontal rule, and the parser says so.
        return MarkdownDoc(frontmatter=None, raw_frontmatter="", body=text)

    fm = tokens[0]
    raw_fm = fm.content + "\n" if fm.content else ""
    body = "\n".join(text.split("\n")[fm.map[1]:])
    try:
        # `raw_fm`, not `fm.content`: the token drops the block's final newline, and a
        # folded scalar's trailing-newline semantics depend on it.
        data = yaml.safe_load(raw_fm) or {}
    except yaml.YAMLError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return MarkdownDoc(frontmatter=data, raw_frontmatter=raw_fm, body=body)


# ---------------------------------------------------------------------------
# Hierarchical parse
# ---------------------------------------------------------------------------
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
    """Collect every pipe table from a flat token stream.

    Cell tokens carry no line map of their own, so the row's ``tr_open`` supplies the span
    and the cell's ``inline`` child supplies the text — already unescaped and with the
    trailing/leading padding the renderer strips.
    """
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
            # The first row of a table is its header; every later one is data.
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
        if tok.type == "heading_open":
            level = int(tok.tag[1])
            title = tokens[i + 1].content if i + 1 < len(tokens) and tokens[i + 1].type == "inline" else ""
            headings.append(Section(level=level, title=title, line_start=tok.map[0],
                                    line_end=len(lines), body_lines=lines))

    # close each heading's span at the next heading of equal-or-higher rank
    for idx, sec in enumerate(headings):
        for nxt in headings[idx + 1:]:
            if nxt.level <= sec.level:
                sec.line_end = nxt.line_start
                break

    # nest headings by level
    roots: list[Section] = []
    stack: list[Section] = []
    for sec in headings:
        while stack and stack[-1].level >= sec.level:
            stack.pop()
        (stack[-1].children if stack else roots).append(sec)
        stack.append(sec)

    # preamble: content before the first heading
    first_start = headings[0].line_start if headings else len(lines)
    if first_start > 0:
        preamble = Section(level=0, title="", line_start=0, line_end=first_start, body_lines=lines)
        roots.insert(0, preamble)

    # attach top-level bullets and tables to the deepest section that contains them
    flat = [s for r in roots for s in r.walk()]

    def _container(line_start: int) -> Section | None:
        return max(
            (s for s in flat if s.line_start <= line_start < s.line_end),
            key=lambda s: s.line_start,
            default=None,
        )

    for bullet in _top_level_bullets(tree):
        container = _container(bullet.line_start)
        (container.bullets if container else roots and roots[0].bullets).append(bullet)

    for table in _parse_tables(tokens):
        container = _container(table.line_start)
        (container.tables if container else roots and roots[0].tables).append(table)

    return roots
