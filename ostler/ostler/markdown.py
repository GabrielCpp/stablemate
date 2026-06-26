"""Markdown(+YAML frontmatter) parsing.

Two layers, deliberately kept separate:

* **Byte-exact layer** — ``split`` returns a :class:`MarkdownDoc` whose ``raw_frontmatter`` and
  ``body`` are the original text. Edits operate here so round-tripping never reflows the file.
* **Hierarchical view** — :attr:`MarkdownDoc.sections` lazily parses the body with a CommonMark
  parser (``markdown-it-py``) into a tree of :class:`Section` (by heading level) and :class:`Bullet`
  (list items, nested). Every node keeps its **source line span** into ``body`` so a semantic node
  can always be mapped back to exact bytes for editing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

_FENCE = "---"

GAP_TAG_RE = re.compile(r"\[gap:\s*([A-Za-z0-9][\w-]*)\s*\]")
KNOWLEDGE_PATH_RE = re.compile(r"docs/knowledge/[^\s)\]'\"`]+\.(?:json|md)")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

_MD = MarkdownIt("commonmark")


@dataclass
class References:
    gap_tags: list[str] = field(default_factory=list)
    knowledge_paths: list[str] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)  # (text, href)


def extract_refs(text: str) -> References:
    return References(
        gap_tags=sorted(set(GAP_TAG_RE.findall(text))),
        knowledge_paths=sorted(set(KNOWLEDGE_PATH_RE.findall(text))),
        links=LINK_RE.findall(text),
    )


@dataclass
class Bullet:
    text: str
    line_start: int          # 0-indexed, body-relative
    line_end: int            # exclusive
    children: list["Bullet"] = field(default_factory=list)

    @property
    def refs(self) -> References:
        return extract_refs(self.text)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class Section:
    level: int               # heading level 1-6; 0 = preamble before the first heading
    title: str
    line_start: int          # 0-indexed, body-relative (the heading line)
    line_end: int            # exclusive
    body_lines: list[str] = field(default_factory=list, repr=False)
    children: list["Section"] = field(default_factory=list)
    bullets: list[Bullet] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.body_lines[self.line_start:self.line_end])

    @property
    def refs(self) -> References:
        return extract_refs(self.text)

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

    def find_section(self, title: str) -> Section | None:
        for root in self.sections:
            if root.title.strip() == title.strip():
                return root
            if hit := root.find(title):
                return hit
        return None

    @property
    def refs(self) -> References:
        return extract_refs(self.body)


def split(text: str) -> MarkdownDoc:
    """Split Markdown text into frontmatter + body, tolerant of files with neither."""
    if not text.startswith(_FENCE + "\n") and text.strip() != _FENCE:
        return MarkdownDoc(frontmatter=None, raw_frontmatter="", body=text)

    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i].strip() == _FENCE:
            raw_fm = "\n".join(lines[1:i])
            raw_fm = raw_fm + "\n" if raw_fm else ""
            body = "\n".join(lines[i + 1:])
            try:
                data = yaml.safe_load(raw_fm) or {}
            except yaml.YAMLError:
                data = {}
            if not isinstance(data, dict):
                data = {}
            return MarkdownDoc(frontmatter=data, raw_frontmatter=raw_fm, body=body)

    return MarkdownDoc(frontmatter=None, raw_frontmatter="", body=text)


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

    # attach top-level bullets to the deepest section that contains them
    flat = [s for r in roots for s in r.walk()]
    for bullet in _top_level_bullets(tree):
        container = max(
            (s for s in flat if s.line_start <= bullet.line_start < s.line_end),
            key=lambda s: s.line_start,
            default=None,
        )
        (container.bullets if container else roots and roots[0].bullets).append(bullet)

    return roots
