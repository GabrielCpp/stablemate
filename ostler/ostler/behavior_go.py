"""Go lexical behavior candidates, without type resolution or a native toolchain."""
from __future__ import annotations

import hashlib
import json
from collections import Counter

from tree_sitter import Node

from ostler import syntax
from ostler.behavior_models import BehaviorEvidence, SourceContext


#: Maximum recursion depth the Go visitor will follow into a tree-sitter node subtree.
#:
#: A real Go AST rarely nests past ~30 frames; a generated struct or a deeply chained
#: switch can reach a few hundred. tree-sitter's `Node.text` is a C-extension property
#: that has segfaulted inside a recursive visit when the AST carries a malformed
#: subtree (see history: `bd8d0fd1` for the 0.26.0 pin, `1bea8d97` for the packet-budget
#: shape; the new path is the same fault class). The cap keeps Python's own stack
#: inside its default recursion limit for very large files; the *real* answer is
#: `_slice` below, which replaces every `syntax.text_of` call with a byte-range read
#: off `self.source_bytes` so the C-extension call never happens.
MAX_DEPTH = 500


def _tokens(node: Node, source_bytes: bytes, skip: frozenset[str] = frozenset({"comment", ";"})) -> list[tuple[str, str]]:
    """Keep syntax and literal bytes, not comments, offsets or inter-token whitespace."""
    result: list[tuple[str, str]] = []
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type in skip:
            continue
        if not current.children:
            result.append((current.type, source_bytes[current.start_byte:current.end_byte].decode()))
        else:
            stack.extend(reversed(current.children))
    return result


class GoEvidence:
    """Retain lexical branch and declaration enclosure for each syntax observation."""

    def __init__(self, path: str, source: str, digest: str) -> None:
        self.path = path
        self.source = source
        self.source_bytes = source.encode()
        self.digest = digest
        self.symbols: list[str] = []
        self.conditions: list[str] = []
        self.candidates: list[BehaviorEvidence] = []
        self.source_context: list[SourceContext] = []
        self.occurrences: Counter[str] = Counter()
        self.literals: Counter[str] = Counter()

    def _slice(self, node: Node | None) -> str:
        """The bytes *node* spans, decoded. Always returns; never calls `node.text`.

        This is the bulletproof replacement for `syntax.text_of` on a node we own
        — the visitor already has the source bytes, and a tree-sitter C call on a
        malformed subtree has segfaulted the interpreter in production. Slicing
        into the same bytes produces the identical string for any well-formed
        node and produces `""` (with the `replace` flag preserved) for an out-of-
        bounds range, which is what every visitor's downstream callers already
        tolerate.
        """
        if node is None:
            return ""
        start, end = node.start_byte, node.end_byte
        if start < 0 or end > len(self.source_bytes) or start > end:
            return ""
        return self.source_bytes[start:end].decode()

    def _field(self, node: Node, field: str) -> str:
        """``node``'s named field child, decoded — same role as ``syntax.field_text``."""
        return self._slice(node.child_by_field_name(field))

    def emit(self, node: Node, kind: str, *, text: str = "", snippet: str = "", framework: str = "go") -> None:
        symbol = ".".join(self.symbols) or "<module>"
        identity = json.dumps((self.path, symbol, kind, _tokens(node, self.source_bytes)), ensure_ascii=True)
        self.occurrences[identity] += 1
        ident = hashlib.sha256(f"{identity}\0{self.occurrences[identity]}".encode()).hexdigest()
        sliced = self._slice(node)
        self.candidates.append(BehaviorEvidence.model_validate({
            "id": f"evidence:{ident}", "path": self.path, "symbol": symbol,
            "start_line": node.start_point.row + 1, "end_line": node.end_point.row + 1,
            "start_column": node.start_point.column, "end_column": node.end_point.column,
            "kind": kind, "text": text or sliced, "snippet": snippet or sliced,
            "conditions": tuple(self.conditions), "source_digest": self.digest, "framework": framework,
        }))

    def context(self, node: Node) -> None:
        start, end = syntax.lines_of(node)
        self.source_context.append(SourceContext(
            path=self.path, symbol=".".join(self.symbols) or "<module>", start_line=start, end_line=end,
            text="".join(self.source.splitlines(keepends=True)[start - 1:end]), source_digest=self.digest,
        ))

    def visit(self, node: Node, depth: int = 0) -> None:
        # See MAX_DEPTH — the cap is the only thing keeping a malformed subtree's C call
        # from tearing the interpreter down. Drop the rest of this branch and keep going:
        # the candidates emitted at the shallower frame still name the right symbol.
        if depth > MAX_DEPTH:
            return
        if node.type == "comment":
            return
        if node.type == "source_file":
            for child in node.named_children:
                before = len(self.candidates)
                self.visit(child, depth + 1)
                if any(item.symbol == "<module>" for item in self.candidates[before:]):
                    self.context(child)
            return
        if node.type in {"function_declaration", "method_declaration", "func_literal"}:
            body = node.child_by_field_name("body")
            if body is None:
                return
            name = self._field(node, "name")
            receiver = node.child_by_field_name("receiver")
            if receiver is not None:
                receiver_type = next((part for part in syntax.walk(receiver) if part.type == "type_identifier"), None)
                name = f"{self._slice(receiver_type)}.{name}"
            if node.type == "func_literal":
                parent = ".".join(self.symbols)
                self.literals[parent] += 1
                name = f"<literal:{self.literals[parent]}>"
            self.symbols.append(name)
            self.context(node)
            # Bodies with only effects still need an audit candidate. Include private
            # declarations too: visibility alone cannot decide externally used behavior.
            # The contract's snippet is its signature, not the body: the body already travels
            # as this declaration's source context, and repeating it doubled a long function
            # inside every packet holding its contract — past the packet budget for one item.
            signature = self.source_bytes[node.start_byte:body.start_byte].decode().strip()
            self.emit(node, "function_contract", text=signature, snippet=signature)
            for child in node.named_children:
                self.visit(child, depth + 1)
            self.symbols.pop()
            return
        if node.type in {"type_spec", "type_alias"}:
            self.symbols.append(self._field(node, "name"))
            before = len(self.candidates)
            for child in node.named_children:
                self.visit(child, depth + 1)
            if len(self.candidates) > before:
                self.context(node)
            self.symbols.pop()
            return
        if node.type == "field_declaration":
            self.emit(node, "schema_field", framework="go struct field; tags and types are syntax, not validated constraints")
        elif node.type == "return_statement":
            self.emit(node, "return")
        elif node.type == "call_expression":
            function = node.child_by_field_name("function")
            if function is not None:
                name = self._field(function, "field")
                if function.type == "identifier" and self._slice(function) == "panic":
                    self.emit(node, "panic", framework="go panic-like call; binding unresolved")
                elif function.type == "selector_expression" and name in {"Handle", "HandleFunc"}:
                    self.emit(node, "route", framework="unresolved net/http-like registration call")
                elif function.type == "selector_expression" and name in {
                    "WriteHeader", "Write", "Error", "NotFound", "Redirect", "ServeContent", "ServeFile",
                }:
                    self.emit(node, "http_response", framework="unresolved net/http-like response call")
        if node.type == "if_statement":
            condition = self._field(node, "condition")
            consequence = node.child_by_field_name("consequence")
            alternative = node.child_by_field_name("alternative")
            for child in node.named_children:
                label = f"if {condition}" if child == consequence else f"else of ({condition})" if child == alternative else ""
                if label:
                    self.conditions.append(label)
                self.visit(child, depth + 1)
                if label:
                    self.conditions.pop()
            return
        contextual = node.type in {
            "expression_switch_statement", "type_switch_statement", "select_statement",
            "expression_case", "type_case", "communication_case", "default_case", "for_statement",
        }
        if contextual:
            # Headers come from the grammar's direct token children, not a text search
            # for braces/colons that could also occur inside literals or expressions.
            boundary = next((child for child in node.children if child.type in {"{", ":", "block"}), None)
            end = boundary.start_byte if boundary is not None else node.end_byte
            header = self.source_bytes[node.start_byte:end].decode().strip()
            self.conditions.append(f"within {header}")
        for child in node.named_children:
            self.visit(child, depth + 1)
        if contextual:
            self.conditions.pop()
