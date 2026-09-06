"""Extract lexical Python behavior candidates without executing or resolving source."""
from __future__ import annotations

import ast
import hashlib
from collections import Counter

from ostler.behavior_models import BehaviorEvidence, SourceContext


class PythonEvidence(ast.NodeVisitor):
    """Keep symbol and lexical-block context while visiting every source branch."""

    def __init__(self, path: str, source: str, digest: str) -> None:
        self.path = path
        self.source = source
        self.digest = digest
        self.symbols: list[str] = []
        self.scopes: list[str] = []
        self.conditions: list[str] = []
        self.candidates: list[BehaviorEvidence] = []
        self.occurrences: Counter[str] = Counter()
        self.source_context: list[SourceContext] = []
        self.limitations: list[str] = []
        self.module_statement: ast.stmt | None = None

    def excerpt(self, start: int, end: int, symbol: str) -> None:
        if end < start:
            return
        context = SourceContext(path=self.path, symbol=symbol, start_line=start, end_line=end,
                                text="".join(self.source.splitlines(keepends=True)[start - 1:end]),
                                source_digest=self.digest)
        if context not in self.source_context:
            self.source_context.append(context)

    def visit_Module(self, node: ast.Module) -> None:
        for statement in node.body:
            self.module_statement = statement
            self.visit(statement)
        # Include same-file bindings referenced by the excerpts, transitively. This is
        # lexical retrieval only, not name resolution or a data-flow verdict.
        bindings = [statement for statement in node.body if isinstance(statement, (ast.Assign, ast.AnnAssign))]
        while True:
            names = {part.id for part in ast.walk(node) if isinstance(part, ast.Name)
                     and isinstance(part.ctx, ast.Load)
                     and any(context.start_line <= part.lineno <= context.end_line for context in self.source_context)}
            selected = [statement for statement in bindings
                        if any(isinstance(part, ast.Name) and isinstance(part.ctx, ast.Store) and part.id in names
                               for part in ast.walk(statement))]
            if not selected:
                break
            for statement in selected:
                self.excerpt(statement.lineno, statement.end_lineno or statement.lineno, "<module>")
                bindings.remove(statement)
        self.source_context.sort(key=lambda context: (context.start_line, context.end_line, context.symbol))

    def emit(self, node: ast.expr | ast.stmt, kind: str, *, text: str = "", framework: str = "python") -> None:
        symbol = ".".join(self.symbols) or "<module>"
        identity = f"{self.path}\0{symbol}\0{kind}\0{ast.dump(node)}\0{text}"
        self.occurrences[identity] += 1
        ident = hashlib.sha256(f"{identity}\0{self.occurrences[identity]}".encode()).hexdigest()
        snippet = ast.get_source_segment(self.source, node) or ast.unparse(node)
        self.candidates.append(BehaviorEvidence.model_validate({
            "id": f"evidence:{ident}", "path": self.path, "symbol": symbol,
            "start_line": node.lineno, "end_line": node.end_lineno or node.lineno,
            "start_column": node.col_offset, "end_column": node.end_col_offset or 0,
            "kind": kind, "text": text or ast.unparse(node), "snippet": snippet,
            "conditions": tuple(self.conditions), "source_digest": self.digest, "framework": framework,
        }))
        if not self.symbols and self.module_statement is not None:
            statement = self.module_statement
            self.excerpt(statement.lineno, statement.end_lineno or statement.lineno, "<module>")

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        before = len(self.candidates)
        enclosing_function = "function" in self.scopes
        self.symbols.append(node.name)
        self.scopes.append("function")
        for decorator in node.decorator_list:
            route = (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                     and decorator.func.attr in {"get", "post", "put", "patch", "delete", "route", "head", "options", "websocket"})
            self.emit(decorator, "route" if route else "decorator",
                      framework="unresolved route-like decorator" if route else "python decorator")
        positional = [*node.args.posonlyargs, *node.args.args]
        for arg, default in zip(positional[len(positional) - len(node.args.defaults):], node.args.defaults):
            self.emit(default, "function_default", text=f"{arg.arg}={ast.unparse(default)}")
        for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
            if default is not None:
                self.emit(default, "function_default", text=f"{arg.arg}={ast.unparse(default)}")
        for statement in node.body:
            self.visit(statement)
        if len(self.candidates) == before:
            self.limitations.append(f"{self.path}::{'.'.join(self.symbols)}: no candidates extracted; function behavior is not audited.")
        elif not enclosing_function:
            self.excerpt(min([node.lineno, *(item.lineno for item in node.decorator_list)]),
                         node.end_lineno or node.lineno, ".".join(self.symbols))
        self.scopes.pop()
        self.symbols.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        before = len(self.candidates)
        enclosing_function = "function" in self.scopes
        self.symbols.append(node.name)
        self.scopes.append("class")
        for decorator in node.decorator_list:
            self.emit(decorator, "decorator", framework="python decorator")
        for statement in node.body:
            self.visit(statement)
        if len(self.candidates) > before and not enclosing_function:
            # Class declarations retain fields and prose, not every method body.
            start = min([node.lineno, *(item.lineno for item in node.decorator_list)])
            for statement in node.body:
                if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    end = min([statement.lineno, *(item.lineno for item in statement.decorator_list)]) - 1
                    self.excerpt(start, end, ".".join(self.symbols))
                    start = (statement.end_lineno or statement.lineno) + 1
            self.excerpt(start, node.end_lineno or node.lineno, ".".join(self.symbols))
        self.scopes.pop()
        self.symbols.pop()

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self.scopes and self.scopes[-1] == "class":
            self.emit(node, "schema_field", framework="annotated class field; schema framework unresolved")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
            self.emit(node, "argparse_option", framework="unresolved argparse-like call")
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        self.emit(node, "raise")
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        self.emit(node, "return")
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        for label, body in ((f"if {ast.unparse(node.test)}", node.body),
                            (f"else of ({ast.unparse(node.test)})", node.orelse)):
            self.conditions.append(label)
            for statement in body:
                self.visit(statement)
            self.conditions.pop()

    def generic_visit(self, node: ast.AST) -> None:
        # Non-if control flow is retained as lexical context, never a reachability claim.
        contextual = isinstance(node, (ast.For, ast.AsyncFor, ast.While, ast.Try, ast.TryStar,
                                       ast.ExceptHandler, ast.With, ast.AsyncWith, ast.Match, ast.match_case))
        if contextual:
            self.conditions.append(f"within {type(node).__name__}: {ast.unparse(node)}")
        super().generic_visit(node)
        if contextual:
            self.conditions.pop()
