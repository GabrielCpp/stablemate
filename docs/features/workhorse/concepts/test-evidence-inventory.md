---
type: concept
slug: test-evidence-inventory
title: workhorse test evidence inventory
---
# workhorse test evidence inventory

The engine's dependency-free test suite is the executable evidence for the contracts in this
book. Each module below is the bounded evidence set for the behavior named by its neighboring
concept or surface: module citations intentionally preserve the test module as a whole where its
symbols exercise one shared seam. The suite-wide fixtures and doubles are also recorded because
they define the substitution boundary used by the tests.

`test_guardrails.py` is the one test file in this suite that doubles as a standalone script: its
[`main`](#main) runs every guardrail test in sequence and returns `0` when all pass
or `1` on the first failure, so the file can be invoked with `python workhorse/tests/test_guardrails.py`
for a quick local check of the failure-classification and configuration surfaces without going
through pytest.

- code: `workhorse/tests/conftest.py`
- code: `workhorse/tests/conftest.py::_no_base_fetch`
- code: `workhorse/tests/conftest.py::_no_real_config`
- code: `workhorse/tests/_fakes.py::present`
- code: `workhorse/tests/_fakes.py::FakeBackend`
- code: `workhorse/tests/_fakes.py::FakeClock`
- code: `workhorse/tests/_fakes.py::RecordingTelemetry`
- code: `workhorse/tests/_fakes.py::fake_groom`
- code: `workhorse/tests/test_otel.py::FakeSpan`
- code: `workhorse/tests/test_otel.py::FakeTracer`
- code: `workhorse/tests/test_otel.py::FakeTraceApi`
- code: `workhorse/tests/test_otel.py::FakeInstrument`
- code: `workhorse/tests/test_otel.py::FakeMeter`
- code: `workhorse/tests/test_otel.py::FakeTelemetry`
- code: `workhorse/tests/test_otel.py::installed`
- code: `workhorse/tests/test_guardrails.py::main`
- code: `workhorse/tests/test_run_terminal.py::Greeting`
- code: `workhorse/tests/test_run_terminal.py::Recorder`
- tests: `workhorse/tests/conftest.py`
- tests: `workhorse/tests/_fakes.py::present`
- tests: `workhorse/tests/_fakes.py::FakeBackend`
- tests: `workhorse/tests/_fakes.py::FakeClock`
- tests: `workhorse/tests/_fakes.py::RecordingTelemetry`
- tests: `workhorse/tests/_fakes.py::fake_groom`
- tests: `workhorse/tests/test_activity.py`
- tests: `workhorse/tests/test_agent_cap.py`
- tests: `workhorse/tests/test_agent_exec_retry.py`
- tests: `workhorse/tests/test_agent_recovery.py`
- tests: `workhorse/tests/test_artifacts_fresh.py`
- tests: `workhorse/tests/test_backends.py`
- tests: `workhorse/tests/test_body_render.py`
- tests: `workhorse/tests/test_config_harness_env.py`
- tests: `workhorse/tests/test_console_script.py`
- tests: `workhorse/tests/test_context_manifest.py`
- tests: `workhorse/tests/test_control_channel.py`
- tests: `workhorse/tests/test_control_command.py`
- tests: `workhorse/tests/test_failure_handoff.py`
- tests: `workhorse/tests/test_flavor_render.py`
- tests: `workhorse/tests/test_gates.py`
- tests: `workhorse/tests/test_gitstate.py`
- tests: `workhorse/tests/test_guardrails.py`
- tests: `workhorse/tests/test_idempotency.py`
- tests: `workhorse/tests/test_inbox_command.py`
- tests: `workhorse/tests/test_inbox.py`
- tests: `workhorse/tests/test_job.py`
- tests: `workhorse/tests/test_json_parse.py`
- tests: `workhorse/tests/test_livesource.py`
- tests: `workhorse/tests/test_logsetup.py`
- tests: `workhorse/tests/test_model_resolution.py`
- tests: `workhorse/tests/test_node_timeout.py`
- tests: `workhorse/tests/test_otel.py`
- tests: `workhorse/tests/test_pyflow_graph.py`
- tests: `workhorse/tests/test_pyflow.py`
- tests: `workhorse/tests/test_records.py`
- tests: `workhorse/tests/test_redact.py`
- tests: `workhorse/tests/test_references.py`
- tests: `workhorse/tests/test_reload_reentry.py`
- tests: `workhorse/tests/test_reload_request.py`
- tests: `workhorse/tests/test_resume_auto.py`
- tests: `workhorse/tests/test_retired_params.py`
- tests: `workhorse/tests/test_run_budget.py`
- tests: `workhorse/tests/test_run_options.py`
- tests: `workhorse/tests/test_run_terminal.py`
- tests: `workhorse/tests/test_scratch.py`
- tests: `workhorse/tests/test_session_chain.py`
- tests: `workhorse/tests/test_stream_subprocess.py`
- tests: `workhorse/tests/test_supervisor.py`
- tests: `workhorse/tests/test_templates_resilient.py`
- tests: `workhorse/tests/test_transcript.py`
- tests: `workhorse/tests/test_turnkey.py`
- tests: `workhorse/tests/test_turn_records.py`
- tests: `workhorse/tests/test_usage.py`
- tests: `workhorse/tests/test_worklist.py`

## Methods

### main
- sig: `main() -> int`
- does: prints a banner, runs every guardrail test in sequence, prints a summary listing the improvements the guardrails deliver, and returns 0
- does: catches any exception raised by a guardrail test, prints the failure to stderr with a traceback, and returns 1
- returns: `0` when every guardrail test passes
- verify: json_path(path="$.returncode", equals=0)
- returns: `1` if any guardrail test raises
- verify: json_path(path="$.returncode", equals=1)
- code: `workhorse/tests/test_guardrails.py::main`

The runner script reuses the same functions pytest discovers — invoking the file as
`python workhorse/tests/test_guardrails.py` exercises the same surface that
`pytest workhorse/tests/test_guardrails.py` does, with the only difference being the banner and
exit-code shell around the calls.

Two further fixtures carry this suite's terminal-status contract — the order in which `run_pyflow`
stamps `end_run` against the `finally` backstop:

- `workhorse/tests/test_run_terminal.py::Greeting` — a one-state flow whose `start` returns
  `Done(None)`. It exists only to satisfy the registry's entry lookup; the tests patch
  `pyflow.run.drive` and the class body never runs.
- `workhorse/tests/test_run_terminal.py::Recorder` — a subclass of `workhorse.otel._NullTelemetry`
  that overrides only the two signals the order-sensitive assertions read. `enabled` always
  returns `True`, so the recorder's view is exercised the way an active host's is; `end_run`
  appends `(status, error)` to `ended` in arrival order. The first-wins rule that keeps a
  status out of `otel._NullTelemetry`'s body lives in production code and is asserted
  separately in `test_otel.py` — re-encoding it here would let one test pass by re-using the
  other's assumption.
