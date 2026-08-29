"""The ``code:`` bullet's ref grammar, in one place.

A ``code:`` bullet may cite **more than one target**, and books already write it that way::

    - code: `docs-app/react-router.config.ts`, `docs-app/package.json`

Three readers consumed that bullet — ``qa.context``'s ownership map, ``doctor``'s grounding
check, and ``coverage``'s citation join — and all three read it as *one* ref, stripping
decoration only from the ends of the whole string. A two-target bullet therefore normalized
to ``path-a`` + a literal backtick + ``, `` + a backtick + ``path-b``: a ref matching no file,
so the node owned **neither** of the files it cited. Silent, because nothing downstream can
tell "cites nothing" from "cites something unparseable" — the ownership map simply reported
the changed file as unmapped, and the node that documented it went unfound.

``verify:`` never had this problem: it has always been read with ``finditer``, so one bullet
yielding several refs is the behavior that side already had. This module gives ``code:`` the
same treatment, and gives all three readers one implementation of it.

**The refs are the leading comma-separated run of inline-code spans, and prose ends it.**
Backticks alone are not enough to mark a ref, because a trailing gloss uses them too — for
its own identifiers, which are not citations::

    - code: `legacy/.../EntityEditorController.php::tableViews` — the `tableViews` const, `save` handler

Reading every code span as a ref there invents three, two of which resolve to nothing. So a
span counts only while the text separating it from the previous one is whitespace or a comma;
the first separator carrying anything else (an em-dash, a parenthetical, any prose) closes the list.
That also drops a trailing gloss rather than gluing it on, fixing a single-ref case that was
mangled too::

    - code: `web/app/components/navbar/Navbar.tsx::Navbar` (inline JSX, not a named export)

A value not starting with inline code has no such structure, so it is split on commas instead.
That is not worse than what it replaces: a bare single ref has no comma and is unchanged, and
a bare list was already unreadable.

Per this package's standing rule — when the book and the tool disagree about grammar, the
book wins; a tool that cannot parse it is the defect.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ostler.markdown import leading_code_spans


@dataclass(frozen=True, slots=True)
class CodeRef:
    """A code citation, optionally qualified by its repository."""

    repository: str
    path: str
    symbol: str = ""


def parse_code_ref(value: str) -> CodeRef:
    """Parse a legacy or repository-qualified code reference."""
    target, separator, symbol = value.partition("::")
    repository = ""
    path = target
    if target.startswith("repo://"):
        repository, slash, path = target.removeprefix("repo://").partition("/")
        if not slash or not repository or not path:
            msg = f"malformed repository-qualified code ref: {value!r}"
            raise ValueError(msg)
    return CodeRef(
        repository=repository,
        path=path.replace("\\", "/"),
        symbol=symbol if separator else "",
    )


def render_code_ref(ref: CodeRef) -> str:
    """Render a code reference in its canonical legacy or qualified form."""
    path = ref.path.replace("\\", "/")
    if ref.repository:
        if not path:
            msg = "malformed repository-qualified code ref: path must not be empty"
            raise ValueError(msg)
        target = f"repo://{ref.repository}/{path}"
    else:
        target = path
    return f"{target}::{ref.symbol}" if ref.symbol else target


def normalize_ref(value: str) -> str:
    """Strip the decoration a single ``code:`` target may carry (backticks, commas, space)."""
    return value.strip().strip("`, ").strip()


def code_refs(value: Any) -> list[str]:
    """Every target a ``code:`` bullet cites, normalized and de-duplicated in order.

    Accepts what a parsed bullet can be: a list (the key was repeated), a single string, or
    nothing. Returns ``[]`` for an empty or absent bullet — a caller may not distinguish
    "cited nothing" from "could not be read", so this never returns a ref it did not find.
    """
    raw: list[str]
    if isinstance(value, list):
        raw = [str(item) for item in value]
    elif value:
        raw = [str(value)]
    else:
        return []

    out: list[str] = []
    for item in raw:
        # A value that opens with inline code is a run of `path::symbol` spans; one that
        # opens with prose is a bare comma-separated list. The parser decides which, and
        # where each span ends — a backtick regex could not read ``a `b` c``.
        parts = leading_code_spans(item) or item.split(",")
        for part in parts:
            normalized = normalize_ref(part)
            if not normalized:
                continue
            try:
                normalized = render_code_ref(parse_code_ref(normalized))
            except ValueError:
                # Bullet extraction is intentionally tolerant; strict callers use parse_code_ref.
                pass
            out.append(normalized)
    return list(dict.fromkeys(out))


def ref_path(ref: str) -> str:
    """The file part of a normalized ``path::symbol`` ref (the whole ref when it has none)."""
    try:
        return parse_code_ref(ref).path
    except ValueError:
        return ref.partition("::")[0]


__all__ = [
    "CodeRef",
    "code_refs",
    "normalize_ref",
    "parse_code_ref",
    "ref_path",
    "render_code_ref",
]
