"""The source symbol front end — one grammar for the join and the grounding check."""
from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from ostler import index, syntax
from tree_sitter import Node

SOURCE_SUFFIXES = {".go", ".py", ".ts", ".tsx", ".php", ".twig"}

SYMBOL_PART = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")

_DEF_NODES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)

_GO_GROUPED = {"type_declaration", "var_declaration", "const_declaration"}
_GO_SPECS = {"type_spec", "type_alias", "var_spec", "const_spec"}

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
_TS_MEMBERS = {"method_definition", "public_field_definition"}
_TS_BINDINGS = {"lexical_declaration", "variable_declaration"}

_PHP_CONTAINERS = {"class_declaration", "interface_declaration", "trait_declaration",
                   "enum_declaration"}


def parse_python(text: str) -> ast.Module | None:
    """The parsed module, or None when *text* is not Python this interpreter can read."""
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError):
        return None


def _py_surface(text: str) -> list[str]:
    """The inventory's Python denominator: module-level `class`/`def`, in source order."""
    module = parse_python(text)
    if module is None:
        return _py_recovered_surface(text)
    return [
        node.name
        for node in module.body
        if isinstance(node, _DEF_NODES) and not node.name.startswith("_")
    ]


def _py_declared(text: str) -> set[str]:
    """Every name the module *binds* — grounding's question."""
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
    """The plain names an assignment target binds."""
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
    """The Python surface of a file `ast` refused — read with tree-sitter's error recovery."""
    out: list[str] = []
    for child in syntax.parse("python", text).named_children:
        node = _py_definition(child)
        if node.type in {"function_definition", "class_definition"}:
            name = syntax.field_text(node, "name")
            if name and not name.startswith("_"):
                out.append(name)
    return out


def _py_recovered_declared(text: str) -> set[str]:
    """Every name a file `ast` refused appears to bind."""
    names: set[str] = set()
    for node in syntax.walk(syntax.parse("python", text)):
        if node.type in {"function_definition", "class_definition"}:
            names.add(syntax.field_text(node, "name"))
        elif node.type in {"assignment", "named_expression"}:
            names.update(_py_target_names(node.child_by_field_name("left")
                                          or node.child_by_field_name("name")))
    return (names | syntax.error_names("python", text)) - {""}


def _py_target_names(target: Node | None) -> set[str]:
    """The names a recovered assignment target binds."""
    if target is None:
        return set()
    if target.type == "identifier":
        return {syntax.text_of(target)}
    if target.type in {"pattern_list", "tuple_pattern", "list_pattern", "list_splat_pattern"}:
        return {name for child in target.named_children for name in _py_target_names(child)}
    return set()


def _go_receiver(node: Node) -> tuple[bool, str]:
    """A method's receiver as (pointer, type name)."""
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


def _go_embedded_name(kind: Node | None) -> str:
    """The name an embedded field or interface is known by: its type's last identifier."""
    while kind is not None and kind.type in {"pointer_type", "generic_type"}:
        kind = kind.child_by_field_name("type") or (
            kind.named_children[0] if kind.named_children else None
        )
    if kind is None:
        return ""
    if kind.type == "qualified_type":
        return syntax.field_text(kind, "name")
    if kind.type == "type_identifier":
        return syntax.text_of(kind)
    return ""


def _go_member_names(spec: Node) -> list[str]:
    """Struct field and interface method names inside one type spec — grounding's extras."""
    out: list[str] = []
    for node in syntax.walk(spec):
        if node.type == "field_declaration":
            names = node.children_by_field_name("name")
            if names:
                out.extend(syntax.text_of(name) for name in names)
            else:
                out.append(_go_embedded_name(node.child_by_field_name("type")))
        elif node.type == "method_elem":
            out.append(syntax.field_text(node, "name"))
        elif node.type == "type_elem":
            out.append(
                _go_embedded_name(node.named_children[0] if node.named_children else None)
            )
    return [name for name in out if name]


def _go_symbols(text: str, *, exported_only: bool) -> list[str]:
    """Types/funcs/vars/consts, plus each method qualified by its receiver."""
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
                    if not exported_only and spec.type in {"type_spec", "type_alias"}:
                        out.extend(_go_member_names(spec))
    return [name for name in out if name]


def _ts_pattern_names(node: Node | None) -> list[str]:
    """The names a binding site introduces, destructuring included."""
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
    if node.type == "ambient_declaration":
        return [name for child in node.named_children for name in _ts_declaration_names(child)]
    return []


def _ts_surface(text: str, language: str) -> list[str]:
    """The inventory's TypeScript denominator: what the module exports, in source order."""
    out: list[str] = []
    for node in syntax.parse(language, text).named_children:
        if node.type != "export_statement":
            continue
        declaration = node.child_by_field_name("declaration")
        if declaration is not None:
            out.extend(_ts_declaration_names(declaration))
    return [name for name in out if name]


def _ts_declared(text: str, language: str) -> set[str]:
    """Every name a TypeScript file binds — the export gate removed, at any depth."""
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
    """Class names, plus each method qualified by the class it is declared in (`Class.method`)."""
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
                    out.append(name)
            elif child.type == "function_definition":
                if name := syntax.field_text(child, "name"):
                    out.append(name)
                visit(child, owner)
            else:
                visit(child, owner)

    visit(syntax.parse("php", text), "")
    return out


def _twig_blocks(text: str) -> list[str]:
    """A template's named regions: `{% block content %}` → `content`."""
    out: list[str] = []
    for node in syntax.walk(syntax.parse("twig", text)):
        if node.type != "tag_statement":
            continue
        parts = node.named_children
        if len(parts) >= 2 and parts[0].type == "tag" and syntax.text_of(parts[0]) == "block":
            out.append(syntax.text_of(parts[1]))
    return [name for name in out if name]


def symbols(path: str | Path, text: str) -> list[str]:
    """The **documented surface** a file declares — the inventory's units."""
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
    """**Every** name a file declares — grounding's question."""
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
    """Whether *text* declares *symbol*, in any of the profile's languages."""
    if Path(path).suffix not in SOURCE_SUFFIXES:
        return True
    return _grounds(declared_names(path, text), symbol)


def symbol_parts(symbol: str) -> frozenset[str]:
    """The identifiers inside a qualified symbol, order- and punctuation-independent."""
    return frozenset(SYMBOL_PART.findall(symbol))


def _grounds(names: set[str] | frozenset[str], symbol: str) -> bool:
    parts = symbol_parts(symbol)
    return bool(parts) and parts.issubset(names)




@dataclass(frozen=True)
class _SymbolTable:
    """An index entry's payload: one file's declaration set and its per-symbol digests."""

    names: frozenset[str]
    digests: dict[str, str]


_SYMBOLS_NAMESPACE = "symbols/3"

_SYMBOL_MEMO: dict[tuple[Path, str, str], tuple[_SymbolTable, index.IndexStore | None]] = {}

_EMPTY_TABLE = _SymbolTable(names=frozenset(), digests={})


def _symbol_key(store: index.IndexStore, digest: str) -> str:
    """The entry key for a symbol table: the content sha and the grammar that will read it."""
    return store.content_key(_SYMBOLS_NAMESPACE, syntax.grammar_version(), digest)


def declared_names_at(path: str | Path) -> frozenset[str]:
    """Every name the file at *path* declares, extracted once per (content sha, grammar version)."""
    return _table_at(path).names


def _table_at(path: str | Path) -> _SymbolTable:
    """The symbol table for the file at *path* — one extraction per (content sha, grammar)."""
    target = Path(path)
    if target.suffix not in SOURCE_SUFFIXES:
        return _EMPTY_TABLE
    data = target.read_bytes()
    digest = index.content_sha(data)
    store = index.active()
    memo_key = (target, digest, syntax.grammar_version())
    memoed = _SYMBOL_MEMO.get(memo_key)
    if memoed is not None and memoed[1] is store:
        return memoed[0]
    table = _extracted(target, data, digest, store)
    _SYMBOL_MEMO[memo_key] = (table, store)
    return table


def _extracted(target: Path, data: bytes, digest: str,
               store: index.IndexStore | None) -> _SymbolTable:
    """*target*'s symbol table, from the store when it has it and from the parser otherwise."""
    if store is not None:
        payload = store.get_key(_symbol_key(store, digest))
        if isinstance(payload, _SymbolTable):
            return payload
    text = data.decode("utf-8")
    table = _SymbolTable(
        names=frozenset(declared_names(target, text)),
        digests=symbol_digests(target, text),
    )
    if store is not None:
        store.put_key(_symbol_key(store, digest), table)
    return table


def declares_at(path: str | Path, symbol: str) -> bool:
    """Whether the file at *path* declares *symbol* — :func:`declares`, served from the index."""
    if Path(path).suffix not in SOURCE_SUFFIXES:
        return True
    return _grounds(declared_names_at(path), symbol)


def extents(path: str | Path, text: str,
            *, language: str | None = None) -> list[tuple[int, int, str]]:
    """Each declaration as `(first line, last line, qualified name)`, 1-based and inclusive."""
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
    """Python's extents, from `ast` — nested declarations qualified by their owner."""
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


def _py_recovered_declarations(text: str) -> list[tuple[Node, str]]:
    """Python's declarations from the recovered tree, as `(node, qualified name)`."""
    found: list[tuple[Node, str]] = []

    def visit(node: Node, prefix: str) -> None:
        for child in node.named_children:
            definition = _py_definition(child)
            if definition.type in {"function_definition", "class_definition"}:
                own = syntax.field_text(definition, "name")
                name = f"{prefix}.{own}" if prefix else own
                if own:
                    found.append((child, name))
                visit(definition, name if own else prefix)
            else:
                visit(child, prefix)

    visit(syntax.parse("python", text), "")
    return found


def _py_recovered_extents(text: str) -> list[tuple[int, int, str]]:
    """Python's extents from the recovered tree."""
    return [(*syntax.lines_of(node), name) for node, name in _py_recovered_declarations(text)]


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


def _ts_declarations(node: Node, prefix: str = "") -> list[tuple[Node, str]]:
    """TypeScript's declarations, each qualified by the declaration that lexically encloses it."""
    found: list[tuple[Node, str]] = []
    for child in node.named_children:
        names = [f"{prefix}.{name}" if prefix else name for name in _ts_declared_here(child)]
        found.extend((child, name) for name in names)
        found.extend(_ts_declarations(child, names[0] if len(names) == 1 else prefix))
    return found


def _ts_declared_here(node: Node) -> list[str]:
    """The names *node* itself declares, unqualified — `[]` for anything that declares none."""
    if node.type in _TS_MEMBERS or node.type in _TS_NAMED:
        return [name for name in [syntax.field_text(node, "name")] if name]
    if node.type == "variable_declarator":
        return [name for name in _ts_pattern_names(node.child_by_field_name("name")) if name]
    return []


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




def _token_digest(node: Node) -> str:
    """A declaration's content digest: its tokens, with comments and layout removed."""
    digest = hashlib.sha256()
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type.endswith("comment"):
            continue
        children = current.children
        if children:
            stack.extend(reversed(children))
            continue
        digest.update(current.text or b"")
        digest.update(b"\0")
    return digest.hexdigest()


def symbol_digests(path: str | Path, text: str,
                   *, language: str | None = None) -> dict[str, str]:
    """Each declaration's content digest, keyed by the name the book would cite it by."""
    grammar = language or syntax.language_for(path)
    if grammar is None or not text:
        return {}
    if grammar == "python":
        module = parse_python(text)
        if module is not None:
            return _py_digests(module)
        return {
            name: _token_digest(node) for node, name in _py_recovered_declarations(text)
        }
    if grammar == "twig":
        return _twig_digests(text)
    return {name: _token_digest(node) for node, name in _tree_declarations(grammar, text)}


def _twig_digests(text: str) -> dict[str, str]:
    """Twig's digests, one per `{% block name %}` region."""
    found: dict[str, str] = {}
    open_blocks: list[tuple[str, list[Node]]] = []
    for node in syntax.parse("twig", text).named_children:
        tag, name = _twig_tag(node)
        if tag == "block" and name:
            open_blocks.append((name, []))
        for _, collected in open_blocks:
            collected.append(node)
        if tag == "endblock" and open_blocks:
            closed, collected = open_blocks.pop()
            digest = hashlib.sha256()
            for member in collected:
                digest.update(_token_digest(member).encode("ascii"))
            found[closed] = digest.hexdigest()
    return found


def _twig_tag(node: Node) -> tuple[str, str]:
    """A `statement_directive`'s tag and its argument — `("block", "content")`, or `("", "")`."""
    if node.type != "statement_directive":
        return ("", "")
    inner = node.named_children
    if not inner or inner[0].type != "tag_statement":
        return ("", "")
    parts = inner[0].named_children
    if not parts or parts[0].type != "tag":
        return ("", "")
    return (syntax.text_of(parts[0]), syntax.text_of(parts[1]) if len(parts) >= 2 else "")


def _py_digests(module: ast.Module) -> dict[str, str]:
    """Python's digests, from the parsed module."""
    found: dict[str, str] = {}

    def visit(node: ast.AST, prefix: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _DEF_NODES):
                name = f"{prefix}.{child.name}" if prefix else child.name
                found[name] = hashlib.sha256(ast.dump(child).encode("utf-8")).hexdigest()
                visit(child, name)
            else:
                visit(child, prefix)

    visit(module)
    return found


def symbol_digests_at(path: str | Path) -> dict[str, str]:
    """:func:`symbol_digests` for the file at *path*, served from the index."""
    return dict(_table_at(path).digests)




def _py_imports(text: str) -> list[str]:
    """Python's imports as dotted module paths, in source order."""
    module = parse_python(text)
    if module is None:
        return _py_recovered_imports(text)
    out: list[str] = []
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    out.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            if node.level:
                module_name = f"{'.' * node.level}{module_name}" if module_name else "." * node.level
            if module_name:
                out.append(module_name)
    return out


def _py_recovered_imports(text: str) -> list[str]:
    """Python imports from a recovered tree, when `ast` refused the file."""
    out: list[str] = []
    for node in syntax.walk(syntax.parse("python", text)):
        if node.type == "import_statement":
            for child in node.named_children:
                if child.type == "dotted_name":
                    out.append(syntax.text_of(child))
                elif child.type == "aliased_import":
                    inner = child.child_by_field_name("name")
                    if inner is not None:
                        out.append(syntax.text_of(inner))
        elif node.type == "import_from_statement":
            module_name = ""
            level = 0
            for child in node.children:
                if child.type == "import_prefix":
                    level += 1
                elif child.type == "dotted_name" and not module_name:
                    module_name = syntax.text_of(child)
            if level:
                out.append(f"{'.' * level}{module_name}" if module_name else "." * level)
            elif module_name:
                out.append(module_name)
    return out


def _go_imports(text: str) -> list[str]:
    """Go's imports: every `import "path"` and `import (...)` member, verbatim."""
    out: list[str] = []
    for node in syntax.walk(syntax.parse("go", text)):
        if node.type == "import_spec":
            path = node.child_by_field_name("path")
            if path is not None:
                value = syntax.text_of(path).strip('"').strip("`")
                if value:
                    out.append(value)
        elif node.type == "import_spec_list":
            continue
    return out


def _ts_imports(text: str) -> list[str]:
    """TypeScript's imports: `import x from "y"`, side-effect `import "y"`, `require("y")`."""
    out: list[str] = []
    for node in syntax.walk(syntax.parse("typescript", text)):
        if node.type == "import_statement":
            source = node.child_by_field_name("source")
            if source is not None:
                value = syntax.text_of(source).strip('"').strip("'")
                if value:
                    out.append(value)
        elif node.type == "call_expression":
            function = node.child_by_field_name("function")
            args = node.child_by_field_name("arguments")
            if function is not None and args is not None and syntax.text_of(function) == "require":
                if args.named_children and args.named_children[0].type == "string":
                    value = syntax.text_of(args.named_children[0]).strip('"').strip("'")
                    if value:
                        out.append(value)
    return out


def imports_of(path: str | Path, text: str, *,
               language: str | None = None) -> list[str]:
    """The module specifiers a file imports, in source order, deduplicated."""
    grammar = language or syntax.language_for(path)
    if grammar is None or not text:
        return []
    if grammar == "python":
        raw = _py_imports(text)
    elif grammar == "go":
        raw = _go_imports(text)
    elif grammar in {"typescript", "tsx"}:
        raw = _ts_imports(text)
    else:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for spec in raw:
        if spec and spec not in seen:
            seen.add(spec)
            out.append(spec)
    return out
