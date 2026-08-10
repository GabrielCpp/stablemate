"""The source symbol front end — one grammar for the join and the grounding check.

Three callers need to know what a file declares, and they must agree:

* **the coverage join** (``ostler coverage``) inventories a tree's units, which the book's
  ``code:`` citations are diffed against;
* **``doctor``'s ``code:`` grounding**, which asserts a citation names a file that exists and a
  symbol that file declares;
* **the QA diff mapper** (``ostler qa context``), which asks the same question of a *line*:
  which unit does this changed hunk belong to.

They used to answer that question in two places — real declaration regexes in the builder's
source inventory (the `inventory_source` node), and a *word-presence* test in `doctor`. The two disagreed, and the
disagreement was invisible in the direction that mattered: a facade module that re-exports a
name (``from .renderer import Renderer``) still contains the word, so grounding passed on a
citation whose definition had moved away. A book could cite a symbol its file no longer
declared and `doctor` stayed green — the exact drift §4.4 exists to catch. One grammar, defined
once, is the fix.

**Every language is parsed.** Python is read with the stdlib `ast`, because a real parse is
free there; the other five go through `syntax`, which is tree-sitter. The regexes those
replace were wrong in both directions at once, because a regex matches text and text includes
comments, strings and unrelated scopes — a commented-out `export function ghost()` entered the
coverage *denominator*, a name inside a template literal grounded a citation, and the shapes
the pattern did not spell (`export abstract class`, `export const {a, b} = …`, Go's grouped
`type (…)`) were invisible, which turns a correct citation into a `missing-code-symbol` no
edit can clear. `syntax`'s module docstring has the argument for tree-sitter over the target
repo's own toolchain.

**Two questions, two answers, deliberately.** ``symbols()`` reports the *documented surface* —
it applies each language's export/visibility filter, because an unexported helper is not a unit
a book owes coverage for. ``declared_names()`` reports *everything the file declares*, filter
and all removed, because grounding a citation is a different question: a book may legitimately
document a private symbol (``main.py::_run_run`` **is** the subcommand handler), and flagging it
would punish the book for the inventory's narrower scope. A unit's shape is language-shaped;
so is its visibility, and only the first question cares.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from ostler import syntax
from tree_sitter import Node

# The languages the front end can read. A source tree containing NONE of these is an error, not
# an empty inventory — an unsupported language must never be indistinguishable from a fully
# documented one. Narrower than `syntax.LANGUAGES`, which also reads `.js`/`.jsx` for the QA
# diff mapper: those are attributable, but they are not units a book owes coverage for.
SOURCE_SUFFIXES = {".go", ".py", ".ts", ".tsx", ".php", ".twig"}

# An identifier inside a qualified symbol: `(*Writer).SetRoleClaims` → Writer, SetRoleClaims.
SYMBOL_PART = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")

_DEF_NODES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)

# ── Go ────────────────────────────────────────────────────────────────────────────────
#
# The four package-level declaration forms. `type`/`var`/`const` carry their names one level
# down in a *spec*, and a parenthesized group is the same spec repeated — which is why the
# grouped form needs no special case here, where the brace-counting scan it replaces existed
# entirely to fake one.
_GO_GROUPED = {"type_declaration", "var_declaration", "const_declaration"}
_GO_SPECS = {"type_spec", "type_alias", "var_spec", "const_spec"}

# ── TypeScript ────────────────────────────────────────────────────────────────────────
#
# The declaration shapes that carry a plain `name` field. `abstract_class_declaration` is its
# own node rather than a modifier on `class_declaration`, and `function_signature` is what
# `declare function f(): void` parses to — both were simply missing from the regex alternation,
# so an abstract class was a unit the inventory could never see.
_TS_NAMED = {
    "function_declaration",
    "generator_function_declaration",
    "function_signature",
    "class_declaration",
    "abstract_class_declaration",
    "interface_declaration",
    "type_alias_declaration",
    "enum_declaration",
}
#: A binding site inside a class body. Methods and fields are not part of the *inventory's*
#: surface (a class is the unit there) but a book may cite one, so grounding must see them.
_TS_MEMBERS = {"method_definition", "public_field_definition"}
#: `const x = …` and `var x = …`; the names hang off `variable_declarator`, possibly as a
#: destructuring pattern.
_TS_BINDINGS = {"lexical_declaration", "variable_declaration"}

# ── PHP ───────────────────────────────────────────────────────────────────────────────
#
# Only `class` is a unit for the inventory — interfaces, traits and enums join the grounding
# set alone, because widening the denominator would make every existing book instantly less
# complete.
_PHP_CONTAINERS = {"class_declaration", "interface_declaration", "trait_declaration",
                   "enum_declaration"}


def parse_python(text: str) -> ast.Module | None:
    """The parsed module, or None when *text* is not Python this interpreter can read."""
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError):  # ValueError: a source containing NUL bytes
        return None


def _py_surface(text: str) -> list[str]:
    """The inventory's Python denominator: module-level `class`/`def`, in source order.

    "Module-level" is a structural fact rather than a column-0 match, which keeps the
    denominator exactly where it was while dropping the two ways the anchor lied: a `def` at
    the left margin of a docstring or a commented-out block counted, and a class body's methods
    did not (correctly) — but neither did a decorated declaration's *own* line matter, so a
    signature the formatter wrapped read as a declaration named after its first argument.
    A conditionally-defined function (inside `if TYPE_CHECKING:`) stays out, as before.
    """
    module = parse_python(text)
    if module is None:
        return _py_recovered_surface(text)
    return [
        node.name
        for node in module.body
        if isinstance(node, _DEF_NODES) and not node.name.startswith("_")
    ]


def _py_declared(text: str) -> set[str]:
    """Every name the module *binds* — grounding's question.

    Classes, functions and methods at any depth, plus assignment targets. Imports are absent
    by construction, which is the property the whole module exists for: a facade that
    re-exports `Renderer` must not ground a citation whose definition moved away.

    Augmented assignment (`count += 1`) binds nothing new and is excluded; tuple unpacking
    (`a, b = ...`) binds both, which the line regex could not see.
    """
    module = parse_python(text)
    if module is None:
        return _py_recovered_declared(text)
    names: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, _DEF_NODES):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names.update(_binding_names(target))
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            names.update(_binding_names(node.target))
    return names


def _binding_names(target: ast.expr) -> set[str]:
    """The plain names an assignment target binds. `self.x = …` binds no module-level name."""
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        return {name for item in target.elts for name in _binding_names(item)}
    if isinstance(target, ast.Starred):
        return _binding_names(target.value)
    return set()


def _py_definition(node: Node) -> Node:
    """Past a decorator stack to the declaration it decorates."""
    if node.type == "decorated_definition":
        return node.child_by_field_name("definition") or node
    return node


def _py_recovered_surface(text: str) -> list[str]:
    """The Python surface of a file `ast` refused — read with tree-sitter's error recovery.

    A file mid-edit is not one we can be *right* about, so approximating beats reporting
    nothing. This used to be a line regex, which meant an unparseable file was scanned by a
    grammar that disagreed with the parsed case; the recovered tree is the same grammar with a
    hole in it, so the two only ever differ about the broken region.
    """
    out: list[str] = []
    for child in syntax.parse("python", text).named_children:
        node = _py_definition(child)
        if node.type in {"function_definition", "class_definition"}:
            name = syntax.field_text(node, "name")
            if name and not name.startswith("_"):
                out.append(name)
    return out


def _py_recovered_declared(text: str) -> set[str]:
    """Every name a file `ast` refused appears to bind. See `_py_recovered_surface`."""
    names: set[str] = set()
    for node in syntax.walk(syntax.parse("python", text)):
        if node.type in {"function_definition", "class_definition"}:
            names.add(syntax.field_text(node, "name"))
        elif node.type in {"assignment", "named_expression"}:
            names.update(_py_target_names(node.child_by_field_name("left")
                                          or node.child_by_field_name("name")))
    return (names | syntax.error_names("python", text)) - {""}


def _py_target_names(target: Node | None) -> set[str]:
    """The names a recovered assignment target binds. `self.x = …` binds none."""
    if target is None:
        return set()
    if target.type == "identifier":
        return {syntax.text_of(target)}
    if target.type in {"pattern_list", "tuple_pattern", "list_pattern", "list_splat_pattern"}:
        return {name for child in target.named_children for name in _py_target_names(child)}
    return set()


def _go_receiver(node: Node) -> tuple[bool, str]:
    """A method's receiver as (pointer, type name). `func (g *G[T]) M()` → (True, "G")."""
    receiver = node.child_by_field_name("receiver")
    declaration = next(
        (c for c in receiver.named_children if c.type == "parameter_declaration"), None
    ) if receiver is not None else None
    kind = declaration.child_by_field_name("type") if declaration is not None else None
    if kind is None:
        return False, ""
    pointer = kind.type == "pointer_type"
    if pointer:
        kind = kind.named_children[0] if kind.named_children else None
    if kind is not None and kind.type == "generic_type":
        kind = kind.child_by_field_name("type")
    return pointer, syntax.text_of(kind)


def _go_symbols(text: str, *, exported_only: bool) -> list[str]:
    """Types/funcs/vars/consts, plus each method qualified by its receiver.

    `func (w *FirebaseClaimsWriter) SetRoleClaims(…)` → `(*FirebaseClaimsWriter).SetRoleClaims`;
    a value receiver drops the star. Export is judged on the *method* name, not the receiver's:
    an exported method on an unexported type is still part of the surface.

    Package-level values count. A Go table (`var ElementRules = map[…]{…}`) is where a
    closed vocabulary actually lives, and it is the direct analog of the TypeScript `const`
    the TS scanner has always resolved — a book documenting both sides of a parity pair
    could ground the TS half and never the Go one, which makes a correct citation an
    unfixable `missing-code-symbol`.

    Only `source_file`'s own children are read, which is what keeps a function-local `var` out
    of a package's symbol set. Ordering is source order, because `symbols` is the inventory's
    ordered unit list.
    """
    out: list[str] = []

    def keep(name: str) -> None:
        if name and not (exported_only and not name[:1].isupper()):
            out.append(name)

    for node in syntax.parse("go", text).named_children:
        if node.type == "function_declaration":
            keep(syntax.field_text(node, "name"))
        elif node.type == "method_declaration":
            method = syntax.field_text(node, "name")
            if exported_only and not method[:1].isupper():
                continue
            pointer, owner = _go_receiver(node)
            out.append(f"(*{owner}).{method}" if pointer else f"{owner}.{method}")
            if not exported_only:
                out.extend((method, owner))
        elif node.type in _GO_GROUPED:
            for spec in syntax.walk(node):
                if spec.type in _GO_SPECS:
                    for name in spec.children_by_field_name("name"):
                        keep(syntax.text_of(name))
    return [name for name in out if name]


def _ts_pattern_names(node: Node | None) -> list[str]:
    """The names a binding site introduces, destructuring included.

    `const {a, b: c} = x` binds `a` and `c` — the *value* half of a `pair_pattern`, not the
    key. The regex saw neither, because it read one identifier after the keyword and a `{` is
    not an identifier.
    """
    if node is None:
        return []
    if node.type in {"identifier", "shorthand_property_identifier_pattern",
                     "property_identifier", "type_identifier"}:
        return [syntax.text_of(node)]
    if node.type == "pair_pattern":
        return _ts_pattern_names(node.child_by_field_name("value"))
    if node.type == "assignment_pattern":
        return _ts_pattern_names(node.child_by_field_name("left"))
    if node.type in {"object_pattern", "array_pattern", "rest_pattern"}:
        return [name for child in node.named_children for name in _ts_pattern_names(child)]
    return []


def _ts_declaration_names(node: Node) -> list[str]:
    """The names one declaration introduces — the shared half of both TS questions."""
    if node.type in _TS_NAMED:
        return [syntax.field_text(node, "name")]
    if node.type in _TS_BINDINGS:
        return [
            name
            for child in node.named_children
            if child.type == "variable_declarator"
            for name in _ts_pattern_names(child.child_by_field_name("name"))
        ]
    if node.type == "ambient_declaration":  # `declare function f(): void`
        return [name for child in node.named_children for name in _ts_declaration_names(child)]
    return []


def _ts_surface(text: str, language: str) -> list[str]:
    """The inventory's TypeScript denominator: what the module exports, in source order.

    A re-export (`export { Re } from './x'`) is deliberately absent: it declares nothing here,
    and counting it would put the same unit in two files' denominators.
    """
    out: list[str] = []
    for node in syntax.parse(language, text).named_children:
        if node.type != "export_statement":
            continue
        declaration = node.child_by_field_name("declaration")
        if declaration is not None:
            out.extend(_ts_declaration_names(declaration))
    return [name for name in out if name]


def _ts_declared(text: str, language: str) -> set[str]:
    """Every name a TypeScript file binds — the export gate removed, at any depth.

    Depth is kept because Python's answer keeps it: `ast.walk` reaches a nested `def` and a
    function-local assignment alike, and grounding is the one question that should err wide.
    What the parse removes is not depth but *unreality* — a declaration inside a comment or a
    template literal is not a binding, and used to ground a citation.
    """
    names: set[str] = set()
    for node in syntax.walk(syntax.parse(language, text)):
        if node.type in _TS_MEMBERS:
            names.add(syntax.field_text(node, "name"))
        elif node.type == "variable_declarator":
            names.update(_ts_pattern_names(node.child_by_field_name("name")))
        else:
            names.update(_ts_declaration_names(node))
    return names - {""}


def _php_symbols(text: str, *, public_only: bool) -> list[str]:
    """Class names, plus each method qualified by the class it is declared in (`Class.method`).

    For the inventory, private/protected methods are not part of the documented surface, and
    magic methods (`__construct`, …) are DI/framework boilerplate rather than behavior — both
    are skipped, mirroring the `_`-prefix filter the Python front end applies. For grounding,
    neither filter applies: the question is only whether the file declares the name, and
    interfaces, traits and enums join it there.

    Qualification follows the *tree* rather than the last class seen above the match, so a
    plain function declared after a class is no longer attributed to it.
    """
    out: list[str] = []

    def visit(node: Node, owner: str) -> None:
        for child in node.named_children:
            if child.type in _PHP_CONTAINERS:
                name = syntax.field_text(child, "name")
                if name and (child.type == "class_declaration" or not public_only):
                    out.append(name)
                visit(child, name)
            elif child.type == "method_declaration":
                name = syntax.field_text(child, "name")
                visibility = next(
                    (syntax.text_of(m) for m in child.named_children
                     if m.type == "visibility_modifier"), "")
                if not name or (public_only and (visibility in {"private", "protected"}
                                                 or name.startswith("__"))):
                    continue
                out.append(f"{owner}.{name}" if owner else name)
                if not public_only:
                    out.append(name)  # grounding matches part-wise: the bare name must be there
            elif child.type == "function_definition":
                if name := syntax.field_text(child, "name"):
                    out.append(name)
                visit(child, owner)
            else:
                visit(child, owner)

    visit(syntax.parse("php", text), "")
    return out


def _twig_blocks(text: str) -> list[str]:
    """A template's named regions: `{% block content %}` → `content`.

    Parsed rather than matched so that a block named inside a `{# … #}` comment — the shape a
    half-removed region leaves behind — is not a unit the book owes coverage for.
    """
    out: list[str] = []
    for node in syntax.walk(syntax.parse("twig", text)):
        if node.type != "tag_statement":
            continue
        parts = node.named_children
        if len(parts) >= 2 and parts[0].type == "tag" and syntax.text_of(parts[0]) == "block":
            out.append(syntax.text_of(parts[1]))
    return [name for name in out if name]


def symbols(path: str | Path, text: str) -> list[str]:
    """The **documented surface** a file declares — the inventory's units.

    Applies each language's export/visibility filter: an unexported helper is not a unit the
    book owes coverage for. See ``declared_names`` for the other question.
    """
    suffix = Path(path).suffix
    if suffix == ".py":
        return _py_surface(text)
    if suffix == ".go":
        return _go_symbols(text, exported_only=True)
    if suffix in {".ts", ".tsx"}:
        return _ts_surface(text, syntax.LANGUAGES[suffix])
    if suffix == ".php":
        return _php_symbols(text, public_only=True)
    if suffix == ".twig":
        return _twig_blocks(text)
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
        return _py_declared(text)
    if suffix not in SOURCE_SUFFIXES:
        return set()
    grammar = syntax.LANGUAGES[suffix]
    if suffix == ".go":
        names = set(_go_symbols(text, exported_only=False))
    elif suffix in {".ts", ".tsx"}:
        names = _ts_declared(text, grammar)
    elif suffix == ".php":
        names = set(_php_symbols(text, public_only=False))
    else:
        names = set(_twig_blocks(text))
    return names | syntax.error_names(grammar, text)


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


def extents(path: str | Path, text: str,
            *, language: str | None = None) -> list[tuple[int, int, str]]:
    """Each declaration as `(first line, last line, qualified name)`, 1-based and inclusive.

    The QA diff mapper's question: a changed hunk belongs to the innermost declaration whose
    body spans it. A parse is what makes the *extent* real — the line scan this replaces knew
    only where each declaration started and assumed it ended where the next one began, so a
    hunk in a trailing comment, or anywhere inside a nested declaration, was attributed to
    whichever name happened to be above it.

    `language` overrides the suffix mapping, for a file whose name carries no extension.
    Returns `[]` for a language no front end reads, which the caller distinguishes from a file
    that genuinely declares nothing.
    """
    grammar = language or syntax.language_for(path)
    if grammar is None or not text:
        return []
    if grammar == "python":
        return _py_extents(text)
    return [
        (*syntax.lines_of(node), name)
        for node, name in _tree_declarations(grammar, text)
    ]


def _py_extents(text: str) -> list[tuple[int, int, str]]:
    """Python's extents, from `ast` — nested declarations qualified by their owner.

    A file `ast` refuses is the *normal* case here rather than an exotic one: the mapper reads
    both sides of a diff, and the base side of a half-finished refactor often does not parse.
    Tree-sitter's recovery answers for it, so a hunk in a broken file still names its unit.
    """
    module = parse_python(text)
    if module is None:
        return _py_recovered_extents(text)
    found: list[tuple[int, int, str]] = []

    def visit(node: ast.AST, prefix: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _DEF_NODES):
                name = f"{prefix}.{child.name}" if prefix else child.name
                found.append((child.lineno, getattr(child, "end_lineno", child.lineno), name))
                visit(child, name)
            else:
                visit(child, prefix)

    visit(module)
    return found


def _py_recovered_extents(text: str) -> list[tuple[int, int, str]]:
    """Python's extents from the recovered tree. See `_py_extents`."""
    found: list[tuple[int, int, str]] = []

    def visit(node: Node, prefix: str) -> None:
        for child in node.named_children:
            definition = _py_definition(child)
            if definition.type in {"function_definition", "class_definition"}:
                own = syntax.field_text(definition, "name")
                name = f"{prefix}.{own}" if prefix else own
                if own:
                    found.append((*syntax.lines_of(child), name))
                visit(definition, name if own else prefix)
            else:
                visit(child, prefix)

    visit(syntax.parse("python", text), "")
    return found


def _tree_declarations(grammar: str, text: str) -> list[tuple[Node, str]]:
    """Every declaration node in *text*, with the name the book would cite it by."""
    root = syntax.parse(grammar, text)
    if grammar == "go":
        return _go_declarations(root)
    if grammar in {"typescript", "tsx"}:
        return _ts_declarations(root)
    if grammar == "php":
        return _php_declarations(root, "")
    return []


def _go_declarations(root: Node) -> list[tuple[Node, str]]:
    found: list[tuple[Node, str]] = []
    for node in root.named_children:
        if node.type == "function_declaration":
            found.append((node, syntax.field_text(node, "name")))
        elif node.type == "method_declaration":
            pointer, owner = _go_receiver(node)
            method = syntax.field_text(node, "name")
            found.append((node, f"(*{owner}).{method}" if pointer else f"{owner}.{method}"))
        elif node.type in _GO_GROUPED:
            found.extend(
                (spec, syntax.text_of(name))
                for spec in syntax.walk(node) if spec.type in _GO_SPECS
                for name in spec.children_by_field_name("name")
            )
    return [(node, name) for node, name in found if name]


def _ts_declarations(root: Node) -> list[tuple[Node, str]]:
    found: list[tuple[Node, str]] = []
    for node in syntax.walk(root):
        if node.type in _TS_MEMBERS:
            found.append((node, syntax.field_text(node, "name")))
        elif node.type in _TS_NAMED:
            found.append((node, syntax.field_text(node, "name")))
        elif node.type == "variable_declarator":
            found.extend(
                (node, name) for name in _ts_pattern_names(node.child_by_field_name("name"))
            )
    return [(node, name) for node, name in found if name]


def _php_declarations(node: Node, owner: str) -> list[tuple[Node, str]]:
    found: list[tuple[Node, str]] = []
    for child in node.named_children:
        if child.type in _PHP_CONTAINERS:
            name = syntax.field_text(child, "name")
            found.append((child, name))
            found.extend(_php_declarations(child, name))
        elif child.type == "method_declaration":
            name = syntax.field_text(child, "name")
            found.append((child, f"{owner}.{name}" if owner else name))
        elif child.type == "function_definition":
            found.append((child, syntax.field_text(child, "name")))
        else:
            found.extend(_php_declarations(child, owner))
    return [(item, name) for item, name in found if name]
