---
type: concept
slug: pyflow-errors
title: pyflow errors
---
# pyflow errors

The pyflow error taxonomy separates import-time definition mistakes from failures in
an active run. All classes derive from `PyflowError`; `WorkflowFailed` optionally carries
a machine-readable failure class and artifact paths for the failure handoff. A runtime
failure remains resumable unless the outer run policy explicitly marks it terminal.

- code: `workhorse/workhorse/pyflow/errors.py::PyflowError`
- tests: [pyflow tests](../../../../workhorse/tests/test_pyflow.py)

## Classes

### field: WorkflowFailed
- type: `PyflowError`
- semantics: state-declared or driver-detected failed outcome, with optional `failure_class` and artifact paths
- verify: json_path(path="$.kind", equals="failure")
- code: `workhorse/workhorse/pyflow/errors.py::WorkflowFailed`

### field: AgentTimeout
- type: `PyflowError`
- semantics: an agent turn exhausted its recovery ladder after a timeout
- code: `workhorse/workhorse/pyflow/errors.py::AgentTimeout`

### field: RunBudgetExceeded
- type: `PyflowError`
- semantics: the run-wide wall-clock budget expired and the checkpoint must remain resumable
- verify: json_path(path="$.terminal", equals=null)
- code: `workhorse/workhorse/pyflow/errors.py::RunBudgetExceeded`

### field: WorkflowDefinitionError
- type: `PyflowError`
- semantics: a registry, state, node, alias, or package declaration is invalid at import or setup time
- code: `workhorse/workhorse/pyflow/errors.py::WorkflowDefinitionError`

### field: UnknownStateError
- type: `PyflowError`
- semantics: a transition or checkpoint names neither a live state nor an alias
- code: `workhorse/workhorse/pyflow/errors.py::UnknownStateError`

### field: UnknownNodeError
- type: `PyflowError`
- semantics: a function is used as a node without blueprint registration or is absent from the run index
- code: `workhorse/workhorse/pyflow/errors.py::UnknownNodeError`

### field: NodeNotRunError
- type: `PyflowError`
- semantics: `self.output` requested an artifact with no recorded invocation in the current scope
- code: `workhorse/workhorse/pyflow/errors.py::NodeNotRunError`

### field: WorkflowFrozenError
- type: `PyflowError`
- semantics: a workflow field was assigned after setup sealed the instance
- verify: json_path(path="$.error.type", equals="WorkflowFrozenError")
- code: `workhorse/workhorse/pyflow/errors.py::WorkflowFrozenError`

The package re-exports these classes, the transition values, `Blueprint`, `Registry`,
`Workflow`, `state`, `NodeSpec`, `StateSpec`, and `Transition` from `pyflow.__init__`.
The `run` module is intentionally not imported by that package initializer, keeping a
workflow's lightweight declaration import separate from the run engine.

- code: `workhorse/workhorse/pyflow/__init__.py::__all__`
