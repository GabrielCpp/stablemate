"""The module-level object a workflow's console script points at.

```python
workflow = Registry("coder", package=__package__).add_blueprints(kit.blueprint, blueprint)
main = console_script(workflow.entry_point(Coder))
```

This object *is* the workflow, as far as anything outside the module is concerned.
`main` — *the callable `console_script` returns*, never a call made at import — is what
the distribution binds as its `workhorse-coder` script, and it carries this registry
with it. Nothing resolves a workflow by name: a workflow module must stay importable
without running anything, and the script that imports it already knows which one it got.

`console_script` lives in `workhorse.cli`, not here. A registry that built its own
console callable had to import the CLI, which imports the driver, which imports this
module; the arrow points the other way now.

It is also the run's **composition root**. `registry.nodes` is not bookkeeping: it is
what `self.call` resolves against, so a substituted copy of it (`override(...)`,
`stub_nodes(...)`) is how a test or a dry run replaces a node without patching anyone's
module attributes. Registration travels with the flow class as well as the node
function, which is what lets a handed-off sub-flow bring its own prompts and its own
node table instead of inheriting its caller's.
"""
from __future__ import annotations

import dataclasses
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from workhorse.packaged import package_dir
from workhorse.pyflow.blueprint import Blueprint, NodeSpec
from workhorse.pyflow.errors import WorkflowDefinitionError
from workhorse.pyflow.names import NameIndex
from workhorse.pyflow.workflow import Workflow, state

#: Attribute stamped on a registered flow class. `self.handoff(Surveyor, …)` takes the
#: class, not a name, so the registration has to travel with it — the same idiom as
#: `NODE_ATTR` on a node function, for the same reason.
REGISTRY_ATTR = "__workhorse_registry__"


def registry_of(cls: type[Workflow]) -> "Registry | None":
    """The registry that claimed `cls`, or None if it was never registered.

    None means "inherit the caller's world", which is what keeps a sub-flow declared
    beside its parent working with no ceremony. Read off `cls.__dict__` rather than
    with `getattr`, so a subclass of a registered flow is unclaimed until it registers
    itself instead of quietly answering with its base's registry.
    """
    registry = cls.__dict__.get(REGISTRY_ATTR)
    return registry if isinstance(registry, Registry) else None


class Registry:
    """One workflow distribution's flows, nodes and entry point.

    Named `Registry` rather than `Workflow` because the base class a workflow
    subclasses already owns that name, and the two are different things: the class is
    the state machine, this is what the packaging metadata points at.
    """

    def __init__(self, name: str = "", package: str = "") -> None:
        self.name = name
        #: The importable package whose directory holds this workflow's `prompts/`, as
        #: `Registry("coder", package=__package__)`. Declared rather than inferred
        #: because the registry *is* the composition root: the entry class is free to
        #: live in a sub-package beside its siblings (`coder/main/flow.py`), and a root
        #: taken from that class would land inside one flow and put every other flow's
        #: prompts outside the loader. Empty falls back to the entry class's package,
        #: which is what every workflow relied on before this existed.
        self.package = package
        self.blueprints: list[Blueprint] = []
        self.flows: dict[str, type[Workflow]] = {}
        self.entry: type[Workflow] | None = None
        self.nodes: NameIndex[NodeSpec] = NameIndex("node", owner=f"workflow {name!r}")
        #: Canned agent replies for `--dry-run`, by prompt stem. See `stub_agents`.
        self.agent_stubs: dict[str, Any] = {}

    # --- composition --------------------------------------------------------

    def add_blueprints(self, *blueprints: Blueprint) -> "Registry":
        """Fold node libraries in. Plural because composition is the point: a
        workflow picks up the shared `await_operator` / `commit_all` / `push_branch`
        rather than re-implementing them a fourth time.

        Merging the indexes here is what makes two blueprints claiming one node name
        an import-time error rather than a coin flip at `self.output(...)` time.
        """
        for blueprint in blueprints:
            self.blueprints.append(blueprint)
            self.nodes.merge(blueprint.index)
        return self

    def add_flows(self, **flows: type[Workflow]) -> "Registry":
        """Register sub-flows a caller can name, e.g. `workhorse-coder run qa`."""
        for flow_name, workflow in flows.items():
            if flow_name in self.flows:
                raise WorkflowDefinitionError(
                    f"flow {flow_name!r} is registered twice on workflow {self.name!r}"
                )
            _require_workflow(flow_name, workflow)
            self._claim(workflow)
            self.flows[flow_name] = workflow
        return self

    def stub_agents(self, replies: dict[str, Any]) -> "Registry":
        """Declare what `--dry-run` should get back from each prompt, by stem.

        A value, a dict of the reply model's fields, or a callable taking the render
        args. Declaring these is what turns a dry run from "every branch reads a blank
        field and takes an arbitrary path" into a smoke test of the workflow's own
        happy path — and it is why a fail terminal under `--dry-run` is a real verdict
        for a workflow that declares them and not for one that does not.

        A dict rather than `**kwargs` because prompt stems are hyphenated
        (`check-gate`), which is not an identifier.
        """
        self.agent_stubs.update(replies)
        return self

    def override(self, **by_name: Callable[..., Any]) -> NameIndex[NodeSpec]:
        """A copy of `self.nodes` with those nodes bound to those functions.

        What a test hands to `RunEnv(nodes=…)` instead of patching the module the node
        lives in. The copy is non-mutating, so the registry every other run in the
        process shares is untouched.
        """
        targets: dict[str, NodeSpec] = {}
        for name, fn in by_name.items():
            spec = self.nodes.get(name)
            if spec is None:
                known = ", ".join(sorted(self.nodes.live_names())) or "(none)"
                raise WorkflowDefinitionError(
                    f"workflow {self.name!r} has no node {name!r} to override. "
                    f"Registered nodes: {known}."
                )
            targets[name] = dataclasses.replace(spec, fn=fn)
        return self.nodes.replacing(targets)

    def _claim(self, workflow: type[Workflow]) -> None:
        """Stamp the class so `handoff` can find its registry from the class alone."""
        claimed = workflow.__dict__.get(REGISTRY_ATTR)
        if claimed is not None and claimed is not self:
            raise WorkflowDefinitionError(
                f"{workflow.__name__} is registered on two workflows "
                f"({getattr(claimed, 'name', '?')!r} and {self.name!r}) — a flow class "
                "belongs to one distribution, because its registry is what decides "
                "which prompts directory and which nodes it runs with"
            )
        setattr(workflow, REGISTRY_ATTR, self)

    def state(
        self, fn: Callable[..., Any] | None = None, *, aliases: Iterable[str] = ()
    ) -> Any:
        """`@workflow.state(aliases=[...])`, identical to the standalone `@state`.

        Both exist because the spec shows both, and because a class body is often
        written *above* the `Registry` the module ends with — a decorator that needed
        the registry to exist first would force the file into one order.
        """
        return state(fn, aliases=aliases)

    # --- entry point --------------------------------------------------------

    def entry_point(self, entry: type[Workflow]) -> "Registry":
        """Declare `entry` the flow a bare `workhorse-<name> run` starts.

        Returns `self`, so the declaration composes with the binding the CLI ring
        owns: `main = console_script(workflow.entry_point(Coder))`.

        This method used to *return* that console callable, which meant the registry
        imported `workhorse.cli` — and `workhorse.cli` imports the driver, which
        imports this module. The import had to sit in a function body to keep the two
        modules loadable, and a function-body import with no ImportError beside it is
        a cycle being suppressed rather than a dependency being optional. The binding
        belongs to the ring the console script actually starts.
        """
        _require_workflow("entry", entry)
        if not self.name:
            raise WorkflowDefinitionError(
                "a workflow needs a name before it can be a command — `Registry(\"coder\")`, "
                "not `Registry()`. The name is what the console script is called and "
                "what its usage line and run directories are named after."
            )
        self._claim(entry)
        self.entry = entry
        self.flows.setdefault("default", entry)
        return self

    # --- lookup -------------------------------------------------------------

    def flow(self, flow_name: str | None) -> type[Workflow]:
        """The workflow class a `<flow>` argument names, or the entry point."""
        if not flow_name:
            if self.entry is None:
                raise WorkflowDefinitionError(
                    f"workflow {self.name!r} declares no entry point — call "
                    "`workflow.entry_point(SomeWorkflow)` in the workflow module"
                )
            return self.entry
        try:
            return self.flows[flow_name]
        except KeyError:
            known = ", ".join(sorted(self.flows)) or "(none)"
            raise WorkflowDefinitionError(
                f"workflow {self.name!r} has no flow {flow_name!r}. Known flows: {known}."
            ) from None

    def flow_names(self) -> list[str]:
        return sorted(self.flows)

    def class_named(self, class_name: str | None) -> type[Workflow] | None:
        """The registered flow whose *class* is named `class_name`, or None.

        A checkpoint records the class, not the flow key, because that is what the
        driver has in hand — and because two keys may point at one class. This is how
        `--resume-latest` re-enters the flow that wrote the checkpoint instead of the
        distribution's default one.
        """
        if not class_name:
            return None
        for workflow in self.flows.values():
            if workflow.__name__ == class_name:
                return workflow
        return None

    def directory(self) -> Path:
        """The workflow's own directory — what holds its `prompts/`.

        `package` when the registry declared one, which is the composition root itself
        and the only answer that stays right once the entry class moves into a
        sub-package beside its sibling flows. Otherwise the package the entry class's
        module lives in — what every workflow relied on before `package` existed, kept
        so a distribution that declares nothing keeps resolving as it did.

        `package_dir` is what refuses a zip-imported package here rather than at
        `TemplateNotFound` time.
        """
        if self.package:
            return package_dir(self.package, workflow=self.name or None)
        if self.entry is None:
            raise WorkflowDefinitionError(
                f"workflow {self.name!r} declares neither a package nor an entry point, "
                "so it has no directory — pass `Registry(name, package=__package__)`, or "
                "call `workflow.entry_point(SomeWorkflow)` in the workflow module"
            )
        module = sys.modules.get(self.entry.__module__)
        package = getattr(module, "__package__", None) or self.entry.__module__.rpartition(".")[0]
        if not package:
            raise WorkflowDefinitionError(
                f"workflow {self.name!r} defines {self.entry.__name__} in the top-level "
                f"module {self.entry.__module__!r}, which has no package directory "
                "around it. A workflow's prompts live in its package directory, so the "
                "workflow must be a package (e.g. `myworkflows/research/workflow.py`)."
            )
        return package_dir(package, workflow=self.name or None)

    def __repr__(self) -> str:
        return f"Registry({self.name!r}, flows={self.flow_names()})"


def _require_workflow(label: str, candidate: Any) -> None:
    if not (isinstance(candidate, type) and issubclass(candidate, Workflow)):
        raise WorkflowDefinitionError(
            f"{label} must be a Workflow subclass, got {candidate!r}"
        )
