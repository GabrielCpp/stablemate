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
import textwrap
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from workhorse.pyflow.registry import Registry
from workhorse.pyflow.workflow import StateSpec, Workflow

#: Where each transition constructor keeps its target, as a positional index.
#: `Continue(result, next, /, *args)` and `Await(path, questions, next, /, *args)` —
#: both positional-only, so a keyword never carries the target.
_TARGET_ARG = {"Continue": 1, "Await": 2}


@dataclass(frozen=True)
class Edge:
    """One transition a state can return."""

    target: str
    #: "continue" or "await" — an await edge suspends for an operator first.
    kind: str = "continue"
    #: The parameters this transition binds on the target, for the edge label.
    params: tuple[str, ...] = ()
    #: The target expression was not a plain `self.<state>` (a variable, a lookup).
    #: The edge is real; where it goes is only known at runtime.
    dynamic: bool = False
    #: The target resolved to a `self.<name>` that is not a state — an author error
    #: the driver would only report on the transition that made it.
    dangling: bool = False


@dataclass(frozen=True)
class StateNode:
    """One state, and what its body was seen to do."""

    name: str
    edges: tuple[Edge, ...] = ()
    #: The body constructs `Done(...)` somewhere — the machine can end here.
    terminal: bool = False
    #: Blueprint nodes reached through `self.call(...)`, in source order.
    calls: tuple[str, ...] = ()
    #: Literal prompt paths passed to `self.agent(...)`. Only constants: an f-string
    #: prompt is unknowable here, and guessing one would fail a dry run over nothing.
    prompts: tuple[str, ...] = ()
    #: Sub-workflows reached through `self.handoff(...)`.
    handoffs: tuple[str, ...] = ()
    #: `inspect.getsource` could not read this state — nothing below it is known.
    opaque: bool = False


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
                if not edge.dynamic and not edge.dangling
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


def state_graph(cls: type[Workflow], names: Iterable[str] = ()) -> FlowGraph:
    """Read `cls` into a `FlowGraph`. Live state names only, sorted for stable output."""
    # Looked up once and filtered on the spec itself: reading `cls.states` twice — once
    # to test, once to pass — is what let a `None` through to `_read_state`.
    specs = (cls.states.get(name) for name in sorted(cls.state_names()))
    states = tuple(_read_state(cls, spec) for spec in specs if spec is not None)
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
    return [state_graph(cls, names) for cls, names in by_class.items()]


@dataclass
class _Found:
    """What a scan has seen so far. Mutable, because the scan recurses."""

    edges: list[Edge] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    handoffs: list[str] = field(default_factory=list)
    terminal: bool = False


def _read_state(cls: type[Workflow], spec: StateSpec) -> StateNode:
    tree = _source_tree(spec.fn)
    if tree is None:
        return StateNode(name=spec.name, opaque=True)

    found = _Found()
    _scan(cls, tree, found, {spec.name})
    return StateNode(
        name=spec.name,
        edges=tuple(dict.fromkeys(found.edges)),
        terminal=found.terminal,
        calls=tuple(dict.fromkeys(found.calls)),
        prompts=tuple(dict.fromkeys(found.prompts)),
        handoffs=tuple(dict.fromkeys(found.handoffs)),
    )


def _scan(cls: type[Workflow], tree: ast.AST, found: _Found, seen: set[str]) -> None:
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
        if not isinstance(node, ast.Call):
            continue
        dotted = _dotted(node.func)
        if dotted is None:
            continue
        tail = dotted.rsplit(".", 1)[-1]
        if tail == "Done":
            found.terminal = True
        elif tail in _TARGET_ARG:
            found.edges.append(_read_edge(cls, tail, node))
        elif dotted == "self.call":
            _append(found.calls, _first_ident(node))
        elif dotted == "self.agent":
            _append(found.prompts, _first_literal(node))
        elif dotted == "self.handoff":
            _append(found.handoffs, _first_ident(node))
        elif dotted == f"self.{tail}" and tail.startswith("_") and tail not in seen:
            seen.add(tail)
            helper = _source_tree(getattr(cls, tail, None))
            if helper is not None:
                _scan(cls, helper, found, seen)


def _read_edge(cls: type[Workflow], ctor: str, call: ast.Call) -> Edge:
    index = _TARGET_ARG[ctor]
    kind = "await" if ctor == "Await" else "continue"
    expr = call.args[index] if len(call.args) > index else None

    if isinstance(expr, ast.Attribute) and _dotted(expr.value) == "self":
        target = expr.attr
        return Edge(
            target=target,
            kind=kind,
            params=_param_names(cls, target, call, index),
            dangling=target not in cls.state_names(),
        )
    return Edge(target=_unparse(expr), kind=kind, dynamic=True)


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
    "preflight",
    "registry_graphs",
    "state_graph",
]
