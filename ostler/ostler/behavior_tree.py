"""Tree-sitter behavior candidates for languages a table can describe."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tree_sitter import Node

from ostler import syntax
from ostler.behavior_lexical import LexicalEvidence


@dataclass(frozen=True)
class LanguageTable:
    """What a language's syntax tree means to the audit."""

    framework: str
    root: str
    functions: frozenset[str]
    """Declarations that open a symbol and emit a ``function_contract`` up to the body."""
    literals: frozenset[str]
    """Anonymous functions; named ``<literal:n>`` under the enclosing symbol."""
    containers: frozenset[str]
    """Declarations that open a symbol without a contract: classes, interfaces, aliases."""
    binders: frozenset[str]
    """``const f = () => {}`` and its kin: the symbol is the binder's name, the body the value's."""
    wrappers: frozenset[str]
    """Statements that carry an export down to their binders without opening a symbol."""
    fields: frozenset[str]
    field_holders: frozenset[str]
    """A field counts only directly under one of these, not in an inline type elsewhere."""
    parameters: frozenset[str]
    returns: frozenset[str]
    raises: frozenset[str]
    routes: frozenset[str]
    responses: frozenset[str]
    conditionals: frozenset[str]
    """``if``: the consequence and alternative fields are labelled conditions."""
    contextual: frozenset[str]
    """Everything else whose header encloses its children lexically."""
    exports: frozenset[str]
    """The wrapper that marks its declaration exported; a re-export clause names locals."""
    private_modifiers: frozenset[str] = frozenset({"private", "protected"})
    private_prefixes: tuple[str, ...] = ("#", "_")
    """Name spellings that mean private where the language has a convention for it; PHP has none."""
    modifier: str = "accessibility_modifier"
    """The child node that spells a member's visibility, on the member or on its holder."""
    module_public: bool = False
    """Whether a top-level declaration is public without an export marker (PHP), or not (TS)."""
    sigil: str = ""
    """A prefix a name carries in the source but not in a book citation (PHP's ``$``)."""
    default_field: str = "value"
    """The parameter field that carries a default."""
    binder_fields: tuple[str, str] = ("name", "value")
    consequence_field: str = "consequence"
    """The conditional's taken-branch field; every other named child but the condition is an else."""
    calls: frozenset[str] = frozenset({"call_expression"})
    call_name: tuple[str, ...] = ("function", "property")
    """Field path from a call to the member name it invokes; a missing hop means no member."""
    skip: frozenset[str] = frozenset({"comment"})
    headers: frozenset[str] = field(default_factory=lambda: frozenset({
        "{", ":", "statement_block", "switch_body", "=>", "compound_statement", "declaration_list", "switch_block"}))
    field_note: str = ""
    route_note: str = ""
    response_note: str = ""
    raise_note: str = ""


TYPESCRIPT = LanguageTable(
    framework="typescript",
    root="program",
    functions=frozenset({"function_declaration", "generator_function_declaration", "method_definition",
                         "function_signature", "method_signature", "abstract_method_signature"}),
    literals=frozenset({"arrow_function", "function_expression", "generator_function"}),
    containers=frozenset({"class_declaration", "abstract_class_declaration", "interface_declaration",
                          "type_alias_declaration", "enum_declaration", "module", "internal_module"}),
    binders=frozenset({"variable_declarator"}),
    wrappers=frozenset({"lexical_declaration", "variable_declaration"}),
    fields=frozenset({"public_field_definition", "property_signature"}),
    field_holders=frozenset({"class_body", "interface_body", "type_alias_declaration"}),
    parameters=frozenset({"required_parameter", "optional_parameter"}),
    returns=frozenset({"return_statement"}),
    raises=frozenset({"throw_statement"}),
    routes=frozenset({"get", "post", "put", "delete", "patch", "head", "options", "all", "use", "route"}),
    responses=frozenset({"status", "sendStatus", "json", "send", "redirect", "render", "end"}),
    conditionals=frozenset({"if_statement"}),
    contextual=frozenset({"switch_statement", "switch_case", "switch_default", "for_statement", "for_in_statement",
                          "while_statement", "do_statement", "try_statement", "catch_clause", "finally_clause",
                          "ternary_expression"}),
    exports=frozenset({"export_statement"}),
    field_note="typescript class field or interface property; types are syntax, not validated constraints",
    route_note="unresolved express-like registration call",
    response_note="unresolved express-like response call",
    raise_note="typescript throw; the thrown value's type is not resolved",
)

PHP = LanguageTable(
    framework="php",
    root="program",
    functions=frozenset({"function_definition", "method_declaration"}),
    literals=frozenset({"anonymous_function", "arrow_function"}),
    containers=frozenset({"class_declaration", "interface_declaration", "trait_declaration", "enum_declaration"}),
    binders=frozenset({"assignment_expression"}),
    wrappers=frozenset({"expression_statement"}),
    fields=frozenset({"property_element", "const_element", "enum_case"}),
    field_holders=frozenset({"declaration_list", "enum_declaration_list"}),
    parameters=frozenset({"simple_parameter", "property_promotion_parameter"}),
    returns=frozenset({"return_statement"}),
    raises=frozenset({"throw_expression"}),
    routes=frozenset({"get", "post", "put", "delete", "patch", "options", "any", "map", "group", "route"}),
    responses=frozenset({"withStatus", "json", "write", "redirect", "render", "setStatusCode", "send"}),
    conditionals=frozenset({"if_statement", "else_if_clause"}),
    contextual=frozenset({"switch_statement", "case_statement", "default_statement", "for_statement",
                          "foreach_statement", "while_statement", "do_statement", "try_statement", "catch_clause",
                          "finally_clause", "conditional_expression", "match_expression", "match_conditional_expression"}),
    exports=frozenset(),
    modifier="visibility_modifier",
    module_public=True,
    private_prefixes=(),
    sigil="$",
    default_field="default_value",
    binder_fields=("left", "right"),
    consequence_field="body",
    calls=frozenset({"member_call_expression", "scoped_call_expression", "nullsafe_member_call_expression"}),
    call_name=("name",),
    field_note="php class property or constant; a type is syntax, not a validated constraint",
    route_note="unresolved slim/laravel-like registration call",
    response_note="unresolved psr-7-like response call",
    raise_note="php throw; the thrown value's type is not resolved",
)

TABLES: dict[str, LanguageTable] = {"typescript": TYPESCRIPT, "tsx": TYPESCRIPT, "php": PHP}


MAX_DEPTH = 500


def _member_name(call: Node, path: tuple[str, ...], source_bytes: bytes) -> str:
    if not path:
        return ""
    *hops, last = path
    current: Node | None = call
    for hop in hops:
        current = current.child_by_field_name(hop) if current is not None else None
    if current is None or (hops and current.type != "member_expression"):
        return ""
    child = current.child_by_field_name(last)
    if child is None:
        return ""
    return source_bytes[child.start_byte:child.end_byte].decode()


class TreeEvidence(LexicalEvidence):
    """The TypeScript and PHP collector, driven by a language table."""

    def __init__(self, path: str, source: str, digest: str, table: LanguageTable) -> None:
        super().__init__(path, source, digest)
        self.table = table
        self.skip = table.skip
        self.framework = table.framework
        self.exported: list[bool] = []
        self.reexported: set[str] = set()
        self.handlers = 0
        """Depth inside a route registration call; its literal argument is the handler."""

    def _extra(self, symbol: str) -> dict[str, Any]:
        return {"exported": None if symbol == "<module>" else all(self.exported)}

    def _header(self, node: Node, *, stop: Node | None = None) -> str:
        end = stop.start_byte if stop is not None else node.end_byte
        if stop is None:
            boundary = next((child for child in node.children if child.type in self.table.headers), None)
            if boundary is not None:
                end = boundary.start_byte
        return self.source_bytes[node.start_byte:end].decode().strip()

    def _held(self, node: Node) -> bool:
        """Whether a field sits in a declaration's body rather than an inline type."""
        parent = node.parent
        while parent is not None and parent.type not in self.table.field_holders:
            if parent.type in self.table.functions | self.table.literals | self.table.containers:
                return False
            parent = parent.parent
        return parent is not None and (parent.type != "type_alias_declaration" or node.parent is not None
                                       and node.parent.parent == parent)

    def _visible(self, node: Node) -> bool:
        """A member is public unless a modifier or a private name says otherwise."""
        holders = [node] + ([node.parent] if node.parent is not None and node.parent.type not in self.table.field_holders else [])
        if any(child.type == self.table.modifier and self._slice(child) in self.table.private_modifiers
               for holder in holders for child in holder.children):
            return False
        return not self._name(node).startswith(self.table.private_prefixes)

    def _name(self, node: Node) -> str:
        """The declared name: the ``name`` field, or the bare ``name`` child a grammar leaves unlabelled."""
        name = self._field(node, "name")
        if not name:
            name = next((self._slice(child) for child in node.named_children if child.type == "name"), "")
        return name.removeprefix(self.table.sigil)

    def _open(self, node: Node, name: str, *, exported: bool) -> None:
        self.symbols.append(name)
        self.exported.append(exported)

    def _close(self) -> None:
        self.symbols.pop()
        self.exported.pop()

    def _function(self, node: Node, name: str, *, exported: bool) -> None:
        body = node.child_by_field_name("body")
        self._open(node, name, exported=exported)
        self.context(node)
        header = self._header(node, stop=body)
        self.emit(node, "function_contract", text=header, snippet=header)
        for child in node.named_children:
            self.visit(child)
        self._close()

    def visit(self, node: Node, *, exported: bool = False, depth: int = 0) -> None:
        table = self.table
        if node.type in table.skip:
            return
        if depth > MAX_DEPTH:
            return
        if node.type == table.root:
            for child in node.named_children:
                if child.type in table.exports:
                    for spec in syntax.walk(child):
                        if spec.type == "export_specifier":
                            self.reexported.add(self._slice(spec.named_children[0]))
            for child in node.named_children:
                before = len(self.candidates)
                self.visit(child, depth=depth + 1)
                if any(item.symbol == "<module>" for item in self.candidates[before:]):
                    self.context(child)
            return
        if node.type in table.exports:
            for child in node.named_children:
                self.visit(child, exported=True, depth=depth + 1)
            return
        if node.type in table.functions:
            name = self._name(node)
            visible = exported or (table.module_public and not self.symbols) or name in self.reexported
            visible = visible or (bool(self.symbols) and self._visible(node))
            self._function(node, name, exported=visible)
            return
        if node.type in table.literals:
            name = self._name(node)
            if not name:
                parent = ".".join(self.symbols)
                self.literals[parent] += 1
                name = f"<literal:{self.literals[parent]}>"
            visible = self.handlers > 0 or (bool(self.exported) and all(self.exported))
            self._function(node, name, exported=visible)
            return
        if node.type in table.binders:
            value = node.child_by_field_name(table.binder_fields[1])
            if value is not None and value.type in table.literals:
                name = self._field(node, table.binder_fields[0]).removeprefix(self.table.sigil)
                visible = exported or name in self.reexported or (table.module_public and not self.symbols)
                self._function(value, name, exported=visible or (bool(self.symbols) and all(self.exported)))
                return
        if node.type in table.wrappers:
            for child in node.named_children:
                self.visit(child, exported=exported, depth=depth + 1)
            return
        if node.type in table.containers:
            name = self._name(node)
            self._open(node, name, exported=exported or name in self.reexported or (table.module_public and not self.symbols))
            before = len(self.candidates)
            for child in node.named_children:
                self.visit(child, depth=depth + 1)
            if len(self.candidates) > before:
                self.context(node)
            self._close()
            return
        if node.type in table.fields and self._held(node):
            self._open(node, self._name(node), exported=self._visible(node))
            self.emit(node, "schema_field", framework=table.field_note)
            self._close()
            return
        if node.type in table.parameters:
            if node.child_by_field_name(table.default_field) is not None:
                self.emit(node, "function_default")
            return
        if node.type in table.returns:
            self.emit(node, "return")
        elif node.type in table.raises:
            self.emit(node, "raise", framework=table.raise_note)
        handler = False
        if node.type in table.calls:
            name = _member_name(node, table.call_name, self.source_bytes)
            if name in table.routes:
                self.emit(node, "route", framework=table.route_note)
                handler = True
            elif name in table.responses:
                self.emit(node, "http_response", framework=table.response_note)
        if node.type in table.conditionals:
            condition_node = node.child_by_field_name("condition")
            condition = self._slice(condition_node) if condition_node is not None else ""
            consequence = node.child_by_field_name(table.consequence_field)
            for child in node.named_children:
                label = "" if child == condition_node else f"if {condition}" if child == consequence else f"else of {condition}"
                if label:
                    self.conditions.append(label)
                self.visit(child, depth=depth + 1)
                if label:
                    self.conditions.pop()
            return
        contextual = node.type in table.contextual
        if contextual:
            self.conditions.append(f"within {self._header(node)}")
        self.handlers += handler
        for child in node.named_children:
            self.visit(child, depth=depth + 1)
        self.handlers -= handler
        if contextual:
            self.conditions.pop()
