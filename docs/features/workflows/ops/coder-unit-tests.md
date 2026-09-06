---
type: runbook
slug: coder-unit-tests
title: Coder unit tests
---
# Coder unit tests

This pytest tier exercises the [Coder workflow composition root](../concepts/coder-workflow-composition-root.md),
its seven named flows, and their shared contracts against isolated temporary repositories. It drives real workflow
nodes, prompt rendering, artifact checkpointing, and Git operations; only agent turns are replaced through the
run-scoped `RunEnv.agent_runner` seam. The genesis and CI-repair tests likewise replace their external Farrier and
GitHub boundaries at named seams while retaining the nodes around them.

Specs live at `workflows/tests/coder/**/test_*.py`. The top-level tests cover Coder orchestration, commits,
telemetry, prompts, output contracts, and cross-flow session chains; subdirectories mirror the `genesis`, `dev`,
`review`, `docs`, `qa`, `fix`, `fix_ci`, and `shared` source groups. Add a test beside the flow or shared subject it
exercises, use `tests/coder/conftest.py` fixtures to create a temporary repository and drive a real flow, and script
only the agent reply or named external boundary needed by that case. Run one test with pytest's node selector, for
example `uv run pytest tests/coder/test_workflow.py::test_a_qa_mutation_requires_final_documentation_before_commit -q`.
This CLI tier has no browser controls, so it does not use book-derived UI locators. The repository `test` target
invokes `$(MAKE) -C workflows test`; this tier blocks that aggregate CI gate.

- driver: cli
- surfaces: [Coder workflow composition root](../concepts/coder-workflow-composition-root.md)
- code: `workflows/tests/coder/conftest.py::drive_flow`
- working-directory: workflows

## Steps

### provision-test-environment

- kind: service
- run: uv sync --all-packages
- working-directory: .
- timeout: 120
- health: `uv run pytest --version` exits 0 after the workspace environment is available
- provenance: derived

### run-coder-tests

- kind: run
- run: uv run pytest tests/coder -q -n auto --dist worksteal
- working-directory: workflows
- timeout: 120
- produces: pytest's terminal result for `tests/coder`
- verify: [workflow test target](../../../../workflows/Makefile)
- provenance: derived

### confirm-coder-tests-pass

- kind: verify
- run: uv run pytest tests/coder -q -n auto --dist worksteal
- working-directory: workflows
- timeout: 120
- provenance: derived
