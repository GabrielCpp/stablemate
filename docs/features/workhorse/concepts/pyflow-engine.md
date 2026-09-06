---
type: concept
slug: pyflow-engine
title: pyflow engine seams and run environment
---
# pyflow engine seams and run environment

`RunEnv` contains the dependencies and run-scoped state that are not workflow inputs;
`Engine` exposes the workflow seams. Calls resolve node implementations through the
run index, record artifacts, and can substitute dry-run bodies. Agent turns use the
configured runner and typed reply model. Handoffs create a child scope, while output
reads the latest recorded node artifact and fails if none exists.

- code: `workhorse/workhorse/pyflow/engine.py::Engine`
- tests: [pyflow tests](../../../../workhorse/tests/test_pyflow.py)

## Fields

### field: RunEnv
- type: dataclass containing writer, workflow_dir, session_id_path, config, driver, log, dry_run, clock, deadline, labels, manifest, nodes, agent_stubs, agent_runner, and resume_pending
- semantics: all infrastructure dependencies and substitutions shared by one drive invocation
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
- does: injects the run logger into the node call
- verify: count(subject="run loggers injected into one node call", equals=1)
- does: injects the ambient inputs into the node call
- verify: count(subject="ambient inputs injected into one node call", equals=1)
- does: invokes the resolved node
- verify: emitted(event="node invocation", count=1)
- does: records the node's output artifact
- verify: persists(subject="node output artifact")
- raises: `UnknownNodeError` when the node is not in the run index
- returns: the node's typed plain value
- code: `workhorse/workhorse/pyflow/engine.py::Engine.call`

### Engine.agent
- sig: `agent(prompt, *, returns, args, power=None, timeout=None, retries=None, cwd=None, add_dirs=None, session=None) -> Any`
- does: records an agent visit
- verify: persists(subject="agent visit record")
- does: renders and runs the prompt through the run's runner
- verify: persists(subject="rendered agent prompt and runner result")
- does: validates the reply against the requested model
- verify: persists(subject="validated agent reply")
- raises: `AgentTimeout` when a timed-out backend invocation exhausts recovery
- returns: the validated reply value
- verify: persists(subject="agent visit output artifact")
- code: `workhorse/workhorse/pyflow/engine.py::Engine.agent`

### Engine.handoff
- sig: `handoff(wf, args, kwargs) -> Any`
- does: constructs and drives a child workflow in a subscope, returning its terminal result
- raises: `WorkflowFailed` when no driver is available
- returns: the child's `Done` result
- verify: persists(subject="child workflow scope artifacts")
- code: `workhorse/workhorse/pyflow/engine.py::Engine.handoff`

### Engine.output
- sig: `output(node) -> Any`
- raises: `NodeNotRunError` when no output exists under the live or alias directory names
- verify: absent(subject="output artifact before node invocation")
- returns: the latest recorded node output revived through its declared return type
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
