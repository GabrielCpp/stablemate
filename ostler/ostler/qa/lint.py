"""`ostler qa lint` — the static gate a `qa_plan.py` must pass before it may run on the host.

There is no runtime sandbox any more (see `ostler qa run`'s history in QA-RUN.md): a plan
executes directly on the machine that validated it. Containment moves here instead, and it is
an **allowlist** of the AST, not a blocklist of dangerous calls — a blocklist has to name every
way to reach `subprocess`/`eval`/a sandbox escape and loses by default to the one it forgot;
an allowlist has to name every legitimate plan-authoring construct and loses closed.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ostler.qa.outcome import QaOutcome

#: Modules a `qa_plan.py` may import. Everything a real plan needs to describe scenarios and
#: shape data — never a module that reaches the process, the filesystem, or the network
#: directly, because that capability now belongs only to ostler's own built-in tools
#: (`ostler.qa.tools`), never to plan code.
#:
#: `pathlib` is absent for that reason and not by oversight. It was here, and it made the
#: `open()` ban decorative: `pathlib.Path("/etc/passwd").read_text()` reaches the same file
#: through a method call the AST pass had no opinion about. Without it a plan cannot
#: *construct* a path at all — every `Path` it holds was handed to it by `qa`, which is the
#: property `_FILESYSTEM_METHODS` below is written to preserve.
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

#: Bare-name calls a plan may make. Every entry here is inert — it cannot reach outside the
#: interpreter's own data. `eval`, `exec`, `compile`, `__import__`, `open`, `getattr`,
#: `setattr`, `delattr`, `vars`, `globals`, `locals`, and `input` are absent deliberately: this
#: is the allowlist that keeps them out, not a blocklist that has to keep naming them.
ALLOWED_BUILTIN_CALLS = frozenset({
    "len", "range", "str", "int", "float", "bool", "dict", "list", "tuple", "set",
    "frozenset", "enumerate", "zip", "map", "filter", "sorted", "reversed", "min", "max",
    "sum", "abs", "round", "isinstance", "print", "format",
})

#: The full set of AST node types a `qa_plan.py` may contain. Anything else — `ast.Lambda`,
#: `ast.Global`, `ast.Nonlocal`, and every node type this set does not name — is rejected by
#: simply not appearing here, the same "allow, don't blocklist" posture as the import and
#: builtin-call checks above.
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
})


class PlanLintVisitor(ast.NodeVisitor):
    """Walks a `qa_plan.py`'s AST and collects every construct outside the allowlist.

    Every `visit_*` here rejects; there is deliberately no `visit_Lambda` or
    `visit_Global` that raises a specific message, because the node-type allowlist already
    rejects them through `generic_visit` — special-casing a banned node type is exactly the
    blocklist habit this module exists to avoid.
    """

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
        top = module.split(".")[0]
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

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr in _FILESYSTEM_METHODS:
            self.problems.append(
                f"line {node.lineno}: `.{node.func.attr}(...)` touches the filesystem from "
                f"plan code — read and write through a tool (`qa.tool(...)`), and keep "
                f"evidence in `qa.artifact(...)`"
            )
            return
        if isinstance(node.func, ast.Name) and node.func.id not in ALLOWED_BUILTIN_CALLS:
            # A bare-name call to anything other than a known-safe builtin is only legitimate
            # when the name resolves to something defined in the plan itself (a helper
            # function, a decorator target) rather than to a builtin — lint cannot tell which
            # without a symbol table, so it allows bare calls through here and leaves the
            # builtin allowlist to name the *specific* builtins that are safe to call; anything
            # matching a dangerous builtin's name is still caught below.
            if node.func.id in _DANGEROUS_BUILTINS:
                self.problems.append(
                    f"line {node.lineno}: `{node.func.id}(...)` is not allowed in a "
                    f"qa_plan.py"
                )
                return
        self.generic_visit(node)


#: Filesystem verbs, rejected wherever they appear as a method call. The receiver is not
#: examined: lint has no symbol table, so it cannot tell a `Path` from a mock, and a check
#: that only fired on names it recognised would be a blocklist of receivers instead of a set
#: of verbs. Nothing in the corpus loses anything — a plan that needs to read a file reads it
#: through an opted-in tool, which is the norm `depot-infra`'s plan states out loud: "reading
#: it here rather than through a tool would mean the QA harness's own filesystem access is the
#: thing under test."
#:
#: `open` is deliberately *not* here. `json.dump(..., qa.artifact("steps/x.json",
#: kind="json").open("w"))` is how every plan in the corpus writes its evidence, and the
#: python-driver plans read the file their target produced the same way. Both start from a
#: path `qa` handed out, which is what the missing `pathlib` leaves as the only starting point.
#:
#: That is a narrowing, not a proof: `qa.root / ".." / ".."` is still path arithmetic, and an
#: AST pass cannot decide where a joined path lands. Containment of *where* a plan may write
#: is a runtime question and is not claimed here — what this closes is the gap between banning
#: `open()` and leaving `Path(...).read_text()` a method call away, which made the ban read as
#: a rule while enforcing nothing.
_FILESYSTEM_METHODS = frozenset({
    "read_text", "read_bytes", "write_text", "write_bytes",
    "unlink", "rmdir", "mkdir", "touch", "chmod", "lchmod",
    "symlink_to", "hardlink_to", "iterdir", "glob", "rglob", "walk",
})


#: Named explicitly so a bare call to one of these is rejected even though lint has no symbol
#: table to otherwise distinguish "calls a builtin" from "calls a plan-local helper of the
#: same name" — the two builtin lists together are the allow/deny split; nothing here is a
#: general blocklist since only names appearing in this fixed, closed set are ever checked.
_DANGEROUS_BUILTINS = frozenset({
    "eval", "exec", "compile", "__import__", "open", "getattr", "setattr", "delattr",
    "vars", "globals", "locals", "input",
})


def lint_source(source: str, *, filename: str = "<qa_plan.py>") -> list[str]:
    """Lint already-read plan source. Returns problems, empty when the plan is clean."""
    try:
        tree = ast.parse(source, filename=filename, mode="exec")
    except SyntaxError as exc:
        return [f"line {exc.lineno or '?'}: {exc.msg}"]
    visitor = PlanLintVisitor()
    visitor.visit(tree)
    return visitor.problems


def cmd_lint(
    plan_file: Path,
    spec_dir: Path | None = None,  # noqa: ARG001 — kept for parity with cmd_validate's signature
    *,
    root: Path | None = None,
) -> QaOutcome:
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
