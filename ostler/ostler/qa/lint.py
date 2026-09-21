"""`ostler qa lint` — the static gate a `qa_plan.py` must pass before it may run on the host."""

from __future__ import annotations

import ast
from pathlib import Path

from ostler.qa.outcome import QaOutcome

ALLOWED_IMPORT_MODULES = frozenset({
    "collections",
    "dataclasses",
    "typing",
    "itertools",
    "re",
    "json",
    "datetime",
    "enum",
    "textwrap",
    "hashlib",
    "ostler",
    "ostler.qa",
    "ostler_qa",
})

ALLOWED_BUILTIN_CALLS = frozenset({
    "len", "range", "str", "int", "float", "bool", "dict", "list", "tuple", "set",
    "frozenset", "enumerate", "zip", "map", "filter", "sorted", "reversed", "min", "max",
    "sum", "abs", "round", "isinstance", "print", "format",
})

ALLOWED_NODE_TYPES = frozenset({
    ast.Module,
    ast.Import, ast.ImportFrom, ast.alias,
    ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.arguments, ast.arg,
    ast.Return, ast.Pass, ast.Break, ast.Continue,
    ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr,
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.TryStar, ast.ExceptHandler,
    ast.With, ast.AsyncWith, ast.withitem,
    ast.Expr,
    ast.Call, ast.keyword, ast.Attribute, ast.Subscript, ast.Slice, ast.Starred,
    ast.Name, ast.Load, ast.Store, ast.Del,
    ast.Constant, ast.JoinedStr, ast.FormattedValue,
    ast.List, ast.Tuple, ast.Set, ast.Dict,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension,
    ast.BoolOp, ast.And, ast.Or,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.UnaryOp, ast.Not, ast.UAdd, ast.USub, ast.Invert,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot,
    ast.In, ast.NotIn,
    ast.IfExp,
    ast.Lambda,
})


class PlanLintVisitor(ast.NodeVisitor):
    """Walks a `qa_plan.py`'s AST and collects every construct outside the allowlist."""

    def __init__(self) -> None:
        self.problems: list[str] = []

    def generic_visit(self, node: ast.AST) -> None:
        if type(node) not in ALLOWED_NODE_TYPES:
            self.problems.append(
                f"line {getattr(node, 'lineno', '?')}: "
                f"`{type(node).__name__}` is not an allowed construct in a qa_plan.py"
            )
            return
        super().generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_module(alias.name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            self.problems.append(
                f"line {node.lineno}: relative imports are not allowed in a qa_plan.py"
            )
        elif node.module is not None:
            self._check_module(node.module, node.lineno)
        self.generic_visit(node)

    def _check_module(self, module: str, lineno: int) -> None:
        parts = module.split(".")
        top = parts[0]
        if top not in ALLOWED_IMPORT_MODULES and module not in ALLOWED_IMPORT_MODULES:
            allowed = ", ".join(sorted(ALLOWED_IMPORT_MODULES))
            self.problems.append(
                f"line {lineno}: `import {module}` is not allowed — the allowed modules are: "
                f"{allowed}"
            )

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__"):
            self.problems.append(
                f"line {node.lineno}: `.{node.attr}` — dunder attribute access is never "
                f"allowed in a qa_plan.py"
            )
            return
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        if isinstance(node.value, ast.Call) and (verb := _settle_verb(node.value)) is not None:
            self.problems.append(
                f"line {node.lineno}: `{verb}(...)` stands alone as a statement — a settle "
                f"that times out raises, and a raise is not a verdict: the trial ends in a "
                f"traceback and the obligation keeps whatever the earlier checks gave it. "
                f"Settle, read, then return evidence: `qa.eventually(\"...\", "
                f"locator.is_visible, covers=[...])` polls the same condition and records "
                f"the same timeout as a failed check. `qa.eventually` needs a callable to "
                f"re-sample — a lambda (`lambda: page.text(\"#badge\")`), a bound method "
                f"or a named nested function"
            )
            return
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if (
            isinstance(node.ctx, ast.Load)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            self.problems.append(
                f"line {node.lineno}: this plan reads observed data by subscript — a key "
                f"the product spells differently raises instead of failing a check, which "
                f"kills the scenario and leaves every obligation it covers `unproven` "
                f"rather than red; read it with `qa.field(obj, \"a.b\")`"
            )
            return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr in _FILESYSTEM_METHODS:
            self.problems.append(
                f"line {node.lineno}: `.{node.func.attr}(...)` touches the filesystem from "
                f"plan code — read and write through a tool (`qa.tool(...)`), and keep "
                f"evidence in `qa.artifact(...)`"
            )
            return
        if isinstance(node.func, ast.Name) and node.func.id not in ALLOWED_BUILTIN_CALLS:
            if node.func.id in _DANGEROUS_BUILTINS:
                self.problems.append(
                    f"line {node.lineno}: `{node.func.id}(...)` is not allowed in a "
                    f"qa_plan.py"
                )
                return
        self.generic_visit(node)


_FILESYSTEM_METHODS = frozenset({
    "read_text", "read_bytes", "write_text", "write_bytes",
    "unlink", "rmdir", "mkdir", "touch", "chmod", "lchmod",
    "symlink_to", "hardlink_to", "iterdir", "glob", "rglob", "walk",
})


_SETTLE_METHODS = frozenset({
    "wait_for", "wait_for_selector", "wait_for_url", "wait_for_load_state",
    "wait_for_timeout", "wait_for_event", "wait_for_function",
})


def _settle_verb(call: ast.Call) -> str | None:
    """Name the settle verb a call statement is built on, or `None` if it is not one."""
    if isinstance(call.func, ast.Attribute) and call.func.attr in _SETTLE_METHODS:
        return call.func.attr
    inner: ast.expr = call.func
    while isinstance(inner, ast.Attribute):
        inner = inner.value
    if isinstance(inner, ast.Call):
        inner = inner.func
    if isinstance(inner, ast.Name) and inner.id == "expect":
        return "expect"
    return None


_DANGEROUS_BUILTINS = frozenset({
    "eval", "exec", "compile", "__import__", "open", "getattr", "setattr", "delattr",
    "vars", "globals", "locals", "input",
})


def lint_source(source: str, *, filename: str = "<qa_plan.py>") -> list[str]:
    """Lint already-read plan source."""
    try:
        tree = ast.parse(source, filename=filename, mode="exec")
    except SyntaxError as exc:
        return [f"line {exc.lineno or '?'}: {exc.msg}"]
    visitor = PlanLintVisitor()
    visitor.visit(tree)
    return visitor.problems


def cmd_lint(plan_file: Path, *, root: Path | None = None) -> QaOutcome:
    """Lint a `qa_plan.py` against the AST allowlist without importing or executing it."""
    root = (root or Path.cwd()).resolve()
    resolved_plan = plan_file if plan_file.is_absolute() else root / plan_file
    if not resolved_plan.is_file():
        return QaOutcome(
            ok=False,
            message=f"plan file not found: {resolved_plan}",
            status="invalid",
        )
    source = resolved_plan.read_text(encoding="utf-8")
    problems = lint_source(source, filename=str(resolved_plan))
    if problems:
        msg = "Plan lint failed:\n" + "\n".join(f"  - {p}" for p in problems)
        return QaOutcome(
            ok=False,
            message=msg,
            data={"problems": problems},
            status="invalid",
        )
    return QaOutcome(ok=True, message="Plan lint passed.", data={})
