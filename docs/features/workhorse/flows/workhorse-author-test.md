---
type: flow
slug: workhorse-author-test
title: Author and run a workflow's test suite
---
# Author and run a workflow's test suite

The journey a workflow author follows to gain confidence in a `workflow.yaml` without touching a
real agent CLI or a real repo: write `tests/*.py` pytest files against
[`workhorse.testing`](../concepts/testing.md), which drives the **real** `workhorse` binary as a
subprocess against an isolated sandbox (PATH-shimmed agent/command calls, so the actual graph walk,
checkpointing, and [artifact](../run-artifacts.md) writing execute for real), then run that suite
with [`workhorse test <workflow_dir>`](../workhorse.md#test).

- start: a workflow directory `<workflow_dir>/workflow.yaml` with no `tests/` subdirectory yet, and
  `workhorse-agent[test]` (bundles `pytest`) installed alongside `workhorse`.
- steps:
  1. Create `<workflow_dir>/tests/test_*.py`. Each test constructs a
     [`WorkflowRun`](../concepts/testing.md#workflowrun-drive-one-workflow-run-against-a-sandbox)
     with the `workflow.yaml` path and an isolated sandbox directory (typically pytest's `tmp_path`),
     then calls
     [`WorkflowRun.mock_agent`](../concepts/testing.md#mock_agentnode_id-response-exit_code0-side_effectsnone) /
     [`mock_agent_sequence`](../concepts/testing.md#mock_agent_sequencenode_id-responses-exit_code0) to fix
     each `agent` node's response ahead of time, and
     [`WorkflowRun.mock_command`](../concepts/testing.md#mock_commandname-response) to fix the reply of
     any PATH command (`git`, `gh`, …) a `script` node shells out to — unmocked agent/command calls
     fall back to a harmless empty/zero-exit default with a `[test-shim] ⚠` warning rather than
     failing the test.
  2. Call [`WorkflowRun.run(...)`](../concepts/testing.md#run-paramsnone-flownone-cliclaude-timeout120-extra_envnone---runresult)
     to execute the run: it writes PATH shim executables (the [claude shim](../concepts/testing.md#the-claude-shim-_claude_shim)
     and, per `mock_command` call, a [generic command shim](../concepts/testing.md#the-generic-command-shim-_command_shim_template))
     under the sandbox's `.workhorse-test/bin/`, then invokes `workhorse --workflow <path>
     [<flow>] --runs-dir <sandbox>/.workhorse-test/runs [--params <json>]` as a real subprocess with
     that `bin/` prepended to `PATH` and the test-harness env vars set (`WORKHORSE_GAS`,
     `AGENT_MAX_REPHRASE_ATTEMPTS=0`, …), returning a
     [`RunResult`](../concepts/testing.md#runresult-the-outcome-of-one-workflowrunrun-call).
  3. Assert on the outcome — either directly on `RunResult` (`.passed()`, `.context()`,
     `.step_outputs(node_id)`, `.prompt(node_id)`, `.calls(command)`) or via the module-level
     [assertion helpers](../concepts/testing.md#assertion-helpers) (`assert_step_output`,
     `assert_prompt_contains`, `assert_command_called`, `assert_file`, `assert_file_contains`,
     `assert_json_file`).
  4. Run the suite with [`workhorse test <workflow_dir> [-k FILTER] [-v]`](../workhorse.md#test) —
     `_run_test` confirms `<workflow_dir>/tests/` exists (else errors), confirms `pytest` is
     importable (else prints the `workhorse-agent[test]` install hint), then invokes
     `pytest.main([<tests_dir>, ["-k", <FILTER>], ["-v"]])` in-process and exits with pytest's own
     return code.
- end: the process exits `0` when every test in `<workflow_dir>/tests/` passes, `1` if any test
  fails or `tests/` is missing/`pytest` isn't installed; the sandbox and its `.workhorse-test/`
  artifacts are left on disk (under pytest's `tmp_path`) for post-mortem inspection. Every consumer
  of this journey lives outside `stablemate` (each prompt library's own `<workflow>/tests/`), so no
  in-repo test exercises `workhorse test` end-to-end — see
  [`workhorse.testing`'s Consumers](../concepts/testing.md#consumers).

