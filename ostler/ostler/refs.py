"""The ref grammars this package mints and reads, in one place.

Two of them live here: the ``code:`` bullet's citation grammar, and the **anchor ref** a
doctor finding carries as its address. The first is the reason the module exists and is
described below; the second is :func:`bullet_ref`, whose contract is on the function.

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

from collections.abc import Mapping
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


def bullet_ref(node_id: str, key: str, index: int | None = None) -> str:
    """The address a finding names: a node, the bullet key, and *which* occurrence of it.

    A node states ``does:``, ``verify:`` or ``returns:`` many times, so a ref naming only the
    key addresses every one of them at once. Downstream that is not cosmetic: the okf-builder
    drain keys a worklist row on the ref, so N distinct defects collapse into one row with one
    three-attempt budget, and the repair turn reads whichever sibling it lands on, finds it
    correct, and returns with the finding still standing. One finding, one remedy, one ref —
    the same invariant ``competing-implementations`` states in :mod:`ostler.doctor`.

    ``index`` is **1-based and counts occurrences of that key only**, which is exactly what
    :func:`ostler.registry.normative_claims` returns and what ``qa context`` mints obligation
    ids from. Emitting the same number here is what lets a doctor ref and an obligation id name
    the same claim.

    Pass ``index=None`` only when the finding genuinely is not about one bullet — the key is
    absent, or the defect is that a single-valued key was stated twice. That is a decision to
    write down at the call site, not a default to fall into.

    The separator is ``#`` for the key and ``:`` for the index, so every anchor parser in this
    package — which splits on the first ``#`` only — reads the node id unchanged.
    """
    anchor = f"{node_id}#{key}"
    return anchor if index is None else f"{anchor}:{index}"


def collision_ref(node_id: str, collision: Mapping[str, Any]) -> str:
    """The address of *one collision a node takes part in*, not of the node.

    ``ambiguous-locator`` is the finding with no bullet to index: one component collides once
    per screen it is reached from, once per role, and once per template whose holes match its
    name. Every one of those was emitted at ``ref=node_id``, so a node's several distinct
    ambiguities arrived under one address and the repair turn could not tell which pair it was
    sent to separate — the failure :func:`bullet_ref` describes, reached by a different route.

    The identity of a collision is its ``(screen, role, name)`` group key **and its membership**.
    The key alone is not enough: a templated name matches several static siblings, so one
    ``{directory}`` template produces one record per partner, all under the same key. The
    partners are named by their anchors, the way the finding's own message names them, so the
    ref stays something a reader can act on rather than a digest.

    A third ``#`` segment is safe here: every reader cuts the node id at the first ``#`` past
    the path, and a colliding node is a ``component``, never a file node.
    """
    others = "+".join(sorted(o.rpartition("#")[2] for o in collision["nodes"] if o != node_id))
    parts = [collision["screen"], collision["role"], collision["name"] or "", others]
    return f"{node_id}#" + ":".join(parts)


def ref_path(ref: str) -> str:
    """The file part of a normalized ``path::symbol`` ref (the whole ref when it has none)."""
    try:
        return parse_code_ref(ref).path
    except ValueError:
        return ref.partition("::")[0]


__all__ = [
    "CodeRef",
    "bullet_ref",
    "code_refs",
    "collision_ref",
    "normalize_ref",
    "parse_code_ref",
    "ref_path",
    "render_code_ref",
]
