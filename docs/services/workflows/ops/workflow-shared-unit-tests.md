---
type: runbook
slug: workflow-shared-unit-tests
title: Workflow shared unit tests
---
# Workflow shared unit tests

This pytest tier covers cross-workflow contracts and kit helpers outside the individual workflow
directories: prompt static contracts, credential scoping, JSON-with-comments parsing, workspace
checkout, scoped commits, and the no-give-up guard. It drives no browser or running service.

Specs live at `workflows/tests/test_*.py`, with `workflows/tests/_fakes.py` providing the shared
scripted-agent double. Add a test to that directory when it verifies a cross-workflow or kit
contract; place a workflow-specific test in its matching subdirectory instead. Run one test with
its pytest node selector, for example `uv run pytest tests/test_kit_jsonio.py::test_a_url_in_a_string_is_not_a_comment -q`.
This CLI tier has no UI controls, so it does not use book-derived locators. `make test` at the
repository root runs `$(MAKE) -C workflows test`; the workflow package test target runs this tier
and blocks the aggregate CI gate.

- driver: cli
- surfaces: [loop-runner workflow](../concepts/loop-runner-workflow.md)
- code: `workflows/Makefile::test` @4f2f1208042e
- working-directory: workflows
- detail: [Workflow unit-test tiers](../concepts/workflow-unit-test-tiers.md)

## Steps

### provision-test-environment

- kind: service
- run: uv sync --all-packages
- working-directory: .
- timeout: 120
- health: `uv run pytest --version` exits 0 after the workspace environment is available

### run-shared-workflow-tests

- kind: run
- run: uv run pytest tests/test_*.py -q -n auto --dist worksteal
- working-directory: workflows
- timeout: 120
- produces: pytest terminal result for `tests/test_*.py`
- verify: [workflow test target](../../../../workflows/Makefile)

### confirm-shared-workflow-tests-pass

- kind: verify
- run: uv run pytest tests/test_*.py -q -n auto --dist worksteal
- working-directory: workflows
- timeout: 120
