---
type: concept
slug: pyflow-workflow-api
title: pyflow workflow API
---
# pyflow workflow API

`Workflow` is the pydantic state-machine base class. Public subclass methods become live
states, state parameters are the values checkpointed across one transition, and the instance is
sealed after `setup()` so durable state cannot be hidden in mutable fields. The four run seams
delegate to the bound engine: node calls, agent turns, sub-flow handoffs, and recorded node
outputs.

- code: `workhorse/workhorse/pyflow/workflow.py::Workflow`
- tests: [pyflow tests](../../../../workhorse/tests/test_pyflow.py)

## Fields

### field: repo_dir
- type: `str`
- default: empty string
- required: true
- semantics: consuming repository root passed to nodes; an empty value leaves repository-root discovery to the node
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow`

### field: library_dirs
- type: `tuple[str, ...]`
- default: empty tuple
- required: true
- semantics: ordered content-library roots available to nodes and prompt resolution
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow`

### field: injects
- type: `ClassVar[tuple[str, ...]]`
- default: `("repo_dir", "library_dirs")`
- required: true
- semantics: allowlist of workflow fields eligible for ambient injection into seams
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow`

### field: INFRA_NODES
- type: `ClassVar[frozenset[Any]]`
- default: empty frozenset
- required: true
- semantics: node functions whose spans are classified as infrastructure work
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow`

### field: states
- type: `ClassVar[NameIndex[StateSpec]]`
- required: true
- semantics: per-subclass index of live state names and aliases
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow`

### field: start_state
- type: `ClassVar[str]`
- default: `start`
- required: true
- semantics: state entered when no resume checkpoint selects another state
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow`

### field: max_transitions
- type: `ClassVar[int]`
- default: `0`
- required: true
- semantics: transition ceiling before the run's configured budget is used; zero delegates to the run
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow`

### field: REFUEL_ON
- type: `ClassVar[frozenset[str]]`
- default: empty frozenset
- required: true
- semantics: state-parameter names whose changed value refills the transition budget
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow`

## Methods

### state
- sig: `state(fn=None, *, aliases=()) -> Callable`
- does: attaches retired state aliases to a callable without requiring a registry to exist
- returns: the decorated callable, or a decorator when called without `fn`
- verify: count(subject="state decorators applied", equals=1)
- code: `workhorse/workhorse/pyflow/workflow.py::state`

### state_names
- sig: `state_names() -> list[str]`
- returns: live public state names, excluding aliases and private helpers
- verify: count(subject="live states in a workflow with one alias", equals=2)
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.state_names`

### resolve_state
- sig: `resolve_state(name: str) -> StateSpec`
- does: resolves a live state name or a declared retired alias to its state specification
- raises: `UnknownStateError` when neither a live state nor an alias has that name
- returns: the resolved `StateSpec`
- verify: json_path(path="$.name", equals="qa")
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.resolve_state`

### setup
- sig: `setup() -> Any`
- does: runs once before the first state and supplies the run context
- returns: the value installed as `self.ctx`
- verify: count(subject="setup calls during a fresh run and resume", equals=1)
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.setup`

### labels
- sig: `labels() -> dict[str, str]`
- returns: workflow-defined telemetry dimensions, empty by default
- verify: count(subject="default workflow labels", equals=0)
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.labels`

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: supplies telemetry dimensions for the state parameters about to be bound
- returns: the result of `labels()` by default
- verify: count(subject="default state labels", equals=0)
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.state_labels`

### ctx
- sig: `ctx -> Any`
- returns: the run context produced by `setup()` or restored from a checkpoint
- verify: json_path(path="$.ctx", equals="restored")
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.ctx`

### logger
- sig: `logger -> Logger`
- raises: `WorkflowDefinitionError` when the workflow is not bound to a run
- verify: json_path(path="exception.type", equals="WorkflowDefinitionError")
- returns: the bound run logger
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.logger`

### run_dir
- sig: `run_dir -> Path`
- raises: `WorkflowDefinitionError` when the workflow is not bound to a run
- verify: exists(subject="the bound run directory")
- returns: the bound run artifact directory
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.run_dir`

### run_id
- sig: `run_id -> str`
- raises: `WorkflowDefinitionError` when the workflow is not bound to a run
- verify: count(subject="run identifiers returned by a bound workflow", equals=1)
- returns: the bound stable run identifier
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.run_id`

### call
- sig: `call(node, *args, **kwargs) -> T`
- does: resolves and executes a registered blueprint node through the run engine, injecting permitted ambient inputs
- raises: `WorkflowDefinitionError` when called outside a bound run
- verify: count(subject="recorded node calls", equals=1)
- returns: the node's typed plain value
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.call`

### agent
- sig: `agent(prompt: str, *, returns: type[T], args=None, power=None, timeout=None, retries=None, invoke_retries=None, cwd=None, add_dirs=None, session=None) -> T`
- does: renders a prompt, runs one agent turn, and validates the reply against `returns`
- raises: `AgentTimeout` when the turn's recovery ladder ends because of timeout
- returns: the validated reply model or value
- verify: count(subject="validated agent replies", equals=1)
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.agent`

### seed_session
- sig: `seed_session(key: str, session_id: str) -> None`
- does: seeds an empty named conversation chain with an existing opaque session id
- verify: count(subject="session chain seed files", equals=1)
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.seed_session`

### chain_session
- sig: `chain_session(key: str) -> str`
- returns: the session id recorded for a named chain, or empty before its first turn
- verify: count(subject="session ids read before a chain starts", equals=0)
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.chain_session`

### reset_session
- sig: `reset_session(key: str) -> None`
- does: removes a named session chain so its next turn starts a fresh conversation
- verify: absent(subject="reset session chain file")
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.reset_session`

### handoff
- sig: `handoff(wf, *args, **kwargs) -> Any`
- does: constructs and drives a child workflow in its own artifact scope, propagating only declared arguments and ambient injected fields
- raises: `WorkflowFailed` when the child cannot complete
- verify: count(subject="completed child workflow results", equals=1)
- returns: the child workflow's `Done` result
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.handoff`

### output
- sig: `output(node: Callable[..., T]) -> T`
- raises: `NodeNotRunError` when no output exists in the current scope
- verify: json_path(path="$.value", equals="recorded")
- returns: the latest recorded output for a node in the current flow scope, revived into its declared type
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.output`

## State Lifecycle

Public methods declared by a subclass are registered as states unless they are inherited base
members, `setup`, `labels`, or private helpers. `@state(aliases=[...])` preserves checkpoint
resume after a rename without rendering the alias as a second live state. `setup()` may write
inputs; after it returns, public assignment raises `WorkflowFrozenError`. A state must carry
values needed by a later branch in its `Continue` parameters, because those parameters are the
checkpointed state boundary.
