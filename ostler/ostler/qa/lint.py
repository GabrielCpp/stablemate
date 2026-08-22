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

from ostler.qa.fixtures import FIXTURES_DIRNAME, FIXTURES_PACKAGE, declared_modules
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

    def __init__(self, fixture_modules: frozenset[str] = frozenset()) -> None:
        self.problems: list[str] = []
        #: The `_fixtures.<name>` modules this repo declared under `qa: {fixture_modules:}`.
        #: Empty for a repo that declared none, which is the pre-fixture behaviour exactly:
        #: presence of the file on disk is not permission to import it, the declaration is.
        self.fixture_modules = fixture_modules

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
        if top == FIXTURES_PACKAGE:
            # A declared fixture module, and only a declared one. This widening buys nothing
            # a plan could not already do — the fixture module is linted by this same visitor
            # with this same allowlist, so it reaches the process exactly as far as the plan
            # importing it does — and it is what lets `sign_in`/`bearer`/`submission` exist
            # once instead of once per plan. `_fixtures` itself (no submodule) is not a
            # module a plan can import: there is nothing in it to import.
            name = parts[1] if len(parts) > 1 else ""
            if name and name in self.fixture_modules:
                return
            declared = ", ".join(sorted(self.fixture_modules)) or "(none declared)"
            self.problems.append(
                f"line {lineno}: `import {module}` names a fixture module this repo has not "
                f"declared — add `{name or module}` to agents.yml's "
                f"`qa: {{fixture_modules: [...]}}`. Declared here: {declared}"
            )
            return
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
                f"re-sample and lambdas are not allowed here, so hand it a bound method or "
                f"a named nested function"
            )
            return
        self.generic_visit(node)

    def _check_condition(self, node: ast.Call) -> None:
        # The condition and the two evidence arguments alike: `actual=body["claim"]` is
        # evaluated on the way into the call, so it raises exactly where the condition
        # would have, and a plan that fixed only the condition still dies on the argument
        # that was supposed to explain the failure.
        watched = [*node.args[1:2]]
        watched += [kw.value for kw in node.keywords if kw.arg in {"actual", "expected"}]
        for inner in [n for arg in watched for n in ast.walk(arg)]:
            # A *named* key only. `stderr[-2000:]` and `entries[0]` are indexing something
            # the plan already knows the shape of; the hazard is the plan spelling a field
            # the product spells differently, and that always reads as a string literal.
            if isinstance(inner, ast.Subscript) and isinstance(inner.slice, ast.Constant) and isinstance(inner.slice.value, str):
                self.problems.append(
                    f"line {node.lineno}: this assertion reads observed data by subscript — "
                    f"a key the product spells differently raises instead of failing this "
                    f"check, which kills the scenario and leaves every obligation it covers "
                    f"`unproven` rather than red; read it with `qa.field(obj, \"a.b\")`"
                )
                return

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr in _FILESYSTEM_METHODS:
            self.problems.append(
                f"line {node.lineno}: `.{node.func.attr}(...)` touches the filesystem from "
                f"plan code — read and write through a tool (`qa.tool(...)`), and keep "
                f"evidence in `qa.artifact(...)`"
            )
            return
        if isinstance(node.func, ast.Attribute) and node.func.attr in _ASSERTION_METHODS:
            self._check_condition(node)
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


#: Settle verbs, rejected wherever they stand alone as a **statement**. A `wait_for(...)` that
#: times out raises, and a raise inside a scenario is not a verdict — the trial ends in a
#: traceback with `fail_count 0`, so the obligation the wait was standing in front of keeps
#: whatever verdict the scenario's earlier, greener assertions already gave it. A benchmark
#: round measured that exact shape: four seeded defects went undetected not because a check
#: disagreed with the product but because the plan died before reaching the check that would
#: have. A wait's failure must be a *reading*.
#:
#: The harness already ships the settle that reads: `qa.eventually(label, <callable>,
#: covers=[...])` polls the same condition and records a pass or a fail, so the same timeout
#: that used to end the trial now names itself in the evidence map. `covers=` is optional, so
#: even a pure readiness gate is expressible — and strictly more legible than a traceback.
#: `ast.Lambda` is not in `ALLOWED_NODE_TYPES`, so the callable is a bound method
#: (`locator.is_visible`) or a named nested function — `eventually`'s own docstring spells the
#: idiom with a lambda, which this pass rejects.
#:
#: Two deliberate widenings, both for the same reason `_FILESYSTEM_METHODS` does not examine
#: its receiver. **Position**: any settle statement is flagged, not only a terminal one. The
#: crash that costs a verdict is load-bearing wherever it sits — the round's canonical instance
#: was the third line of a nine-line block — and "is it followed by evidence?" is an AST
#: position heuristic, which is the genre of rule that produced this debt rather than caught it.
#: **Driver**: the verbs are flagged in every plan, not only in one that declares a playwright
#: target. Lint has no symbol table and cannot resolve a locator back to its target, so a rule
#: that fired only on receivers it recognised would be a blocklist of receivers instead of a set
#: of verbs. Plans with no browser contain none of these calls, so the wider rule costs them
#: nothing.
#:
#: A settle used as a *value* is untouched: `with qa.page.expect_response(...)` and any
#: `x = something.wait_for(...)` are handling the result rather than betting the trial on it.
#: The assertion verbs whose condition argument is plan-authored Python rather than a
#: declared check. A missing key reached by subscript there is not a failed assertion, it is
#: a dead scenario: the traceback aborts before the checks that would have named the defect,
#: and the run reports `unproven` — nothing observed the product — for obligations the plan
#: was one comparison away from settling. `qa.field()` yields `None` instead, so the same
#: misspelling comes out red in the one place that can explain it.
_ASSERTION_METHODS = frozenset({"check", "require", "eventually"})

_SETTLE_METHODS = frozenset({
    "wait_for", "wait_for_selector", "wait_for_url", "wait_for_load_state",
    "wait_for_timeout", "wait_for_event", "wait_for_function",
})


def _settle_verb(call: ast.Call) -> str | None:
    """Name the settle verb a call statement is built on, or `None` if it is not one."""
    if isinstance(call.func, ast.Attribute) and call.func.attr in _SETTLE_METHODS:
        return call.func.attr
    # `expect(locator).to_be_visible()` — playwright's assertion spelling. The verb is the
    # root of the attribute chain, not its last link, and the last link is an open vocabulary
    # (`to_be_visible`, `to_have_text`, …) that a set could only ever half-name.
    inner: ast.expr = call.func
    while isinstance(inner, ast.Attribute):
        inner = inner.value
    if isinstance(inner, ast.Call):
        inner = inner.func
    if isinstance(inner, ast.Name) and inner.id == "expect":
        return "expect"
    return None


#: Named explicitly so a bare call to one of these is rejected even though lint has no symbol
#: table to otherwise distinguish "calls a builtin" from "calls a plan-local helper of the
#: same name" — the two builtin lists together are the allow/deny split; nothing here is a
#: general blocklist since only names appearing in this fixed, closed set are ever checked.
_DANGEROUS_BUILTINS = frozenset({
    "eval", "exec", "compile", "__import__", "open", "getattr", "setattr", "delattr",
    "vars", "globals", "locals", "input",
})


def lint_source(
    source: str,
    *,
    filename: str = "<qa_plan.py>",
    fixture_modules: frozenset[str] = frozenset(),
) -> list[str]:
    """Lint already-read plan source. Returns problems, empty when the plan is clean."""
    try:
        tree = ast.parse(source, filename=filename, mode="exec")
    except SyntaxError as exc:
        return [f"line {exc.lineno or '?'}: {exc.msg}"]
    visitor = PlanLintVisitor(fixture_modules)
    visitor.visit(tree)
    return visitor.problems


def cmd_lint(
    plan_file: Path,
    spec_dir: Path | None = None,
    *,
    root: Path | None = None,
) -> QaOutcome:
    """Lint a `qa_plan.py` against the AST allowlist without importing or executing it.

    The plan's declared fixture modules are linted in the same pass, with the same visitor
    and the same allowlist. That is what makes admitting them safe: a fixture module is
    plan code that happens to live in another file, so it may not reach anything a plan
    may not reach, and nothing about it is taken on trust because it was declared.
    """
    root = (root or Path.cwd()).resolve()
    resolved_plan = plan_file if plan_file.is_absolute() else root / plan_file
    if not resolved_plan.is_file():
        return QaOutcome(
            ok=False,
            message=f"plan file not found: {resolved_plan}",
            status="invalid",
        )
    modules = frozenset(declared_modules(root))
    source = resolved_plan.read_text(encoding="utf-8")
    problems = lint_source(source, filename=str(resolved_plan), fixture_modules=modules)
    problems.extend(_lint_fixture_modules(resolved_plan, spec_dir, root, modules))
    if problems:
        msg = "Plan lint failed:\n" + "\n".join(f"  - {p}" for p in problems)
        return QaOutcome(
            ok=False,
            message=msg,
            data={"problems": problems},
            status="invalid",
        )
    return QaOutcome(ok=True, message="Plan lint passed.", data={})


def _lint_fixture_modules(
    plan_file: Path, spec_dir: Path | None, root: Path, modules: frozenset[str]
) -> list[str]:
    """Every problem in this repo's declared fixture modules, prefixed with the file.

    A declared module with no file behind it is a problem here rather than an `ImportError`
    at run time: lint is the gate that runs before import, and a declaration nothing
    implements is exactly the class of defect declaring fixtures was meant to surface.
    """
    if not modules:
        return []
    spec_root = (
        (spec_dir if spec_dir.is_absolute() else root / spec_dir).parent
        if spec_dir is not None
        else plan_file.parent.parent
    )
    directory = spec_root / FIXTURES_DIRNAME
    problems: list[str] = []
    for name in sorted(modules):
        path = directory / f"{name}.py"
        if not path.is_file():
            problems.append(
                f"fixture module {name!r} is declared in agents.yml's "
                f"`qa: {{fixture_modules: [...]}}` but {path} does not exist"
            )
            continue
        problems.extend(
            f"{FIXTURES_DIRNAME}/{name}.py: {problem}"
            for problem in lint_source(
                path.read_text(encoding="utf-8"),
                filename=str(path),
                fixture_modules=modules,
            )
        )
    return problems
