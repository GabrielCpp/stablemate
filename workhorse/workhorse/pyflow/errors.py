"""Every way a Python-defined workflow can go wrong, named."""
from __future__ import annotations


class PyflowError(Exception):
    """Base for every error the Python state-machine driver raises."""


class WorkflowFailed(PyflowError):
    """A state gave up."""

    def __init__(
        self,
        message: str,
        *,
        failure_class: str = "",
        artifacts: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.artifacts = dict(artifacts or {})


class AgentTurnFailed(PyflowError):
    """The recovery ladder is finished with an agent turn and it produced nothing."""

    def __init__(
        self,
        message: str,
        *,
        transient: bool = False,
        overflow: bool = False,
    ) -> None:
        super().__init__(message)
        self.transient = transient
        self.overflow = overflow


class AgentTimeout(PyflowError):
    """An agent turn was stopped at its per-node `timeout`, with its budget spent."""

    def __init__(self, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        self.transient = transient


class RunBudgetExceeded(PyflowError):
    """The run outlived `WORKHORSE_MAX_RUNTIME_S`."""


class WorkflowDefinitionError(PyflowError):
    """The workflow is mis-declared — raised at registration/import time."""


class UnknownStateError(PyflowError):
    """A checkpoint (or transition) names a state this workflow does not have."""


class UnknownNodeError(PyflowError):
    """A function was used as a node but never registered on a blueprint."""


class NodeNotRunError(PyflowError):
    """`self.output(node)` for a node that has not run in this run."""


class WorkflowFrozenError(PyflowError):
    """Something tried to write to the workflow instance after `setup()` returned."""
