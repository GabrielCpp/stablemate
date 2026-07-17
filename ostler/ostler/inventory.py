"""The source symbol front end — one grammar for the join and the grounding check.

Two callers need to know what a file declares, and they must agree:

* **the coverage join** (``ostler coverage``) inventories a tree's units, which the book's
  ``code:`` citations are diffed against;
* **``doctor``'s ``code:`` grounding**, which asserts a citation names a file that exists and a
  symbol that file declares.

They used to answer that question in two places — real declaration regexes in the builder's
`inventory-source.py`, and a *word-presence* test in `doctor`. The two disagreed, and the
disagreement was invisible in the direction that mattered: a facade module that re-exports a
name (``from .renderer import Renderer``) still contains the word, so grounding passed on a
citation whose definition had moved away. A book could cite a symbol its file no longer
declared and `doctor` stayed green — the exact drift §4.4 exists to catch. One grammar, defined
once, is the fix.

**Regexes are adequate here** for the same reason they are in the inventory: what is needed is
*the set of declared names*, not a parse tree. Real symbol resolution (tree-sitter/LSP) would be
more accurate and costs a large dependency the coverage diff does not need.

**Two questions, two answers, deliberately.** ``symbols()`` reports the *documented surface* —
it applies each language's export/visibility filter, because an unexported helper is not a unit
a book owes coverage for. ``declared_names()`` reports *everything the file declares*, filter
and all removed, because grounding a citation is a different question: a book may legitimately
document a private symbol (``main.py::_run_run`` **is** the subcommand handler), and flagging it
would punish the book for the inventory's narrower scope. A unit's shape is language-shaped;
so is its visibility, and only the first question cares.
"""
from __future__ import annotations

import re
from pathlib import Path

# The languages the front end can read. A source tree containing NONE of these is an error, not
# an empty inventory — an unsupported language must never be indistinguishable from a fully
# documented one.
SOURCE_SUFFIXES = {".go", ".py", ".ts", ".tsx", ".php", ".twig"}

# The inventory's Python surface: module-level `class`/`def` only, anchored at column 0. The
# anchor is what keeps a method out of the denominator — widening it would change what
# "complete" means and make every existing book instantly less complete.
PY_DECL = re.compile(r"^(?:async\s+)?(?:class|def)\s+([A-Za-z][A-Za-z0-9_]*)", re.MULTILINE)
# Grounding's Python declarations — a strictly wider set, and deliberately so. A book's notion
# of a unit is wider than the inventory's: for an application (rather than a library) a private
# `_run_run` *is* the subcommand handler, a method is a real behavioral unit, and a module
# constant (`LOG`, `REGISTRY`) is a real thing to document. The inventory may narrow its
# denominator; grounding may not punish a book for citing outside it.
PY_ANY_DECL = re.compile(r"^\s*(?:async\s+)?(?:class|def)\s+([A-Za-z_][A-Za-z0-9_]*)",
                         re.MULTILINE)
# A module- or class-level binding: `LOG: deque[dict] = deque(...)`, `REGISTRY = {}`. Excludes
# `==` (a comparison) and augmented assignment, which bind nothing new.
PY_ASSIGN = re.compile(r"^[ \t]*([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=\n]+)?=(?!=)", re.MULTILINE)
# Go: three alternatives, in order — a method (with its receiver captured), a plain func, a
# type. The receiver is captured because a method's unit is qualified by its owner
# (`(*FirebaseClaimsWriter).SetRoleClaims`): that is the form books cite, and it is strictly
# more precise than a bare name, which cannot disambiguate two types declaring the same method
# in one file. Both pointer and value receivers appear in real books. `[(\[]` after the name
# admits generic declarations (`func Map[T any](…)`).
GO_DECL = re.compile(
    r"^func\s+\(\s*(?:[A-Za-z_][A-Za-z0-9_]*\s+)?(\*?)\s*([A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\[[^\]]*\])?\s*\)\s*([A-Za-z][A-Za-z0-9_]*)\s*[(\[]"
    r"|^func\s+([A-Za-z][A-Za-z0-9_]*)\s*[(\[]"
    r"|^type\s+([A-Za-z][A-Za-z0-9_]*)(?:\[[^\]]*\])?\s+(?:struct|interface)\b",
    re.MULTILINE,
)
TS_DECL = re.compile(
    r"^export\s+(?:default\s+)?(?:declare\s+)?(?:async\s+)?"
    r"(?:function|class|interface|type|const|let|enum)\s+([A-Za-z_$][A-Za-z0-9_$]*)",
    re.MULTILINE,
)
# The same shapes without the `export` gate — grounding's question, not the inventory's.
TS_ANY_DECL = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:async\s+)?"
    r"(?:function|class|interface|type|const|let|enum)\s+([A-Za-z_$][A-Za-z0-9_$]*)",
    re.MULTILINE,
)
# PHP: one pass over class + function declarations *in source order*, so a method can be
# qualified by the class it sits in (`AddProjectAction.getRenderPath`). Grouped in one regex
# rather than two passes because the qualification depends on the interleaving.
PHP_DECL = re.compile(
    r"^\s*(?:abstract\s+|final\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"
    r"|^\s*(?:(public|protected|private)\s+)?(?:static\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
# Twig: a template's named regions. `{% block content %}` / `{%- block content -%}`.
TWIG_DECL = re.compile(r"\{%-?\s*block\s+([A-Za-z_][A-Za-z0-9_]*)")

# An identifier inside a qualified symbol: `(*Writer).SetRoleClaims` → Writer, SetRoleClaims.
SYMBOL_PART = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")


def _php_symbols(text: str, *, public_only: bool) -> list[str]:
    """Class names, plus each method qualified by its class (`Class.method`).

    For the inventory, private/protected methods are not part of the documented surface, and
    magic methods (`__construct`, …) are DI/framework boilerplate rather than behavior — both
    are skipped, mirroring the `_`-prefix filter the Python front end applies. For grounding,
    neither filter applies: the question is only whether the file declares the name.
    """
    out: list[str] = []
    current = ""
    for m in PHP_DECL.finditer(text):
        if cls := m.group(1):
            current = cls
            out.append(cls)
            continue
        visibility, name = m.group(2), m.group(3)
        if public_only and (visibility in ("private", "protected") or name.startswith("__")):
            continue
        out.append(f"{current}.{name}" if current else name)
        if not public_only:
            out.append(name)  # grounding matches part-wise, so the bare name must be present
    return out


def _go_symbols(text: str, *, exported_only: bool) -> list[str]:
    """Types/funcs, plus each method qualified by its receiver.

    `func (w *FirebaseClaimsWriter) SetRoleClaims(…)` → `(*FirebaseClaimsWriter).SetRoleClaims`;
    a value receiver drops the star. Export is judged on the *method* name, not the receiver's:
    an exported method on an unexported type is still part of the surface.
    """
    out: list[str] = []
    for star, receiver, method, func, typename in GO_DECL.findall(text):
        if method:
            if exported_only and not method[:1].isupper():
                continue
            owner = f"(*{receiver})" if star else receiver
            out.append(f"{owner}.{method}")
            if not exported_only:
                out.extend((method, receiver))
            continue
        name = func or typename
        if exported_only and not name[:1].isupper():
            continue
        out.append(name)
    return out


def symbols(path: str | Path, text: str) -> list[str]:
    """The **documented surface** a file declares — the inventory's units.

    Applies each language's export/visibility filter: an unexported helper is not a unit the
    book owes coverage for. See ``declared_names`` for the other question.
    """
    suffix = Path(path).suffix
    if suffix == ".py":
        return [m.group(1) for m in PY_DECL.finditer(text) if not m.group(1).startswith("_")]
    if suffix == ".go":
        return _go_symbols(text, exported_only=True)
    if suffix in {".ts", ".tsx"}:
        return [m.group(1) for m in TS_DECL.finditer(text)]
    if suffix == ".php":
        return _php_symbols(text, public_only=True)
    if suffix == ".twig":
        return TWIG_DECL.findall(text)
    return []


def declared_names(path: str | Path, text: str) -> set[str]:
    """**Every** name a file declares — grounding's question.

    No export or visibility filter: a book may document a private symbol, and grounding must
    not punish it for the inventory's narrower scope. Crucially this is a *declaration* set,
    not the words in the file — an imported or re-exported name is absent, which is what lets
    grounding notice a definition that moved out from under a citation.
    """
    suffix = Path(path).suffix
    if suffix == ".py":
        return ({m.group(1) for m in PY_ANY_DECL.finditer(text)}
                | {m.group(1) for m in PY_ASSIGN.finditer(text)})
    if suffix == ".go":
        return set(_go_symbols(text, exported_only=False))
    if suffix in {".ts", ".tsx"}:
        return {m.group(1) for m in TS_ANY_DECL.finditer(text)}
    if suffix == ".php":
        return set(_php_symbols(text, public_only=False))
    if suffix == ".twig":
        return set(TWIG_DECL.findall(text))
    return set()


def declares(path: str | Path, text: str, symbol: str) -> bool:
    """Whether *text* declares *symbol*, in any of the profile's languages.

    Matching is **part-wise**: `(*Writer).SetRoleClaims` needs `Writer` and `SetRoleClaims` to
    each be declared here. That tolerance is deliberate — the alternative is holding the book's
    qualified grammar to an exact string the front end happens to emit, and when the book and
    the tool disagree about grammar, the book wins.

    A file in a language the front end cannot read declares nothing it can speak to, so it
    grounds anything: silence about a language is not evidence against a citation.
    """
    if Path(path).suffix not in SOURCE_SUFFIXES:
        return True
    names = declared_names(path, text)
    parts = SYMBOL_PART.findall(symbol)
    return bool(parts) and all(part in names for part in parts)
