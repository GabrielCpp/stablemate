---
type: flow
slug: workhorse-setup-and-run
title: Set up the prompt library and run a workflow
---
# Set up the prompt library and run a workflow

The first-time path from a bare `workhorse` install to a running workflow: point it at a prompt
library once via [`workhorse config`](../workhorse.md#config), then resolve and execute a named
workflow from that library via [`workhorse run`](../workhorse.md#run), which hands off to
[Workflow execution](../concepts/workflow.md#execution) for the actual graph walk.

- start: a `workhorse` install with **no** `library_dir` configured yet (`workhorse config show`
  would print nothing), and a prompt library on disk holding one or more workflows as
  `<library_dir>/workflows/<name>/workflow.yaml`.
- steps:
  1. [`workhorse config set-library <path>`](../workhorse.md#config) — resolves `<path>` (`~`-expanded,
     absolute) and persists it under the `library_dir` key via
     [`write_config_key`](../concepts/config.md#write_config_key), printing `library_dir=<path>`.
     This is the one-time step that makes bare workflow **names** (not paths) resolvable.
  2. *(optional)* [`workhorse config set-stablemate <path>`](../workhorse.md#config) — same shape,
     persisting `stablemate_dir` for workflow scripts that need `CODER_WORKSPACE`. Independent of
     step 1; skipped when a workflow's scripts don't touch the stablemate checkout.
  3. [`workhorse run <name> [<flow>]`](../workhorse.md#run) — resolves `<name>` as a bare library
     workflow (no `os.sep`, no `.yaml`/`.yml` suffix, not already an existing path) against the
     `library_dir` just configured, via `_resolve_library_dir` reading the
     [config file](../concepts/config.md) through
     [`get_config_value`](../concepts/config.md#get_config_value); missing `library_dir` (step 1
     never run, and `$WORKHORSE_LIBRARY_DIR` also unset) is a hard error at this step rather than
     later. Once resolved to `<library_dir>/workflows/<name>/workflow.yaml`, `run` selects the
     `--cli` [AgentBackend](../concepts/agent-backend.md), resolves fresh-start vs. resume, and hands
     the graph to execution.
  4. [Workflow execution](../concepts/workflow.md#execution) — `load_workflow` parses the resolved
     `workflow.yaml`, the run dir is seeded fresh or resumed in place, and `_step_loop` walks the
     graph node by node (checkpointing after each) until a `terminal`/`fail` node.
- end: the process exits `0` (reached `terminal`) or `1` (reached `fail`, or an unrecovered
  [`BackendInvocationError`](../concepts/workflow.md#resilience-fail-soft) /
  [`OutOfGasError`](../concepts/gas-tank.md)); [run artifacts](../run-artifacts.md) under
  `<runs_dir>/<name>-<run_id>` record the outcome and make the run resumable from where it stopped.
- verify: `workhorse/tests/test_workflow_resolution.py::test_library_dir_from_workhorse_config`,
  `workhorse/tests/test_workflow_resolution.py::test_bare_name_resolves_against_library`

