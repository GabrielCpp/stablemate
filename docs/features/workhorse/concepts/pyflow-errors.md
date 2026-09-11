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
- semantics: the `failure_class` kwarg, when supplied, is what `_record_failure_handoff` writes to the inbox body in place of the exception's class name
- semantics: the `artifacts` kwarg, when supplied, becomes one `name: path` line per entry appended to the inbox body
- verify: json_path(path="$.kind", equals="failure")
- code: `workhorse/workhorse/pyflow/errors.py::WorkflowFailed`
- tests: `workhorse/tests/test_failure_handoff.py::test_a_workflow_failure_writes_a_diagnostic_outbox_entry`, `workhorse/tests/test_failure_handoff.py::test_a_raise_sites_own_failure_class_and_artifacts_reach_the_outbox`

### field: AgentTimeout
- type: `PyflowError`
- semantics: an agent turn was stopped at its per-node `timeout` after the recovery ladder finished with it — the ladder's verdict, not a report of the first overrun, so a catching state lands a verdict rather than short-circuiting a retry that would have succeeded
- semantics: whether anything survives a cut turn depends on what the turn was writing — nothing to salvage and a resumable checkpoint when the deliverable is the reply, a partial draft usually worth more than a fresh start when the deliverable is a file on disk, and only the calling state knows which it has
- semantics: pair it with `retries=0` so the reframes do not spend the node's whole budget again before this is ever raised
- semantics: carries `transient` (default `False`) mirroring `BackendInvocationError.transient`, so a state can distinguish a wall-clock stop from a network blip or an unreachable provider — both want a different gate than a deterministic timeout
- semantics: deliberately NOT a subtype of `AgentTurnFailed` — a cut turn may have left a partial file worth keeping where the other signals "no answer at all"
- verify: json_path(path="exception.type", equals="AgentTimeout")
- verify: json_path(path="exception.transient", equals=false)
- code: `workhorse/workhorse/pyflow/errors.py::AgentTimeout`

### field: AgentTurnFailed
- type: `PyflowError`
- semantics: an agent turn exhausted its recovery ladder without producing an answer, and is deliberately not a supertype of `AgentTimeout`
- semantics: carries `transient` (default `False`) mirroring `BackendInvocationError.transient`, so a state can distinguish "the CLI blipped" (e.g. a `models.dev` catalog fetch timing out) from a deterministic failure — the two want opposite recovery
- semantics: carries `overflow` (default `False`) mirroring `BackendInvocationError.overflow`, so a state can recognise when the model spent its output budget on reasoning rather than producing a usable reply — the two want opposite recovery
- semantics: uncaught, stops the run at a resumable checkpoint rather than stamping a terminal — a provider that gave up is an operational stop, not the workflow's verdict on itself
- verify: json_path(path="exception.type", equals="AgentTurnFailed")
- verify: json_path(path="exception.transient", equals=false)
- verify: json_path(path="exception.overflow", equals=false)
- code: `workhorse/workhorse/pyflow/errors.py::AgentTurnFailed`

### field: RunBudgetExceeded
- type: `PyflowError`
- semantics: the run-wide wall-clock budget expired and the checkpoint must remain resumable
- semantics: caught by the driver but routed past the failure-handoff inbox entry — the run dir is left without `inbox.jsonl`, the same way a run with no `PyflowError` ever raised looks
- verify: json_path(path="$.terminal", absent=true)
- code: `workhorse/workhorse/pyflow/errors.py::RunBudgetExceeded`
- tests: `workhorse/tests/test_failure_handoff.py::test_a_run_budget_stop_writes_no_outbox_entry`

### field: WorkflowDefinitionError
- type: `PyflowError`
- semantics: a registry, state, node, alias, or package declaration is invalid at import or setup time
- verify: json_path(path="exception.type", equals="WorkflowDefinitionError")
- code: `workhorse/workhorse/pyflow/errors.py::WorkflowDefinitionError`

### field: UnknownStateError
- type: `PyflowError`
- semantics: a transition or checkpoint names neither a live state nor an alias
- verify: json_path(path="exception.type", equals="UnknownStateError")
- code: `workhorse/workhorse/pyflow/errors.py::UnknownStateError`

### field: UnknownNodeError
- type: `PyflowError`
- semantics: a function is used as a node without blueprint registration or is absent from the run index
- verify: json_path(path="exception.type", equals="UnknownNodeError")
- code: `workhorse/workhorse/pyflow/errors.py::UnknownNodeError`

### field: NodeNotRunError
- type: `PyflowError`
- semantics: `self.output` requested an artifact with no recorded invocation in the current scope
- verify: json_path(path="exception.type", equals="NodeNotRunError")
- code: `workhorse/workhorse/pyflow/errors.py::NodeNotRunError`

### field: WorkflowFrozenError
- type: `PyflowError`
- semantics: a workflow field was assigned after setup sealed the instance
- verify: json_path(path="$.error.type", equals="WorkflowFrozenError")
- code: `workhorse/workhorse/pyflow/errors.py::WorkflowFrozenError`

The package re-exports `PyflowError`, `WorkflowFailed`, `AgentTimeout`,
`AgentTurnFailed`,
`WorkflowDefinitionError`, `UnknownStateError`, `UnknownNodeError`, `NodeNotRunError`,
and `WorkflowFrozenError`, along with the transition values, `Blueprint`, `Registry`,
`Workflow`, `state`, `NodeSpec`, `StateSpec`, and `Transition` from `pyflow.__init__`.
`RunBudgetExceeded` remains available from `workhorse.pyflow.errors` but is not a
`pyflow` package export. The `run` module is intentionally not imported by that package
initializer, keeping a workflow's lightweight declaration import separate from the run
engine.

- code: `workhorse/workhorse/pyflow/__init__.py::__all__`
