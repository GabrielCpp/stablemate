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

KNOWLEDGE_PATH_RE = re.compile(r"docs/knowledge/[^\s)\]'\"`]+\.(?:json|md)")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)  # fenced code blocks
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")        # inline code spans

_MD = MarkdownIt("commonmark")


def _mask_code(text: str) -> str:
    """Blank out fenced blocks and inline-code spans (same length, newlines kept) so a link/ref
    regex never matches *inside code* — e.g. `strategies[idx](x)` in a snippet is not a link. Byte
    offsets and line numbers are preserved for locating the real links that remain."""
    blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))  # noqa: E731
    return _INLINE_CODE_RE.sub(blank, _FENCE_RE.sub(blank, text))


def iter_links(text: str):
    """Yield ``(text, href, line)`` for every markdown link **outside code**; ``line`` is 1-based."""
    masked = _mask_code(text)
    for m in LINK_RE.finditer(masked):
        yield m.group(1), m.group(2), masked.count("\n", 0, m.start()) + 1


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
        links=LINK_RE.findall(_mask_code(text)),  # links inside code are not links
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
