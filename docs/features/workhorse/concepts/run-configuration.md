---
type: concept
slug: run-configuration
title: Per-run configuration
---
# Per-run configuration

`RunConfig` captures environment-derived settings once at the CLI boundary. The driver and
recovery ladder use this frozen value, so changing the process environment cannot change a run
already in progress. `AgentResilience` is the immutable policy passed to agent turns. A run with
no agent uses `NullBackend`, not a nullable collaborator. The shared selection concept separates
this lifecycle view from the field-focused view of the same value.

- code: `workhorse/workhorse/config_run.py::AgentResilience`
- code: `workhorse/workhorse/config_run.py::RunConfig`
- detail: [run configuration concept selection](run-configuration-concept-selection.md)
- detail: [stablemate config file](config.md)
- detail: [agent resilience concept selection](agent-resilience-concept-selection.md)
- detail: [agent resilience documentation selection](agent-resilience-documentation-selection.md)

## Fields

The first group belongs to `AgentResilience`; the second belongs to `RunConfig`. Both dataclasses
are frozen. Values are captured from environment mappings only by their `from_env` methods.

### field: max_output_retries
- type: `int`
- default: `2`
- required: true
- semantics: additional same-session attempts after an agent response cannot be parsed into the node outputs
- verify: json_path(path="$.max_output_retries", equals=2)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: max_invoke_retries
- type: `int`
- default: `60`
- required: true
- semantics: additional attempts for transient agent-CLI invocation failures
- verify: json_path(path="$.max_invoke_retries", equals=60)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: max_rephrase_attempts
- type: `int`
- default: `3`
- required: true
- semantics: fresh-session prompt reframes after invocation and output parsing still fail
- verify: json_path(path="$.max_rephrase_attempts", equals=3)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: max_compact_attempts
- type: `int`
- default: `2`
- required: true
- semantics: context-compaction recoveries before the ladder moves to reframing
- verify: json_path(path="$.max_compact_attempts", equals=2)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: result_timeout_s
- type: `float`
- default: `3600.0`
- required: true
- semantics: default wall-clock budget in seconds for one agent turn without a node timeout
- verify: json_path(path="$.result_timeout_s", equals=3600.0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: invoke_backoff_base_s
- type: `float`
- default: `15.0`
- required: true
- semantics: initial transient-invocation retry delay in seconds
- verify: json_path(path="$.invoke_backoff_base_s", equals=15.0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: invoke_backoff_cap_s
- type: `float`
- default: `1800.0`
- required: true
- semantics: maximum single transient-invocation retry delay in seconds
- verify: json_path(path="$.invoke_backoff_cap_s", equals=1800.0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: retry_wait_budget_s
- type: `float`
- default: `97305.0`
- required: true
- semantics: cumulative transient-retry sleep allowance for one agent-node visit in seconds
- verify: json_path(path="$.retry_wait_budget_s", equals=97305.0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: watchdog_grace_s
- type: `float`
- default: `120.0`
- required: true
- semantics: seconds beyond a turn timeout before the separate watchdog force-kills the process group
- verify: json_path(path="$.watchdog_grace_s", equals=120.0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: cap_default_wait_s
- type: `float`
- default: `3600.0`
- required: true
- semantics: fallback wait in seconds when a provider cap has no reported reset time
- verify: json_path(path="$.cap_default_wait_s", equals=3600.0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: cap_wait_margin_s
- type: `float`
- default: `120.0`
- required: true
- semantics: extra seconds added around a reported provider-cap reset wait
- verify: json_path(path="$.cap_wait_margin_s", equals=120.0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: cap_tick_s
- type: `float`
- default: `600.0`
- required: true
- semantics: maximum interval in seconds between notices while waiting for a provider cap
- verify: json_path(path="$.cap_tick_s", equals=600.0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: cap_probe_s
- type: `float`
- default: `7200.0`
- required: true
- semantics: single cap wait interval in seconds before probing whether the cap cleared early
- verify: json_path(path="$.cap_probe_s", equals=7200.0)
- semantics: zero selects one sleep through the reported reset instead of probing
- verify: json_path(path="$.cap_probe_s", equals=0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: max_cap_waits
- type: `int`
- default: `128`
- required: true
- semantics: maximum consecutive cap waits during one node visit
- verify: json_path(path="$.max_cap_waits", equals=128)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: cap_max_wait_s
- type: `float`
- default: `691200.0`
- required: true
- semantics: maximum one cap wait in seconds
- verify: json_path(path="$.cap_max_wait_s", equals=691200.0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: cap_wait_budget_s
- type: `float`
- default: `691320.0`
- required: true
- semantics: cumulative cap sleep allowance for one node visit in seconds
- verify: json_path(path="$.cap_wait_budget_s", equals=691320.0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: reframe_wait_budget_s
- type: `float`
- default: `60.0`
- required: true
- semantics: cumulative pause before fresh-session prompt reframes in seconds
- verify: json_path(path="$.reframe_wait_budget_s", equals=60.0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: exec_retry_max
- type: `int`
- default: `5`
- required: true
- semantics: additional subprocess-start attempts for executable replacement errors
- verify: json_path(path="$.exec_retry_max", equals=5)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: exec_retry_base_s
- type: `float`
- default: `1.0`
- required: true
- semantics: initial executable-start retry delay in seconds
- verify: json_path(path="$.exec_retry_base_s", equals=1.0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: exec_retry_cap_s
- type: `float`
- default: `8.0`
- required: true
- semantics: maximum executable-start retry delay in seconds
- verify: json_path(path="$.exec_retry_cap_s", equals=8.0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: exec_retry_wait_budget_s
- type: `float`
- default: `23.0`
- required: true
- semantics: cumulative executable-start retry sleep allowance for one node in seconds
- verify: json_path(path="$.exec_retry_wait_budget_s", equals=23.0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: heartbeat_every_s
- type: `float`
- default: `10.0`
- required: true
- semantics: interval in seconds at which the streaming loop reports turn liveness
- verify: json_path(path="$.heartbeat_every_s", equals=10.0)
- code: `workhorse/workhorse/config_run.py::AgentResilience`
- detail: [agent resilience tuning](agent-resilience-tuning.md)

### field: resilience
- type: `AgentResilience`
- default: a new default `AgentResilience`
- required: true
- semantics: recovery policy used by the run's agent runner
- verify: json_path(path="$.resilience.type", equals="AgentResilience")
- code: `workhorse/workhorse/config_run.py::RunConfig`
- detail: [run configuration field selection](run-configuration-field-selection.md)

### field: max_runtime_s
- type: `float`
- default: `0.0`
- required: true
- semantics: run wall-clock ceiling in seconds, where zero means unbounded
- verify: json_path(path="$.max_runtime_s", equals=0.0)
- code: `workhorse/workhorse/config_run.py::RunConfig`
- detail: [run configuration field selection](run-configuration-field-selection.md)

### field: await_poll_s
- type: `float`
- default: `15.0`
- required: true
- semantics: interval in seconds between stats of a file awaited by the workflow
- verify: json_path(path="$.await_poll_s", equals=15.0)
- code: `workhorse/workhorse/config_run.py::RunConfig`
- detail: [run configuration field selection](run-configuration-field-selection.md)

### field: max_transitions
- type: `int`
- default: `1000`
- required: true
- semantics: maximum state-machine transitions before the run is declared stuck
- verify: json_path(path="$.max_transitions", equals=1000)
- code: `workhorse/workhorse/config_run.py::RunConfig`
- detail: [run configuration field selection](run-configuration-field-selection.md)

### field: print_prompt
- type: `bool`
- default: `true`
- required: true
- semantics: whether the console prints each rendered prompt path without rendered variables
- verify: json_path(path="$.print_prompt", equals=true)
- code: `workhorse/workhorse/config_run.py::RunConfig`
- detail: [run configuration field selection](run-configuration-field-selection.md)

### field: model_override
- type: `str | None`
- default: `None`
- required: false
- semantics: run-level model fallback, with `AGENT_MODEL` taking precedence over `AGENT_CLAUDE_MODEL`
- verify: json_path(path="$.model_override", absent=true)
- code: `workhorse/workhorse/config_run.py::RunConfig`
- detail: [run configuration field selection](run-configuration-field-selection.md)

### field: backend
- type: `AgentBackend`
- default: `NullBackend()`
- required: true
- semantics: already-resolved agent backend
- verify: json_path(path="$.backend.type", matches=".+Backend")
- semantics: absence is represented by the null implementation rather than `None`
- verify: json_path(path="$.backend.type", equals="NullBackend")
- code: `workhorse/workhorse/config_run.py::RunConfig`
- tests: `workhorse/tests/test_backends.py::test_run_config_without_a_cli_holds_the_null_backend`
- detail: [run configuration field selection](run-configuration-field-selection.md)

### field: profile
- type: `str`
- default: `""`
- required: true
- semantics: selected named model profile, or empty for the top-level configuration tables
- verify: json_path(path="$.profile", equals="")
- code: `workhorse/workhorse/config_run.py::RunConfig`
- detail: [run configuration field selection](run-configuration-field-selection.md)

### field: workspace
- type: `str`
- default: `""`
- required: true
- semantics: configured working-tree path, or empty to use the process current directory
- verify: json_path(path="$.workspace", equals="")
- code: `workhorse/workhorse/config_run.py::RunConfig`
- detail: [run configuration field selection](run-configuration-field-selection.md)

### field: capture_transcripts
- type: `bool`
- default: `true`
- required: true
- semantics: whether each agent turn is retained under the run transcript directory
- verify: json_path(path="$.capture_transcripts", equals=true)
- code: `workhorse/workhorse/config_run.py::RunConfig`
- detail: [run configuration field selection](run-configuration-field-selection.md)

### field: transcript_max_bytes
- type: `int`
- default: `transcript.DEFAULT_MAX_BYTES`
- required: true
- semantics: maximum captured transcript size per turn
- verify: json_path(path="$.transcript_max_bytes", matches="^[1-9][0-9]*$")
- semantics: captures reaching the limit are truncated with a marker
- verify: json_path(path="$.truncated", equals=true)
- code: `workhorse/workhorse/config_run.py::RunConfig`
- detail: [run configuration field selection](run-configuration-field-selection.md)

## Methods

### AgentResilience.from_env
- sig: `AgentResilience.from_env(environ: Mapping[str, str] | None = None) -> AgentResilience`
- does: reads the `AGENT_*` resilience variables from the supplied mapping, or from the process environment when no mapping is supplied
- does: uses each field default when its input is absent or malformed
- does: rejects non-finite or disallowed duration values through the field-specific duration parser
- returns: an immutable resilience policy
- verify: json_path(path="$.max_invoke_retries", equals=7)
- code: `workhorse/workhorse/config_run.py::AgentResilience.from_env`
- tests: `workhorse/tests/test_guardrails.py::test_environment_variables`

### AgentResilience.with_overrides
- sig: `AgentResilience.with_overrides(**kwargs: Any) -> AgentResilience`
- does: replaces only the named resilience fields
- verify: unchanged(subject="original AgentResilience", except_fields=["max_invoke_retries"])
- returns: a new immutable resilience policy, leaving the original unchanged
- verify: unchanged(subject="original AgentResilience")
- code: `workhorse/workhorse/config_run.py::AgentResilience.with_overrides`

### RunConfig.from_env
- sig: `RunConfig.from_env(environ: Mapping[str, str] | None = None) -> RunConfig`
- does: captures resilience, runtime, polling, transition, model, workspace, and transcript settings from the supplied mapping, or from the process environment when no mapping is supplied
- does: gives `AGENT_MODEL` precedence over the legacy `AGENT_CLAUDE_MODEL` spelling
- returns: an immutable run configuration with a non-null backend implementation
- verify: json_path(path="$.model_override", equals="opus")
- code: `workhorse/workhorse/config_run.py::RunConfig.from_env`
- tests: `workhorse/tests/test_guardrails.py::test_environment_variables`
