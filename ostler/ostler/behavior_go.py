"""Go lexical behavior candidates, without type resolution or a native toolchain."""
from __future__ import annotations

from tree_sitter import Node

from ostler import syntax
from ostler.behavior_lexical import LexicalEvidence


MAX_DEPTH = 500


class GoEvidence(LexicalEvidence):
    framework = "go"

    def visit(self, node: Node, depth: int = 0) -> None:
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
            boundary = next((child for child in node.children if child.type in {"{", ":", "block"}), None)
            end = boundary.start_byte if boundary is not None else node.end_byte
            header = self.source_bytes[node.start_byte:end].decode().strip()
            self.conditions.append(f"within {header}")
        for child in node.named_children:
            self.visit(child, depth + 1)
        if contextual:
            self.conditions.pop()
