"""Workflows written as Python state machines.

The public surface a workflow module imports:

```python
from workhorse.cli import console_script
from workhorse.pyflow import Blueprint, Continue, Done, Registry, Workflow

blueprint = Blueprint("acme")


class Build(Workflow):
    story: str

    def start(self) -> Continue | Done:
        return Continue(None, self.review, notes="")

    def review(self, notes: str) -> Done:
        return Done(notes)


workflow = Registry("acme").add_blueprints(blueprint)
main = console_script(workflow.entry_point(Build))
```

`run` is deliberately NOT re-exported here: it imports the artifact writer, the agent
runner and the config, so pulling it in would make every `import workhorse.pyflow`
drag the whole engine along — a workflow module must stay cheap to import, because
resolving a workflow *name* imports it.
"""
from __future__ import annotations

from workhorse.pyflow.blueprint import Blueprint, NodeSpec
from workhorse.pyflow.errors import (
    AgentTimeout,
    NodeNotRunError,
    PyflowError,
    UnknownNodeError,
    UnknownStateError,
    WorkflowDefinitionError,
    WorkflowFailed,
    WorkflowFrozenError,
)
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.transitions import Await, Continue, Done
from workhorse.pyflow.workflow import StateSpec, Workflow, state

__all__ = [
    "AgentTimeout",
    "Await",
    "Blueprint",
    "Continue",
    "Done",
    "NodeNotRunError",
    "NodeSpec",
    "PyflowError",
    "Registry",
    "StateSpec",
    "UnknownNodeError",
    "UnknownStateError",
    "Workflow",
    "WorkflowDefinitionError",
    "WorkflowFailed",
    "WorkflowFrozenError",
    "state",
]
