---
type: concept
slug: pyflow-engine
title: pyflow engine seams and run environment
---
# pyflow engine seams and run environment

`RunEnv` contains the dependencies and run-scoped state that are not workflow inputs;
`Engine` exposes the workflow seams. Calls resolve node implementations through the
run index, record artifacts and retry telemetry, and can substitute dry-run bodies.
Agent turns use the configured runner and typed reply model, with optional named
session chains. Handoffs create a resume-aware child scope, while output reads the
first available recorded artifact under a node's live or alias directory and fails if
none exists.

- code: `workhorse/workhorse/pyflow/engine.py::Engine`
- tests: [pyflow tests](../../../../workhorse/tests/test_pyflow.py)

## Fields

### field: RunEnv

All infrastructure dependencies and substitutions are shared by one drive invocation.

- type: dataclass containing writer, workflow_dir, session_id_path, config, driver, log, dry_run, clock, deadline, labels, manifest, nodes, agent_stubs, agent_runner, and resume_pending
- code: `workhorse/workhorse/pyflow/engine.py::RunEnv`

## Methods

### jsonable
- sig: `jsonable(value: Any) -> Any`
- returns: a best-effort JSON-compatible projection, using model dumps, dataclass conversion, path strings, and repr fallback
- verify: json_path(path="$.value", equals="projected")
- code: `workhorse/workhorse/pyflow/engine.py::jsonable`

### stub_nodes
- sig: `stub_nodes(index: NameIndex[NodeSpec]) -> NameIndex[NodeSpec]`
- returns: a non-mutating index whose node bodies are dry-run stand-ins with retries disabled
- verify: count(subject="live names in a stubbed node index", equals=1)
- code: `workhorse/workhorse/pyflow/engine.py::stub_nodes`

### Engine.call
- sig: `call(node, args, kwargs, span_kind="") -> Any`
- does: resolves the registered node from the run index
- verify: count(subject="registered node resolved for one call", equals=1)
- does: records a supplied workflow span kind on the node-enter artifact
- verify: json_path(path="$.node_enter.span_kind", equals="workflow")
- does: injects the run logger into the node call
- verify: count(subject="run loggers injected into one node call", equals=1)
- does: invokes the resolved node
- verify: emitted(event="node invocation", count=1)
- does: retries a failing node up to its declared retry budget and emits a retry event for each failed attempt before the final one
- verify: emitted(event="node_retry", count=1)
- does: records the node's output artifact
- verify: persists(subject="node output artifact")
- raises: `UnknownNodeError` when the node is not in the run index
- returns: the node's typed plain value
- code: `workhorse/workhorse/pyflow/engine.py::Engine.call`

### Engine.agent
- sig: `agent(prompt, *, returns, args, power=None, timeout=None, retries=None, invoke_retries=None, cwd=None, add_dirs=None, session=None) -> Any`
- does: records an agent visit with its prompt and supplied repository working directory and additional directories
- verify: persists(subject="agent visit record")
- does: uses a named session chain with the configured runner and reads its persisted id when its chain file exists
- verify: json_path(path="$.runner.resume_session", equals=true)
- does: returns the registered stub reply and records its output without invoking the configured runner during a dry run
- verify: persists(subject="dry-run agent visit output artifact")
- does: forwards a supplied invocation retry budget to the configured runner
- verify: json_path(path="$.runner.invoke_retries", equals=2)
- does: forwards a supplied working directory to the configured runner
- verify: json_path(path="$.runner.node.cwd", equals="/repos/acme")
- does: forwards supplied additional repository directories to the configured runner
- verify: json_path(path="$.runner.node.add_dirs[1]", equals="/repos/api-service")
- does: supplies the run manifest's projected values to the runner's prompt render context
- verify: json_path(path="$.runner.context.template.backend_layer_name", equals="Go gateway")
- does: overlays the agent call's arguments on same-named manifest render-context values
- verify: json_path(path="$.runner.context.unit", equals="CASE-1")
- does: renders and runs the prompt through the run's runner
- verify: persists(subject="rendered agent prompt and runner result")
- does: supplies a requested Pydantic return model's validator to the runner so a structurally invalid reply can enter corrective retry before final coercion
- verify: json_path(path="$.runner.validation_error", matches="count")
- does: coerces the runner's raw reply to the requested return type
- raises: `AgentTimeout` when a timed-out backend invocation exhausts recovery
- raises: `AgentTurnFailed` when a backend invocation that did not time out exhausts recovery
- returns: the validated reply value
- verify: persists(subject="agent visit output artifact")
- code: `workhorse/workhorse/pyflow/engine.py::Engine.agent`

### Engine.handoff
- sig: `handoff(wf, args, kwargs) -> Any`
- does: constructs and drives a child workflow in a subscope, returning the driver's result
- does: resumes the child in place when the interrupted parent state is re-entered, then consumes the resume marker
- verify: json_path(path="$.child_driver.resume_in_place", equals=true)
- raises: `WorkflowFailed` when no driver is available
- returns: the child workflow's driver result
- verify: persists(subject="child workflow scope artifacts")
- code: `workhorse/workhorse/pyflow/engine.py::Engine.handoff`

### Engine.output
- sig: `output(node) -> Any`
- raises: `NodeNotRunError` when no output exists under the live or alias directory names
- verify: absent(subject="output artifact before node invocation")
- returns: the first available node output under its live or alias directory, revived through its declared return type
- code: `workhorse/workhorse/pyflow/engine.py::Engine.output`

### Engine.session_id
- sig: `session_id(key: str) -> str`
- returns: the persisted session id for a chain, or an empty string before its first turn
- verify: json_path(path="$.session_id", absent=true)
- code: `workhorse/workhorse/pyflow/engine.py::Engine.session_id`

### Engine.seed_session
- sig: `seed_session(key: str, session_id: str) -> None`
- does: writes a non-empty session id for a chain only when that chain has no existing id
- verify: persists(subject="seeded session chain")
- code: `workhorse/workhorse/pyflow/engine.py::Engine.seed_session`

### Engine.reset_session
- sig: `reset_session(key: str) -> None`
- does: removes a chain file so its next turn starts a new conversation
- verify: removed(subject="the session chain for the supplied key")
- code: `workhorse/workhorse/pyflow/engine.py::Engine.reset_session`
