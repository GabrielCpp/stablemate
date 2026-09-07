"""`ostler autofix` — deterministic repair of shape-detectable format drift.

`fmt`'s sibling in the `edit.py` family of mutating commands. `fmt` canonicalizes what a
doc already says; this module fixes the narrow class of drift where the *current* content
alone proves what the bullet is under the *current* registry — no format version, no
knowledge of what the book used to be. Each fix is a shape predicate, idempotent and
convergent from any input, so running it on a clean or from-scratch book is a no-op and
running it twice is the same as running it once.

The second fix: a `json_path` check asserting `equals=None` (or JSON's `null`). The
vocabulary's `equals` is a scalar and carries no null — a field that holds nothing is
asserted by its absence, `absent=true` — and the two spellings are exactly what an author
transcribing a Python default or a JSON sample writes. The fix rewrites that one keyword,
and only when the result parses as a check.

The first fix: a `verify:` bullet holding test-id citations. The contract split the
observation (`verify:` — a call in the closed check vocabulary) from the evidence path
(`tests:` — `path::symbol` citations), and drifted books still carry the citations under
the old key. A value that fails check parsing, opens with an inline-code citation run,
and cites only paths with file extensions cannot be a mistyped check — it is the split's
path half under the split's observation key, and the fix renames the key. Anything the
predicate cannot prove stays where it is and remains a doctor finding for judgment.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from ostler import markdown, refs, registry
from ostler.checks import CheckCall, parse_check
from ostler.fmt import _target_files
from ostler.model import Graph, _file_main_section, _inline_type

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


_NULL_EQUALS = re.compile(r"\bequals\s*=\s*(?:None|null)\b")


def _is_null_equals(value: str) -> bool:
    """True when a `verify:` value is provably `json_path(..., equals=None|null)`.

    Proved on the syntax tree, not the text: the call is `json_path`, its `equals` is the
    constant `None` or the bare name `null`, and no other `one_of` argument is present —
    so the rewrite cannot leave a call asserting two things at once.
    """
    try:
        tree = ast.parse(value.strip(), mode="eval")
    except SyntaxError:
        return False
    call = tree.body
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            and call.func.id == "json_path"):
        return False
    keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg}
    equals = keywords.get("equals")
    if equals is None or "absent" in keywords or "matches" in keywords:
        return False
    is_none = isinstance(equals, ast.Constant) and equals.value is None
    is_null = isinstance(equals, ast.Name) and equals.id == "null"
    return is_none or is_null


def _fix_bullet(bullet: markdown.Bullet, uitype: registry.UINodeType | None,
                body_lines: list[str]) -> tuple[int, int, list[str]] | None:
    """The one-line rewrite for a drifted bullet, or None if every predicate fails.

    `uitype` is None for an untyped heading: the key move needs the type to own `tests:`,
    the null rewrite is a property of the call and applies wherever a `verify:` sits.
    """
    if bullet.label != _DRIFTED_KEY:
        return None
    head = body_lines[bullet.line_start]
    marker, _, rest = head.partition("-")
    _, _, value = rest.partition(":")
    owns_tests = uitype is not None and _TARGET_KEY in uitype.bullet_by_key
    if owns_tests and _is_test_citation_run(bullet.value):
        fixed = f"{marker}- {_TARGET_KEY}:{value}"
        return (bullet.line_start, bullet.line_start + 1, [fixed])
    if _is_null_equals(bullet.value):
        rewritten = _NULL_EQUALS.sub("absent=true", value, count=1)
        if isinstance(parse_check(rewritten.strip()), CheckCall):
            return (bullet.line_start, bullet.line_start + 1, [f"{marker}- {_DRIFTED_KEY}:{rewritten}"])
    return None


def fix_text(text: str) -> str:
    """Return the text with every provable drift fixed (idempotent)."""
    doc = markdown.split(text)
    body_lines = doc.body.split("\n")
    edits: list[tuple[int, int, list[str]]] = []

    def visit(section: markdown.Section, uitype: registry.UINodeType | None) -> None:
        for bullet in section.bullets:
            if edit := _fix_bullet(bullet, uitype, body_lines):
                edits.append(edit)

    def promote(section: markdown.Section, container: str | None) -> None:
        # The same walk `model._promote_section` types nodes by: a container heading
        # types its direct children and is no node itself; an inline `type:` prefix wins;
        # otherwise the container's type, else untyped. Nesting composes at any depth, so
        # a `#### field:` under a record is reached the same way a `### method` is.
        # Case-insensitive on purpose: a drifted book may not have seen `fmt` yet, and
        # `## components` holds the same nodes `## Components` does.
        child_container = _HEADING_TO_TYPE_LOWER.get(section.title.strip().lower())
        if child_container is not None:
            for sub in section.children:
                promote(sub, child_container)
            return
        ntype, _ = _inline_type(section.title.strip())
        ntype = ntype or container
        visit(section, registry.ui_type_named(ntype) if ntype else None)
        for sub in section.children:
            promote(sub, None)

    ftype = registry.ui_type(registry.type_of(doc.frontmatter or {}))
    main = _file_main_section(doc)
    if ftype is not None and ftype.kind == "file" and main is not None:
        visit(main, ftype)
    top = main.children if (main is not None and main.level == 1) else doc.sections
    for section in top:
        promote(section, None)

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
