"""The state graph of a Python workflow, read off its own source.

The YAML engine's `dot` reads a declared `next:`. There is nothing to read here — the
transition is an expression a state *returns* — so the graph is derived instead: each
state's body is parsed and every `Continue` / `Await` / `Done` constructor found in it
is read for its target.

Two properties follow, and they are why this is static rather than an execution trace.
It is an **over-approximation**: an edge is reported for a branch that may never be
taken, because nothing here evaluates a condition. And it **cannot drift** from the
code, the way a declared `next=[...]` list can. Enumerating paths by *running* the
states was the alternative and it buys neither — a state body branching on `self.ctx`
would have to be fed fabricated values, and would raise on the first comparison against
a `--dry-run` stand-in. Running the machine (`--dry-run`) and reading it (`dot`) are
therefore two different tools here, not one: execution covers the path it takes, this
covers every path.

Cost is `sum over states of (transitions in that state)` — linear in states, because a
transition is data the driver reads, so cross-state combinations are never explored.

Live names only: the walk is over `cls.state_names()`, so an alias never appears as a
second state.
"""
from __future__ import annotations

import ast
import inspect
import sys
import textwrap
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from workhorse.pyflow.errors import WorkflowDefinitionError
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.workflow import StateSpec, Workflow

#: Where each transition constructor keeps its target, as a positional index.
#: `Continue(result, next, /, *args)` and `Await(path, questions, next, /, *args)` —
#: both positional-only, so a keyword never carries the target.
_TARGET_ARG = {"Continue": 1, "Await": 2}


@dataclass(frozen=True)
class Edge:
    """One transition a state can return."""

    #: The state this goes to. Empty on a `done` edge: there is nothing to go to.
    target: str
    #: "continue", "await" or "done" — an await edge suspends for an operator first;
    #: a done edge leaves the machine. `Done` is a transition, not a property of the
    #: state that returns it: a state may end on one branch and continue on another.
    kind: str = "continue"
    #: The parameters this transition binds on the target, for the edge label.
    params: tuple[str, ...] = ()
    #: The literal string chained on as `.because("…")`, else empty. An f-string or a
    #: variable there is unknowable statically and leaves the edge unlabelled.
    reason: str = ""
    #: The target expression was not a plain `self.<state>` (a variable, a lookup).
    #: The edge is real; where it goes is only known at runtime.
    dynamic: bool = False
    #: The target resolved to a `self.<name>` that is not a state — an author error
    #: the driver would only report on the transition that made it.
    dangling: bool = False


@dataclass(frozen=True)
class Step:
    """One thing a state's body runs: a blueprint node call or an agent turn.

    Kept in source order so a diagram can draw the state as the chain it is. The
    summary is what the author already wrote about it — the first line of the node's
    docstring, or the title of the prompt — and is empty when there is none to read.
    """

    #: "call" or "agent".
    kind: str
    #: The node's name for a call; the literal prompt path for an agent turn. Only
    #: constants: an f-string prompt is unknowable here, and guessing one would fail a
    #: dry run over nothing.
    name: str
    summary: str = ""

    @property
    def file(self) -> str:
        """The prompt's file name, or the node name — what a label shows."""
        return self.name.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class StateNode:
    """One state, and what its body was seen to do."""

    name: str
    edges: tuple[Edge, ...] = ()
    #: Every `self.call(...)` and literal `self.agent(...)` the body reaches, in source
    #: order, each once.
    steps: tuple[Step, ...] = ()
    #: Sub-workflows reached through `self.handoff(...)`.
    handoffs: tuple[str, ...] = ()
    #: `inspect.getsource` could not read this state — nothing below it is known.
    opaque: bool = False

    @property
    def terminal(self) -> bool:
        """The body constructs `Done(...)` somewhere — the machine *can* end here.

        Derived from the edges rather than stored, so it cannot disagree with them.
        """
        return any(edge.kind == "done" for edge in self.edges)

    @property
    def calls(self) -> tuple[str, ...]:
        """Blueprint nodes reached through `self.call(...)`, in source order."""
        return tuple(step.name for step in self.steps if step.kind == "call")

    @property
    def prompts(self) -> tuple[str, ...]:
        """Literal prompt paths passed to `self.agent(...)`, in source order."""
        return tuple(step.name for step in self.steps if step.kind == "agent")


@dataclass(frozen=True)
class FlowGraph:
    """One `Workflow` subclass as a machine."""

    workflow: str
    #: Every flow name the registry maps to this class, e.g. `("default", "coder")`.
    names: tuple[str, ...] = ()
    start: str = ""
    states: tuple[StateNode, ...] = field(default=())

    @property
    def label(self) -> str:
        """What `dot` titles this flow: its flow names, else the class name."""
        return "/".join(self.names) or self.workflow

    def state(self, name: str) -> StateNode | None:
        for node in self.states:
            if node.name == name:
                return node
        return None

    def reachable(self) -> set[str]:
        """States reachable from `start` over statically readable edges.

        A dynamic edge is a dead end here on purpose: it is precisely the case where
        the target is unknown, so counting it as reaching everything would make the
        unreachable check useless, and counting it as reaching nothing is the honest
        over-report the caller is told about.
        """
        seen: set[str] = set()
        queue = deque([self.start])
        while queue:
            name = queue.popleft()
            if name in seen:
                continue
            node = self.state(name)
            if node is None:
                continue
            seen.add(name)
            queue.extend(
                edge.target
                for edge in node.edges
                if edge.kind != "done" and not edge.dynamic and not edge.dangling
            )
        return seen

    def unreachable(self) -> tuple[str, ...]:
        reached = self.reachable()
        return tuple(node.name for node in self.states if node.name not in reached)

    def prompts(self) -> tuple[tuple[str, str], ...]:
        """(state, prompt path) for every literal `self.agent(...)` in the flow."""
        return tuple(
            (node.name, prompt) for node in self.states for prompt in node.prompts
        )


# ── Reading a class ─────────────────────────────────────────────────────────────


def state_graph(
    cls: type[Workflow], names: Iterable[str] = (), workflow_dir: Path | None = None
) -> FlowGraph:
    """Read `cls` into a `FlowGraph`. Live state names only, sorted for stable output.

    `workflow_dir` is where relative prompt paths resolve, so each agent step can carry
    its prompt's title; without it the step is still read, with no summary.
    """
    # Looked up once and filtered on the spec itself: reading `cls.states` twice — once
    # to test, once to pass — is what let a `None` through to `_read_state`.
    specs = (cls.states.get(name) for name in sorted(cls.state_names()))
    states = tuple(_read_state(cls, spec, workflow_dir) for spec in specs if spec is not None)
    return FlowGraph(
        workflow=cls.__name__,
        names=tuple(names),
        start=cls.start_state,
        states=states,
    )


def registry_graphs(registry: Registry) -> list[FlowGraph]:
    """One graph per distinct workflow class in `registry`, entry flow first.

    Keyed by class rather than by flow name because `main(Coder)` registers the entry
    under `default` as well as its own name, and rendering that class twice would show
    one machine as two.
    """
    by_class: dict[type[Workflow], list[str]] = {}
    if registry.entry is not None:
        by_class[registry.entry] = []
    for flow_name, cls in registry.flows.items():
        by_class.setdefault(cls, []).append(flow_name)
    try:
        directory: Path | None = registry.directory()
    except WorkflowDefinitionError:
        # A class declared at top level — a test file, a REPL — has no package
        # directory, and the graph is still readable; its agent steps go untitled.
        directory = None
    return [state_graph(cls, names, directory) for cls, names in by_class.items()]


@dataclass
class _Found:
    """What a scan has seen so far. Mutable, because the scan recurses."""

    edges: list[Edge] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    handoffs: list[str] = field(default_factory=list)
    #: Transition calls already read as the inner half of a `.because(...)`, so the
    #: walk does not emit them a second time when it reaches them on their own.
    consumed: set[int] = field(default_factory=set)


def _read_state(cls: type[Workflow], spec: StateSpec, workflow_dir: Path | None) -> StateNode:
    tree = _source_tree(spec.fn)
    if tree is None:
        return StateNode(name=spec.name, opaque=True)

    found = _Found()
    _scan(cls, tree, found, {spec.name}, workflow_dir)
    return StateNode(
        name=spec.name,
        edges=tuple(dict.fromkeys(found.edges)),
        steps=tuple(dict.fromkeys(found.steps)),
        handoffs=tuple(dict.fromkeys(found.handoffs)),
    )


def _scan(
    cls: type[Workflow],
    tree: ast.AST,
    found: _Found,
    seen: set[str],
    workflow_dir: Path | None = None,
) -> None:
    """Record every seam this body reaches, following its own private helpers.

    A state that factors its turn into a `_record()` or its node call into a
    `_publish()` is doing what the design sanctions — private methods are not states
    — but reading only the state's literal body would then lose the prompt from the
    diagram *and* from the dry run's prompt-exists check, which is the opposite of
    what factoring should cost. So `self._helper(...)` is followed and merged in.
    Attributed to the state, not to the helper: the helper is not a node.

    `seen` bounds it. A helper calling itself, or two calling each other, would
    otherwise recurse forever over a workflow that runs perfectly well.
    """
    # `ast.walk` rather than a visitor: a transition inside a nested function or a
    # comprehension still counts, and over-reporting is the contract here anyway.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or id(node) in found.consumed:
            continue
        # `Continue(...).because("…")`: the outer call is the reason, the inner call
        # is the transition. `ast.walk` is breadth-first, so the outer one comes first.
        inner, reason = _unwrap_because(node)
        if inner is not None:
            found.consumed.add(id(inner))
            node = inner
        dotted = _dotted(node.func)
        if dotted is None:
            continue
        tail = dotted.rsplit(".", 1)[-1]
        if tail == "Done":
            found.edges.append(Edge(target="", kind="done", reason=reason))
        elif tail in _TARGET_ARG:
            found.edges.append(_read_edge(cls, tail, node, reason))
        elif dotted == "self.call":
            ident = _first_ident(node)
            if ident:
                found.steps.append(Step("call", ident, _doc_summary(cls, node.args[0])))
        elif dotted == "self.agent":
            prompt = _first_literal(node)
            if prompt:
                found.steps.append(Step("agent", prompt, _prompt_title(prompt, workflow_dir)))
        elif dotted == "self.handoff":
            _append(found.handoffs, _first_ident(node))
        elif dotted == f"self.{tail}" and tail.startswith("_") and tail not in seen:
            seen.add(tail)
            helper = _source_tree(getattr(cls, tail, None))
            if helper is not None:
                _scan(cls, helper, found, seen, workflow_dir)


def _unwrap_because(call: ast.Call) -> tuple[ast.Call | None, str]:
    """`(inner transition call, reason)` when `call` is `<transition>.because(...)`.

    The reason is the literal string argument, or empty when it is anything else — an
    f-string built from the state's values is a fine reason at runtime and no label
    here. `(None, "")` when `call` is not a `.because(...)` on a transition call.
    """
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr == "because"):
        return None, ""
    inner = func.value
    if not isinstance(inner, ast.Call):
        return None, ""
    dotted = _dotted(inner.func)
    if dotted is None or dotted.rsplit(".", 1)[-1] not in ("Continue", "Await", "Done"):
        return None, ""
    return inner, _first_literal(call) or ""


def _read_edge(cls: type[Workflow], ctor: str, call: ast.Call, reason: str = "") -> Edge:
    index = _TARGET_ARG[ctor]
    kind = "await" if ctor == "Await" else "continue"
    expr = call.args[index] if len(call.args) > index else None

    if isinstance(expr, ast.Attribute) and _dotted(expr.value) == "self":
        target = expr.attr
        return Edge(
            target=target,
            kind=kind,
            params=_param_names(cls, target, call, index),
            reason=reason,
            dangling=target not in cls.state_names(),
        )
    return Edge(target=_unparse(expr), kind=kind, reason=reason, dynamic=True)


def _param_names(
    cls: type[Workflow], target: str, call: ast.Call, index: int
) -> tuple[str, ...]:
    """The parameter names this transition binds, positional ones resolved by name.

    Positional arguments carry no name at the callsite, so they are read off the
    target's own signature — the same binding the driver does at runtime, done here
    only to label an edge.
    """
    keywords = [kw.arg for kw in call.keywords if kw.arg]
    extra = max(len(call.args) - index - 1, 0)
    positional: list[str] = []
    spec = cls.states.get(target)
    if spec is not None and extra:
        try:
            names = list(inspect.signature(spec.fn).parameters)[1:]  # drop self
        except (TypeError, ValueError):
            names = []
        positional = names[:extra]
    return tuple(positional + keywords)


# ── AST helpers ─────────────────────────────────────────────────────────────────


def _source_tree(fn: object) -> ast.AST | None:
    """Parse a state method's own source, or None when it cannot be read.

    A method defined in a REPL or an `exec` has no source file; that is a hole in the
    analysis rather than a crash, and the caller reports it as one. So is a non-callable:
    one caller looks its argument up with `getattr(cls, tail, None)`, which answers with
    whatever is there — a class attribute, or nothing at all.
    """
    if not callable(fn):
        return None
    try:
        source = textwrap.dedent(inspect.getsource(fn))
    except (OSError, TypeError):
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def _dotted(node: ast.expr) -> str | None:
    """`self.call` for an Attribute chain of plain names, else None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _first_ident(call: ast.Call) -> str | None:
    """The name of the first positional argument — a node or workflow reference."""
    if not call.args:
        return None
    dotted = _dotted(call.args[0])
    return dotted.rsplit(".", 1)[-1] if dotted else None


def _first_literal(call: ast.Call) -> str | None:
    """The first positional argument when it is a string constant."""
    if call.args and isinstance(call.args[0], ast.Constant):
        value = call.args[0].value
        if isinstance(value, str):
            return value
    return None


def _unparse(expr: ast.expr | None) -> str:
    if expr is None:
        return "?"
    try:
        return ast.unparse(expr)
    except Exception:  # noqa: BLE001 — a label is never worth failing a render over
        return "?"


def _append(items: list[str], value: str | None) -> None:
    if value:
        items.append(value)


def _doc_summary(cls: type[Workflow], ref: ast.expr) -> str:
    """The first line of the docstring of the node `ref` names, else empty.

    The reference is resolved the way the state's own code resolves it: a name in the
    class's module, then attributes off it (`nodes.checkpoint_book`). Anything that
    does not resolve — a local, an import the module aliases oddly — is a blank
    summary, not an error: the step is still on the diagram, just unexplained.
    """
    dotted = _dotted(ref)
    if not dotted:
        return ""
    head, *rest = dotted.split(".")
    module = sys.modules.get(cls.__module__)
    target: object = getattr(module, head, None) if module is not None else None
    for attr in rest:
        target = getattr(target, attr, None)
    if target is None:
        return ""
    doc = inspect.getdoc(target) or ""
    return doc.strip().splitlines()[0].strip() if doc.strip() else ""


def _prompt_title(prompt: str, workflow_dir: Path | None) -> str:
    """The first Markdown heading of the prompt at `prompt`, else empty."""
    path = Path(prompt)
    if not path.is_absolute():
        if workflow_dir is None:
            return ""
        path = workflow_dir / path
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            # A prompt titled "<workflow> — <what it does>" repeats the diagram's own
            # name; the caption keeps the half that says something.
            return title.split(" — ", 1)[-1] if " — " in title else title
    return ""


# ── Preflight ───────────────────────────────────────────────────────────────────


def preflight(graphs: Sequence[FlowGraph], workflow_dir: Path | None = None) -> list[str]:
    """Everything wrong with these machines that a static read can see.

    This is the half of `--dry-run` a type checker cannot do: the filesystem (does the
    prompt exist) and reachability (is this state dead). Argument checking moved to
    `ParamSpec` and the editor long before a run starts.
    """
    problems: list[str] = []
    for graph in graphs:
        where = f"flow '{graph.label}'"
        names = {node.name for node in graph.states}
        if graph.start not in names:
            problems.append(
                f"{where}: start state '{graph.start}' does not exist — "
                f"known states: {', '.join(sorted(names)) or '(none)'}"
            )
        if not any(node.terminal for node in graph.states):
            problems.append(
                f"{where}: no state returns Done(...) — the machine cannot terminate"
            )
        for node in graph.states:
            if node.opaque:
                problems.append(
                    f"{where}: cannot read the source of state '{node.name}' — "
                    "its transitions, prompts and reachability are unchecked"
                )
            for edge in node.edges:
                if edge.dangling:
                    problems.append(
                        f"{where}: state '{node.name}' transitions to "
                        f"'self.{edge.target}', which is not a state"
                    )
        for dead in graph.unreachable():
            problems.append(
                f"{where}: state '{dead}' is unreachable from '{graph.start}'"
            )
        if workflow_dir is not None:
            problems.extend(_missing_prompts(graph, where, workflow_dir))
    return problems


def _missing_prompts(graph: FlowGraph, where: str, workflow_dir: Path) -> list[str]:
    """Prompt paths that do not resolve, the same way `templates.render` resolves them.

    A typo here is the failure that costs most: it surfaces at hour 30 of an
    unattended run, in the one state that was never exercised by hand.
    """
    missing: list[str] = []
    for state, prompt in graph.prompts():
        path = Path(prompt)
        resolved = path if path.is_absolute() else workflow_dir / path
        if not resolved.is_file():
            missing.append(f"{where}: state '{state}' renders '{prompt}', which does not exist")
    return missing


__all__ = [
    "Edge",
    "FlowGraph",
    "StateNode",
    "Step",
    "preflight",
    "registry_graphs",
    "state_graph",
]
