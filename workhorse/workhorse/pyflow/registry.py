"""The module-level object a workflow's console script points at."""
from __future__ import annotations

import dataclasses
import inspect
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from workhorse.packaged import package_dir
from workhorse.pyflow.blueprint import Blueprint, NodeSpec
from workhorse.pyflow.errors import WorkflowDefinitionError
from workhorse.pyflow.names import NameIndex
from workhorse.pyflow.workflow import Workflow, state

REGISTRY_ATTR = "__workhorse_registry__"


def registry_of(cls: type[Workflow]) -> "Registry | None":
    """The registry that claimed `cls`, or None if it was never registered."""
    registry = cls.__dict__.get(REGISTRY_ATTR)
    return registry if isinstance(registry, Registry) else None


class Registry:
    """One workflow distribution's flows, nodes and entry point."""

    def __init__(self, name: str = "", package: str | None = None) -> None:
        self.name = name
        self.package = package or ""
        frame = inspect.currentframe()
        caller = frame.f_back if frame is not None else None
        self.module = str(caller.f_globals.get("__name__", "")) if caller is not None else ""
        self.blueprints: list[Blueprint] = []
        self.flows: dict[str, type[Workflow]] = {}
        self.entry: type[Workflow] | None = None
        self.nodes: NameIndex[NodeSpec] = NameIndex("node", owner=f"workflow {name!r}")
        self.agent_stubs: dict[str, Any] = {}


    def add_blueprints(self, *blueprints: Blueprint) -> "Registry":
        """Fold node libraries in."""
        for blueprint in blueprints:
            self.blueprints.append(blueprint)
            self.nodes.merge(blueprint.index)
        return self

    def add_flows(self, **flows: type[Workflow]) -> "Registry":
        """Register sub-flows a caller can name, e.g."""
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
        """Declare what `--dry-run` should get back from each prompt, by stem."""
        self.agent_stubs.update(replies)
        return self

    def override(self, **by_name: Callable[..., Any]) -> NameIndex[NodeSpec]:
        """A copy of `self.nodes` with those nodes bound to those functions."""
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
        """`@workflow.state(aliases=[...])`, identical to the standalone `@state`."""
        return state(fn, aliases=aliases)


    def entry_point(self, entry: type[Workflow]) -> "Registry":
        """Declare `entry` the flow a bare `workhorse-<name> run` starts."""
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
        """The registered flow whose *class* is named `class_name`, or None."""
        if not class_name:
            return None
        for workflow in self.flows.values():
            if workflow.__name__ == class_name:
                return workflow
        return None

    def directory(self) -> Path:
        """The workflow's own directory — what holds its `prompts/`."""
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
