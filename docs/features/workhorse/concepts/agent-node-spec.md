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
- detail: [Output specification reading guide](output-specification-reading-guide.md)
- detail: [Output specification documentation scope](output-specification-documentation-scope.md)
- detail: [Output specification documentation](output-specification-documentation.md)
- detail: [Agent node documentation scope](agent-node-documentation-scope.md)
- detail: [AgentRunner.run](run-agent.md)

## Fields

### AgentNode
- type: Pydantic model
- semantics: accepts only `type: agent`
- verify: json_path(path="$.type", equals="agent")
- semantics: `id` identifies the node
- semantics: `prompt` names its template
- code: `workhorse/workhorse/runner/spec.py::AgentNode`
- detail: [Agent node field selection](agent-node-field-selection.md)

### type
- type: literal `agent`
- required: true
- verify: json_path(path="$.type", equals="agent")
- semantics: distinguishes an agent node from other node kinds
- verify: json_path(path="$.type", matches="^agent$")
- code: `workhorse/workhorse/runner/spec.py::AgentNode`
- detail: [Agent node field selection](agent-node-field-selection.md)

### id
- type: string
- required: true
- verify: json_path(path="$.id", matches=".+")
- semantics: stable node identifier used in logs, artifacts, telemetry, and session records
- code: `workhorse/workhorse/runner/spec.py::AgentNode`
- detail: [Agent node field selection](agent-node-field-selection.md)

### prompt
- type: string
- required: true
- verify: json_path(path="$.prompt", matches=".+")
- semantics: workflow-relative template rendered before invocation
- verify: persists(subject="the rendered workflow-relative prompt")
- code: `workhorse/workhorse/runner/spec.py::AgentNode`
- detail: [Agent node field selection](agent-node-field-selection.md)

### args
- type: `dict[str, str]`
- default: `{}`
- verify: count(subject="AgentNode arguments when omitted", equals=0)
- required: false
- semantics: Jinja string arguments rendered and merged into the prompt context
- code: `workhorse/workhorse/runner/spec.py::AgentNode`
- detail: [Agent node field selection](agent-node-field-selection.md)

### outputs
- type: `list[OutputSpec]`
- default: `[]`
- verify: count(subject="declared output specifications when omitted", equals=0)
- required: false
- semantics: ordered output specifications for declared result keys
- semantics: an empty list means the turn returns no extracted values
- verify: count(subject="extracted output values for an empty declaration", equals=0)
- code: `workhorse/workhorse/runner/spec.py::AgentNode`
- detail: [Agent node field selection](agent-node-field-selection.md)

### power
- type: `str | None`
- default: `None`
- verify: json_path(path="$.power", absent=true)
- required: false
- semantics: opaque operator-configured model capacity tier resolved through `[power.<level>.<backend>]` mappings rather than a closed enum
- verify: json_path(path="$.power", matches=".+")
- semantics: `low`, `medium`, `high`, `smart`, and `extra-smart` are the shipped cheapest-to-most-capable convention
- verify: json_path(path="$.power", equals="high")
- semantics: `smart` requests frontier reasoning
- verify: json_path(path="$.power", equals="smart")
- semantics: `extra-smart` requests the premium model
- verify: json_path(path="$.power", equals="extra-smart")
- semantics: neither `smart` nor `extra-smart` constrains the tiers an operator configures
- verify: json_path(path="$.power", equals="cheap-bulk")
- semantics: an unmapped or misspelled tier falls through to `[default.<backend>]` rather than failing the run
- verify: json_path(path="$.model", matches=".+")
- code: `workhorse/workhorse/runner/spec.py::AgentNode`
- detail: [Agent node field selection](agent-node-field-selection.md)

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
- semantics: case-insensitive `infinity`, `inf`, `infinite`, `unbounded`, and `never`, plus YAML `.inf`, disable the deadline
- verify: json_path(path="$.timeout", equals="infinity")
- code: `workhorse/workhorse/runner/spec.py::AgentNode._coerce_timeout`

### retries
- type: `int | None`
- default: `None`
- required: false
- semantics: limits how many failed turns are reframed from scratch in a fresh session before the recovery ladder gives up on the node
- verify: json_path(path="$.retries", matches="^(None|[0-9]+)$")
- semantics: `None` uses the run's `resilience.max_rephrase_attempts` setting
- verify: json_path(path="$.retries", equals="None")
- semantics: `0` disables reframing when a node delivers a file whose caller can use a partial artifact more cheaply than starting a fresh full-price session
- verify: count(subject="fresh reframe sessions after a failed file-delivery turn with retries 0", equals=0)
- semantics: `0` prevents reframes from multiplying a tight per-node timeout budget
- verify: count(subject="fresh reframe sessions that consume an additional per-node timeout budget after a failed turn with retries 0", equals=0)
- code: `workhorse/workhorse/runner/spec.py::AgentNode`
- detail: [Agent node field selection](agent-node-field-selection.md)

### invoke_retries
- type: `int | None`
- default: `None`
- required: false
- semantics: caps retries for transient rate-limit, overload, and network failures during the node's turn
- verify: json_path(path="$.invoke_retries", matches="^(None|[0-9]+)$")
- semantics: `None` uses the run's `resilience.max_invoke_retries` setting, whose days-long budget lets an unattended run ride out a provider outage
- verify: json_path(path="$.invoke_retries", equals="None")
- semantics: a spending-cap wait is not limited by this field because recovery waits for the cap to clear rather than stopping the turn
- code: `workhorse/workhorse/runner/spec.py::AgentNode`
- detail: [Agent node field selection](agent-node-field-selection.md)

### cwd
- type: `str | None`
- default: `None`
- verify: json_path(path="$.cwd", absent=true)
- required: false
- verify: json_path(path="$.cwd", absent=true)
- semantics: optional Jinja-rendered subprocess working directory that controls the agent CLI's CLAUDE.md and skills discovery and Git context
- semantics: an empty rendered directory or `None` inherits the process working directory
- verify: json_path(path="$.cwd", matches=".+")
- code: `workhorse/workhorse/runner/spec.py::AgentNode`
- detail: [Agent node field selection](agent-node-field-selection.md)

### add_dirs
- type: `list[str] | str`
- default: `[]`
- verify: count(subject="default additional-directory entries", equals=0)
- required: false
- semantics: additional Jinja-rendered directories are passed to the agent CLI as `--add-dir` flags, allowing a multi-repo workflow to read and write outside its working directory
- verify: count(subject="backend --add-dir arguments for rendered additional directories", equals=2)
- semantics: a bare variable may resolve to a native list
- verify: count(subject="--add-dir arguments from a native list-valued template", equals=2)
- code: `workhorse/workhorse/runner/spec.py::AgentNode`
- detail: [Agent node field selection](agent-node-field-selection.md)

### activity
- type: `str | None`
- default: `None`
- verify: json_path(path="$.activity", absent=true)
- required: false
- verify: json_path(path="$.activity", absent=true)
- semantics: optional Jinja-rendered human activity label stamped as `wf.activity` telemetry before the node runs
- semantics: lets a monitor display the run's current activity without knowing the workflow's vocabulary
- semantics: an empty rendered activity label is not published
- verify: emitted(event="wf.activity", count=1)
- code: `workhorse/workhorse/runner/spec.py::AgentNode`
- detail: [Agent node field selection](agent-node-field-selection.md)

### next
- type: `str | None`
- default: `None`
- verify: json_path(path="$.next", matches="^None$")
- required: false
- verify: json_path(path="$.next", absent=true)
- semantics: optional following node identifier carried by the node specification
- verify: json_path(path="$.next", equals="next_node")
- code: `workhorse/workhorse/runner/spec.py::AgentNode`
- detail: [Agent node field selection](agent-node-field-selection.md)

### OutputSpec
- type: Pydantic model
- semantics: names one extracted output
- verify: json_path(path="$.key", matches=".+")
- semantics: records whether its key must be present
- verify: json_path(path="$.required", matches="^(true|false)$")
- code: `workhorse/workhorse/runner/spec.py::OutputSpec`
- detail: [Output specification fields](output-specification-fields.md)

### key
- type: string
- required: true
- verify: json_path(path="$.key", matches=".+")
- semantics: output key requested from the agent response
- verify: created(subject="the declared output key in extracted results")
- code: `workhorse/workhorse/runner/spec.py::OutputSpec`
- detail: [Output specification fields](output-specification-fields.md)

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
- detail: [Output specification fields](output-specification-fields.md)

`workhorse.runner.__init__` intentionally exports no names. Consumers import the specific runner
modules rather than receiving a second public API from the package initializer.
