"""`ostler autofix` — deterministic repair of shape-detectable format drift.

`fmt`'s sibling in the `edit.py` family of mutating commands. `fmt` canonicalizes what a
doc already says; this module fixes the narrow class of drift where the *current* content
alone proves what the bullet is under the *current* registry — no format version, no
knowledge of what the book used to be. Each fix is a shape predicate, idempotent and
convergent from any input, so running it on a clean or from-scratch book is a no-op and
running it twice is the same as running it once.

The one fix so far: a `verify:` bullet holding test-id citations. The contract split the
observation (`verify:` — a call in the closed check vocabulary) from the evidence path
(`tests:` — `path::symbol` citations), and drifted books still carry the citations under
the old key. A value that fails check parsing, opens with an inline-code citation run,
and cites only paths with file extensions cannot be a mistyped check — it is the split's
path half under the split's observation key, and the fix renames the key. Anything the
predicate cannot prove stays where it is and remains a doctor finding for judgment.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ostler import markdown, refs, registry
from ostler.checks import CheckCall, parse_check
from ostler.fmt import _target_files
from ostler.model import Graph, _file_main_section

#: The key whose drifted values this module recognizes, and the key they belong under.
_DRIFTED_KEY = "verify"
_TARGET_KEY = "tests"

_HEADING_TO_TYPE_LOWER = {h.lower(): t for h, t in registry.UI_HEADING_TO_TYPE.items()}


def _is_test_citation_run(value: str) -> bool:
    """True when a `verify:` value is provably the `tests:` citation form.

    Every clause narrows, none guesses: a parsing check is a check (left alone); a value
    opening with prose is a sentence for a human to judge; a citation without a file
    extension could be a module path or a stray identifier rather than a test file.
    """
    if isinstance(parse_check(value), CheckCall):
        return False
    spans = markdown.leading_code_spans(value)
    if not spans:
        return False
    cited = [ref for span in spans if (ref := refs.normalize_ref(span))]
    return bool(cited) and all(Path(refs.ref_path(ref)).suffix for ref in cited)


def _fix_bullet(bullet: markdown.Bullet, uitype: registry.UINodeType,
                body_lines: list[str]) -> tuple[int, int, list[str]] | None:
    """The one-line key rewrite for a drifted bullet, or None if the predicate fails."""
    if bullet.label != _DRIFTED_KEY or _TARGET_KEY not in uitype.bullet_by_key:
        return None
    if not _is_test_citation_run(bullet.value):
        return None
    head = body_lines[bullet.line_start]
    marker, _, rest = head.partition("-")
    _, _, value = rest.partition(":")
    fixed = f"{marker}- {_TARGET_KEY}:{value}"
    return (bullet.line_start, bullet.line_start + 1, [fixed])


def fix_text(text: str) -> str:
    """Return the text with every provable drift fixed (idempotent)."""
    doc = markdown.split(text)
    body_lines = doc.body.split("\n")
    edits: list[tuple[int, int, list[str]]] = []

    def visit(section: markdown.Section, uitype: registry.UINodeType) -> None:
        for bullet in section.bullets:
            if edit := _fix_bullet(bullet, uitype, body_lines):
                edits.append(edit)

    ftype = registry.ui_type(registry.type_of(doc.frontmatter or {}))
    if ftype is not None and ftype.kind == "file":
        main = _file_main_section(doc)
        if main is not None:
            visit(main, ftype)

    for section in doc.walk_sections():
        if section.level != 2:
            continue
        # Case-insensitive on purpose: a drifted book may not have seen `fmt` yet, and
        # `## components` holds the same nodes `## Components` does.
        type_name = _HEADING_TO_TYPE_LOWER.get(section.title.strip().lower())
        if type_name is None:
            continue
        uitype = registry.ui_type_named(type_name)
        for sub in section.children:
            visit(sub, uitype)

    if not edits:
        return text
    out = list(body_lines)
    for start, end, lines in sorted(edits, key=lambda e: e[0], reverse=True):
        out[start:end] = lines
    doc.body = "\n".join(out)
    return doc.render()


@dataclass
class AutofixResult:
    changed: list[Path]        # files whose fixed form differs from disk
    written: bool              # whether the changes were applied


def run_autofix(graph: Graph, paths: list[str], check: bool = False) -> AutofixResult:
    """Fix every target file. ``check=True`` never writes; it just reports what would change."""
    changed: list[Path] = []
    for path in _target_files(graph, paths):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fixed = fix_text(text)
        if fixed != text:
            changed.append(path)
            if not check:
                path.write_text(fixed, encoding="utf-8")
    return AutofixResult(changed=changed, written=not check and bool(changed))
