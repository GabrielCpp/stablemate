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

- code: `workhorse/tests/conftest.py`
- code: `workhorse/tests/conftest.py::_no_base_fetch`
- code: `workhorse/tests/conftest.py::_no_real_config`
- code: `workhorse/tests/_fakes.py::present`
- code: `workhorse/tests/_fakes.py::FakeBackend`
- code: `workhorse/tests/_fakes.py::FakeClock`
- code: `workhorse/tests/_fakes.py::RecordingTelemetry`
- code: `workhorse/tests/_fakes.py::fake_groom`
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
