"""`ostler autofix` — deterministic repair of shape-detectable format drift."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass
from pathlib import Path

from ostler import markdown, registry
from ostler.checks import CheckCall, parse_check, parse_expression, relocatable_to_tests
from ostler.fmt import _target_files
from ostler.model import Graph, _file_main_section, _inline_type

_DRIFTED_KEY = "verify"
_TARGET_KEY = "tests"

_HEADING_TO_TYPE_LOWER = {h.lower(): t for h, t in registry.UI_HEADING_TO_TYPE.items()}


def _unwrap_code_span(value: str) -> str:
    """The value with one inline-code span around the whole of it removed, else unchanged."""
    spans = markdown.leading_code_spans(value)
    stripped = value.strip()
    if len(spans) != 1 or stripped != f"`{spans[0]}`":
        return value
    return value[:len(value) - len(value.lstrip())] + spans[0]


_NULL_EQUALS = re.compile(r"\bequals\s*=\s*(?:None|null)\b")


def _is_null_equals(value: str) -> bool:
    """True when a `verify:` value is provably `json_path(..., equals=None|null)`."""
    try:
        tree = parse_expression(value.strip())
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


def _colon_keywords_as_equals(value: str) -> str:
    """`value` with every `name: …` keyword spelled `name=…` — unchanged when it has none."""
    try:
        tokens = [t for t in tokenize.generate_tokens(io.StringIO(value).readline)
                  if t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER)]
    except (tokenize.TokenError, SyntaxError):
        return value
    spans: list[tuple[int, int]] = []
    depth = 0
    for i, token in enumerate(tokens):
        if token.type == tokenize.OP and token.string in "([{":
            depth += 1
        elif token.type == tokenize.OP and token.string in ")]}":
            depth -= 1
        elif (token.type == tokenize.OP and token.string == ":" and depth == 1 and i >= 2
              and tokens[i - 1].type == tokenize.NAME
              and tokens[i - 2].type == tokenize.OP and tokens[i - 2].string in "(,"):
            if token.start[0] != 1:
                return value
            after = tokens[i + 1].start if i + 1 < len(tokens) else token.end
            spans.append((token.start[1], after[1] if after[0] == 1 else token.end[1]))
    rewritten = value
    for start, end in reversed(spans):
        rewritten = rewritten[:start] + "=" + rewritten[end:]
    return rewritten


def _fix_bullet(bullet: markdown.Bullet, uitype: registry.UINodeType | None,
                body_lines: list[str]) -> tuple[int, int, list[str]] | None:
    """The one-line rewrite for a drifted bullet, or None if every predicate fails."""
    if bullet.label != _DRIFTED_KEY:
        return None
    head = body_lines[bullet.line_start]
    marker, _, rest = head.partition("-")
    _, _, value = rest.partition(":")
    owns_tests = uitype is not None and _TARGET_KEY in uitype.bullet_by_key
    if owns_tests and relocatable_to_tests(bullet.value):
        fixed = f"{marker}- {_TARGET_KEY}:{value}"
        return (bullet.line_start, bullet.line_start + 1, [fixed])
    fixed = _colon_keywords_as_equals(_unwrap_code_span(value))
    if _is_null_equals(fixed):
        fixed = _NULL_EQUALS.sub("absent=true", fixed, count=1)
    if fixed == value or not isinstance(parse_check(fixed.strip()), CheckCall):
        return None
    return (bullet.line_start, bullet.line_start + 1, [f"{marker}- {_DRIFTED_KEY}:{fixed}"])


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
    changed: list[Path]
    written: bool


def run_autofix(graph: Graph, paths: list[str], check: bool = False) -> AutofixResult:
    """Fix every target file."""
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
