---
type: concept
slug: agent-node-spec
title: Agent node specification
---
# Agent node specification

The runner receives one `AgentNode` for each agent turn. It is the internal contract shared by
the Python driver and the runner: prompt and arguments are rendered from workflow context,
declared outputs determine extraction, and per-node settings override run defaults. It is not a
workflow-format file or a backend request.

- code: `workhorse/workhorse/runner/spec.py::AgentNode`
- code: `workhorse/workhorse/runner/spec.py::OutputSpec`
- detail: [AgentRunner.run](run-agent.md)

## Fields

### AgentNode
- type: Pydantic model
- semantics: accepts only `type: agent`
- verify: json_path(path="$.type", equals="agent")
- semantics: `id` identifies the node
- semantics: `prompt` names its template
- code: `workhorse/workhorse/runner/spec.py::AgentNode`

### type
- type: literal `agent`
- required: true
- verify: json_path(path="$.type", equals="agent")
- semantics: distinguishes an agent node from other node kinds
- verify: json_path(path="$.type", matches="^agent$")
- code: `workhorse/workhorse/runner/spec.py::AgentNode`

### id
- type: string
- required: true
- verify: json_path(path="$.id", matches=".+")
- semantics: stable node identifier used in logs, artifacts, telemetry, and session records
- code: `workhorse/workhorse/runner/spec.py::AgentNode`

### prompt
- type: string
- required: true
- verify: json_path(path="$.prompt", matches=".+")
- semantics: workflow-relative template rendered before invocation
- verify: persists(subject="the rendered workflow-relative prompt")
- code: `workhorse/workhorse/runner/spec.py::AgentNode`

### args
- type: `dict[str, str]`
- default: `{}`
- verify: count(subject="AgentNode arguments when omitted", equals=0)
- required: false
- semantics: Jinja string arguments rendered and merged into the prompt context
- code: `workhorse/workhorse/runner/spec.py::AgentNode`

### outputs
- type: `list[OutputSpec]`
- default: `[]`
- verify: count(subject="declared output specifications when omitted", equals=0)
- required: false
- semantics: ordered declared result keys
- semantics: an empty list means the turn returns no extracted values
- verify: count(subject="extracted output values for an empty declaration", equals=0)
- code: `workhorse/workhorse/runner/spec.py::AgentNode`

### power
- type: `str | None`
- default: `None`
- verify: json_path(path="$.power", equals=None)
- required: false
- semantics: opaque operator-configured model capacity tier
- verify: json_path(path="$.power", matches=".+")
- semantics: unresolved tiers fall through to backend defaults
- verify: json_path(path="$.model", matches=".+")
- code: `workhorse/workhorse/runner/spec.py::AgentNode`

### timeout
- type: `float | None`
- default: `3600`
- required: false
- semantics: per-turn seconds
- verify: json_path(path="$.timeout", equals=3600)
- semantics: numeric strings are accepted as seconds
- verify: json_path(path="$.timeout", equals=5000)
- semantics: `0` and `None` use the engine default
- verify: json_path(path="$.timeout", equals=0)
- semantics: `infinity`, `inf`, `infinite`, `unbounded`, and `never` disable the deadline
- verify: json_path(path="$.timeout", equals="infinity")
- code: `workhorse/workhorse/runner/spec.py::AgentNode._coerce_timeout`

### retries
- type: `int | None`
- default: `None`
- required: false
- semantics: retries sets a node-specific reframe limit
- verify: json_path(path="$.retries", matches="^(None|[0-9]+)$")
- semantics: `None` uses run resilience
- verify: json_path(path="$.retries", equals="None")
- semantics: `0` disables reframing
- verify: json_path(path="$.retries", equals=0)
- code: `workhorse/workhorse/runner/spec.py::AgentNode`

### cwd
- type: `str | None`
- default: `None`
- verify: json_path(path="$.cwd", equals=None)
- required: false
- verify: json_path(path="$.cwd", absent=true)
- semantics: optional Jinja-rendered subprocess working directory
- verify: json_path(path="$.cwd", matches=".+")
- code: `workhorse/workhorse/runner/spec.py::AgentNode`

### add_dirs
- type: `list[str] | str`
- default: `[]`
- verify: count(subject="default additional-directory entries", equals=0)
- required: false
- semantics: additional Jinja-rendered directories are granted to the backend
- verify: count(subject="backend --add-dir arguments for rendered additional directories", equals=2)
- semantics: a bare variable may resolve to a native list
- verify: count(subject="--add-dir arguments from a native list-valued template", equals=2)
- code: `workhorse/workhorse/runner/spec.py::AgentNode`

### activity
- type: `str | None`
- default: `None`
- verify: json_path(path="$.activity", equals=None)
- required: false
- verify: json_path(path="$.activity", absent=true)
- semantics: optional Jinja-rendered human activity label for telemetry
- verify: emitted(event="wf.activity", count=1)
- code: `workhorse/workhorse/runner/spec.py::AgentNode`

### next
- type: `str | None`
- default: `None`
- verify: json_path(path="$.next", equals=None)
- required: false
- verify: json_path(path="$.next", absent=true)
- semantics: optional following node identifier carried by the node specification
- verify: json_path(path="$.next", equals="next_node")
- code: `workhorse/workhorse/runner/spec.py::AgentNode`

### OutputSpec
- type: Pydantic model
- semantics: names one extracted output
- verify: json_path(path="$.key", matches=".+")
- semantics: records whether its key must be present
- verify: json_path(path="$.required", matches="^(true|false)$")
- code: `workhorse/workhorse/runner/spec.py::OutputSpec`

### key
- type: string
- required: true
- verify: json_path(path="$.key", matches=".+")
- semantics: output key requested from the agent response
- verify: created(subject="the declared output key in extracted results")
- code: `workhorse/workhorse/runner/spec.py::OutputSpec`

### required
- type: boolean
- default: `true`
- verify: json_path(path="$.required", equals=true)
- required: false
- verify: json_path(path="$.required", absent=true)
- semantics: missing optional keys are omitted
- verify: absent(subject="a missing optional output key")
- semantics: missing required keys raise `OutputParseError`
- verify: absent(subject="fallback output after a missing required key")
- code: `workhorse/workhorse/runner/spec.py::OutputSpec`

`workhorse.runner.__init__` intentionally exports no names. Consumers import the specific runner
modules rather than receiving a second public API from the package initializer.
