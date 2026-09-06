---
type: concept
slug: run-configuration
title: Per-run configuration
---
# Per-run configuration

`RunConfig` captures environment-derived settings once at the CLI boundary. The driver and
recovery ladder then use this frozen value, so a running process does not change behavior because
the environment changes. The absent agent collaborator is represented by `NullBackend`, not by a
nullable field.

- code: `workhorse/workhorse/config_run.py::RunConfig`
- detail: [stablemate config file](config.md)

`RunConfig` carries `resilience`, `max_runtime_s` (`0.0` means unbounded), `await_poll_s`
(`15.0`), `max_transitions` (`1000`), `print_prompt` (`true`), `model_override` (`None`),
`backend` (`NullBackend` by default), `profile` (empty), `workspace` (empty),
`capture_transcripts` (`true`), and `transcript_max_bytes` (the transcript module default).
`AgentResilience` carries the retry, timeout, cap, reframe, execution-retry, and heartbeat
limits used by agent turns.

### AgentResilience.from_env
- sig: `AgentResilience.from_env(environ: Mapping[str, str] | None = None) -> AgentResilience`
- does: reads each `AGENT_*` resilience variable from the supplied mapping or process environment
- does: falls back to the dataclass default for missing, malformed, non-finite, or disallowed duration values
- returns: an immutable resilience policy
- code: `workhorse/workhorse/config_run.py::AgentResilience.from_env`
- tests: `workhorse/tests/test_guardrails.py::test_environment_variables`

### AgentResilience.with_overrides
- sig: `AgentResilience.with_overrides(**kwargs: Any) -> AgentResilience`
- returns: a copy with only the named resilience fields replaced
- code: `workhorse/workhorse/config_run.py::AgentResilience.with_overrides`

### RunConfig.from_env
- sig: `RunConfig.from_env(environ: Mapping[str, str] | None = None) -> RunConfig`
- does: captures resilience, runtime, polling, transition, model, workspace, and transcript settings from the supplied mapping or process environment
- does: gives `AGENT_MODEL` precedence over the legacy `AGENT_CLAUDE_MODEL` spelling
- returns: an immutable run configuration with a non-null backend implementation
- code: `workhorse/workhorse/config_run.py::RunConfig.from_env`
- tests: `workhorse/tests/test_guardrails.py::test_environment_variables`
