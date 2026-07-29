"""The module-level object an entry point points at.

```python
workflow = Registry("coder")
workflow.add_blueprints(scriptutil.blueprint, blueprint)
main = workflow.main(Coder)
```

Two things resolve to this object, and it is the reason both can share one parser:
the `workhorse.workflows` entry point names it (so `workhorse run coder …` finds the
workflow), and `main` — *the callable `main(Entry)` returns*, never a call made at
import — is the `workhorse-coder` console script. A workflow module must stay
importable without running anything.
"""
from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from workhorse.packaged import package_dir
from workhorse.pyflow.blueprint import Blueprint, NodeSpec
from workhorse.pyflow.errors import WorkflowDefinitionError
from workhorse.pyflow.names import NameIndex
from workhorse.pyflow.workflow import Workflow, state


class Registry:
    """One workflow distribution's flows, nodes and entry point.

    Named `Registry` rather than `Workflow` because the base class a workflow
    subclasses already owns that name, and the two are different things: the class is
    the state machine, this is what the packaging metadata points at.
    """

    def __init__(self, name: str = "") -> None:
        self.name = name
        self.blueprints: list[Blueprint] = []
        self.flows: dict[str, type[Workflow]] = {}
        self.entry: type[Workflow] | None = None
        self.nodes: NameIndex[NodeSpec] = NameIndex("node", owner=f"workflow {name!r}")

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
        """Register sub-flows a caller can name, e.g. `workhorse run coder qa`."""
        for flow_name, workflow in flows.items():
            if flow_name in self.flows:
                raise WorkflowDefinitionError(
                    f"flow {flow_name!r} is registered twice on workflow {self.name!r}"
                )
            _require_workflow(flow_name, workflow)
            self.flows[flow_name] = workflow
        return self

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

    def main(self, entry: type[Workflow]) -> Callable[..., None]:
        """Declare `entry` the default flow and RETURN the console-script callable.

        Returning rather than calling is the whole contract: `main = workflow.main(Coder)`
        leaves the module importable — which entry-point discovery depends on, since
        resolving a workflow name imports it — while `[project.scripts]` still has a
        callable to point at.
        """
        _require_workflow("entry", entry)
        if not self.name:
            raise WorkflowDefinitionError(
                "a workflow needs a name before it can be a command — `Registry(\"coder\")`, "
                "not `Registry()`. The name is what `workhorse run <name>` resolves and "
                "what the CLI binds so a bare `workhorse-<name> run qa` reads 'qa' as the "
                "flow rather than as the workflow."
            )
        self.entry = entry
        self.flows.setdefault("default", entry)

        def console_main(argv: list[str] | None = None) -> None:
            # Imported here, not at module scope: `workhorse.main` imports the driver,
            # which imports this module. This is the one place the cycle is broken, and
            # it is broken at call time so importing a workflow module stays cheap.
            from workhorse.main import main as workhorse_main

            workhorse_main(argv, workflow=self.name, registry=self)

        console_main.__name__ = "main"
        console_main.__doc__ = f"Console-script entry for the {self.name!r} workflow."
        return console_main

    # --- lookup -------------------------------------------------------------

    def flow(self, flow_name: str | None) -> type[Workflow]:
        """The workflow class a `<flow>` argument names, or the entry point."""
        if not flow_name:
            if self.entry is None:
                raise WorkflowDefinitionError(
                    f"workflow {self.name!r} declares no entry point — call "
                    "`workflow.main(SomeWorkflow)` in the workflow module"
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

        Taken from the package the entry class's module lives in, so it is the same
        directory whether the name was resolved through an entry point or the console
        script bypassed discovery entirely. `package_dir` is what refuses a
        zip-imported package here rather than at `TemplateNotFound` time.
        """
        if self.entry is None:
            raise WorkflowDefinitionError(
                f"workflow {self.name!r} declares no entry point, so it has no "
                "directory — call `workflow.main(SomeWorkflow)` in the workflow module"
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
