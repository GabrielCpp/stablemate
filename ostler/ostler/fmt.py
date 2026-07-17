"""`ostler fmt` — the canonicalizing formatter for OKF UI-profile docs.

Paired with the linter the way ``ruff format`` pairs with ``ruff check``: it mechanically fixes
*shape* (frontmatter key order, bullet order/spacing, heading casing, ``### id`` anchors, wikilink
rewriting) so ``doctor`` only ever hard-errors on *semantic* gaps. Driven entirely by the per-type
``UINodeType`` spec in ``registry.py`` — the same single source of truth the loader and scaffolder
read, so the three tools never drift.

``markdown.py`` is deliberately byte-exact / no-reflow; this module is the *intentional exception*
— a mutating command in the ``edit.py`` family, never on the read path. It is idempotent and offers
a ``--check`` mode (no writes, exit 1 if unformatted), the same idiom as ``farrier install --check``.
Prose is left untouched (profile §12.2): only frontmatter, bullets, and headings are canonicalized.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from ostler import markdown, registry
from ostler.model import Graph, _file_main_section, anchor_of

# Frontmatter keys emitted first, in this order; the rest follow in their original order.
FRONTMATTER_ORDER = ("type", "slug", "surface", "title", "status", "id", "area", "route")

_KEY_RE = re.compile(r"^([A-Za-z][\w-]*)\s*:(.*)$")
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
# Canonical UI headings, matched case-insensitively so `## components` → `## Components`.
_HEADING_BY_LOWER = {h.lower(): h for h in registry.UI_HEADING_TO_TYPE}


def _canonical_frontmatter(fm: dict) -> str:
    ordered: dict = {}
    for key in FRONTMATTER_ORDER:
        if key in fm:
            ordered[key] = fm[key]
    for key, value in fm.items():
        if key not in ordered:
            ordered[key] = value
    return yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True)


def _bullet_key(text: str) -> str | None:
    """The lowercased key of a ``key: value`` bullet, or None if it isn't that shape."""
    m = _KEY_RE.match(text.strip())
    return m.group(1).lower() if m else None


def _emit_bullet(bullet: markdown.Bullet, uitype: registry.UINodeType,
                 body_lines: list[str]) -> list[str]:
    """Canonical lines for one metadata bullet: normalize its ``- key: value`` first line and keep
    any nested child lines verbatim; expand a one-line ``does:`` into the nested-bullet form."""
    raw = body_lines[bullet.line_start:bullet.line_end]
    key = _bullet_key(bullet.text)
    spec = uitype.bullet_by_key.get(key or "")
    if spec is None:
        return raw  # unrecognized bullet — leave exactly as authored
    value = bullet.text.split(":", 1)[1].strip() if ":" in bullet.text else ""
    if spec.nested and value and not bullet.children:
        return [f"- {key}:", f"  - {value}"]
    first = f"- {key}: {value}" if value else f"- {key}:"
    return [first, *raw[1:]]


def _bullet_run(section: markdown.Section) -> list[markdown.Bullet]:
    """The leading contiguous run of ``key: value`` metadata bullets (stops at the first prose
    bullet), so reordering never disturbs a trailing prose list inside the node."""
    run: list[markdown.Bullet] = []
    for bullet in sorted(section.bullets, key=lambda b: b.line_start):
        if _bullet_key(bullet.text) is None:
            break
        run.append(bullet)
    return run


def _bullet_edit(section: markdown.Section, uitype: registry.UINodeType,
                 body_lines: list[str]) -> tuple[int, int, list[str]] | None:
    """A (start, end, lines) replacement that reorders + normalizes the node's metadata bullets to
    the canonical ``bullet_keys`` order, or None if already canonical."""
    run = _bullet_run(section)
    if not run:
        return None
    order = {b.key: i for i, b in enumerate(uitype.bullet_keys)}

    def rank(bullet: markdown.Bullet) -> tuple[int, int]:
        key = _bullet_key(bullet.text)
        return (0, order[key]) if key in order else (1, 0)

    ordered = sorted(run, key=rank)  # stable: unknown keys keep their relative order, after known
    start, end = run[0].line_start, run[-1].line_end
    new_lines: list[str] = []
    for bullet in ordered:
        block = _emit_bullet(bullet, uitype, body_lines)
        # A bullet's raw span can absorb trailing blank list-separators; drop them so reordering
        # never strands a blank *between* bullets.
        while block and block[-1].strip() == "":
            block.pop()
        new_lines.extend(block)
    # Preserve a single blank line after the run (before the next heading/prose) if there was one.
    if end > start and body_lines[end - 1].strip() == "":
        new_lines.append("")
    if new_lines == body_lines[start:end]:
        return None
    return (start, end, new_lines)


def _apply_edits(body_lines: list[str], edits: list[tuple[int, int, list[str]]]) -> list[str]:
    """Splice line-range replacements in, applied bottom-to-top so earlier spans stay valid."""
    out = list(body_lines)
    for start, end, lines in sorted(edits, key=lambda e: e[0], reverse=True):
        out[start:end] = lines
    return out


def format_text(text: str) -> str:
    """Return the canonical form of a single doc's text (idempotent)."""
    doc = markdown.split(text)
    fm = doc.frontmatter or {}
    body_lines = doc.body.split("\n")
    edits: list[tuple[int, int, list[str]]] = []

    ftype = registry.ui_type(registry.type_of(fm))
    if ftype is not None and ftype.kind == "file":
        main = _file_main_section(doc)
        if main is not None and (edit := _bullet_edit(main, ftype, body_lines)):
            edits.append(edit)

    for section in doc.walk_sections():
        if section.level != 2:
            continue
        canonical = _HEADING_BY_LOWER.get(section.title.strip().lower())
        if canonical is None:
            continue
        if section.title.strip() != canonical:
            edits.append((section.line_start, section.line_start + 1, [f"## {canonical}"]))
        uitype = registry.ui_type(registry.UI_HEADING_TO_TYPE[canonical])
        for sub in section.children:
            kebab = anchor_of(sub.title)
            if kebab and sub.title.strip() != kebab:
                edits.append((sub.line_start, sub.line_start + 1, [f"### {kebab}"]))
            if edit := _bullet_edit(sub, uitype, body_lines):
                edits.append(edit)

    new_body = "\n".join(_apply_edits(body_lines, edits))
    new_body = _WIKILINK_RE.sub(
        lambda m: f"[{(m.group(2) or m.group(1)).strip()}]({m.group(1).strip()})", new_body)

    if doc.has_frontmatter:
        doc.raw_frontmatter = _canonical_frontmatter(fm)
    doc.body = new_body
    return doc.render()


@dataclass
class FmtResult:
    changed: list[Path]        # files whose canonical form differs from disk
    written: bool              # whether the changes were applied


def _target_files(graph: Graph, paths: list[str]) -> list[Path]:
    if paths:
        return [Path(p) if Path(p).is_absolute() else graph.root / p for p in paths]
    froot = graph.doc_roots["features"]
    if not froot.is_dir():
        return []
    return [p for p in sorted(froot.rglob("*.md"))
            if p.is_file() and p.name not in registry.RESERVED_FILES]


def run_fmt(graph: Graph, paths: list[str], check: bool = False) -> FmtResult:
    """Format every target file. ``check=True`` never writes; it just reports what would change."""
    changed: list[Path] = []
    for path in _target_files(graph, paths):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        formatted = format_text(text)
        if formatted != text:
            changed.append(path)
            if not check:
                path.write_text(formatted, encoding="utf-8")
    return FmtResult(changed=changed, written=not check and bool(changed))
