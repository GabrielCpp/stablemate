"""The syntax-walking base the language evidence collectors share."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from tree_sitter import Node

from ostler import syntax
from ostler.behavior_models import BehaviorEvidence, SourceContext


def tokens(node: Node, source_bytes: bytes, skip: frozenset[str]) -> list[tuple[str, str]]:
    """Keep syntax and literal bytes, not comments, offsets or inter-token whitespace."""
    result: list[tuple[str, str]] = []
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type in skip or current.type == ";":
            continue
        if not current.children:
            result.append((current.type, source_bytes[current.start_byte:current.end_byte].decode()))
        else:
            stack.extend(reversed(current.children))
    return result


class LexicalEvidence:
    """Retain lexical branch and declaration enclosure for each syntax observation."""

    skip: frozenset[str] = frozenset({"comment"})
    framework: str = ""

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
        """The bytes *node* spans, decoded."""
        if node is None:
            return ""
        start, end = node.start_byte, node.end_byte
        if start < 0 or end > len(self.source_bytes) or start > end:
            return ""
        return self.source_bytes[start:end].decode()

    def _field(self, node: Node, field: str) -> str:
        """``node``'s named field child, decoded — same role as ``syntax.field_text``."""
        return self._slice(node.child_by_field_name(field))

    def _extra(self, symbol: str) -> dict[str, Any]:
        return {}

    def emit(self, node: Node, kind: str, *, text: str = "", snippet: str = "", framework: str = "") -> None:
        symbol = ".".join(self.symbols) or "<module>"
        identity = json.dumps((self.path, symbol, kind, tokens(node, self.source_bytes, self.skip)), ensure_ascii=True)
        self.occurrences[identity] += 1
        ident = hashlib.sha256(f"{identity}\0{self.occurrences[identity]}".encode()).hexdigest()
        sliced = self._slice(node)
        self.candidates.append(BehaviorEvidence.model_validate({
            "id": f"evidence:{ident}", "path": self.path, "symbol": symbol,
            "start_line": node.start_point.row + 1, "end_line": node.end_point.row + 1,
            "start_column": node.start_point.column, "end_column": node.end_point.column,
            "kind": kind, "text": text or sliced, "snippet": snippet or sliced,
            "conditions": tuple(self.conditions), "source_digest": self.digest,
            "framework": framework or self.framework, **self._extra(symbol),
        }))

    def context(self, node: Node) -> None:
        start, end = syntax.lines_of(node)
        self.source_context.append(SourceContext(
            path=self.path, symbol=".".join(self.symbols) or "<module>", start_line=start, end_line=end,
            text="".join(self.source.splitlines(keepends=True)[start - 1:end]), source_digest=self.digest,
        ))
