---
type: runbook
slug: research-unit-tests
title: Research unit tests
---
# Research unit tests

This pytest tier exercises the [Research workflow composition root](../concepts/research-workflow-composition-root.md)
through two complementary boundaries. `test_workflow.py` drives the complete state machine against a temporary
committed research-program repository: agent replies, detached-measurement nodes, and operator waits are scripted,
while manifest parsing, resource-envelope arithmetic, result publication, checkpoints, and Git result branches run
for real. `test_measure.py` drives the deterministic measurement adapter against real temporary job directories and
their supervisor/result artifacts; it covers fault-locus classification, declared-resource admission, submission
refusals, result classification, wake-file ordering, overrun triage, and stale-result cleanup.

Specs live at `workflows/tests/research/test_workflow.py` and `workflows/tests/research/test_measure.py`. Add a
state-machine scenario to `test_workflow.py` when it needs the workflow driver and its injected seams; add a
deterministic adapter scenario to `test_measure.py` when it can be expressed through on-disk job artifacts. Run one
scenario with pytest's node selector, for example `uv run pytest
tests/research/test_measure.py::test_an_overrun_past_a_fresh_threshold_goes_to_triage_once -q`. This CLI tier has
no browser controls, so it does not use book-derived UI locators. The repository `test` target invokes `$(MAKE) -C
workflows test`, so this tier blocks that aggregate CI gate.

- driver: cli
- surfaces: [Research workflow composition root](../concepts/research-workflow-composition-root.md)
- code: `workflows/Makefile::test`
- working-directory: workflows
- detail: [Workflow unit-test tiers](../concepts/workflow-unit-test-tiers.md)

## Steps

### provision-test-environment

- kind: service
- run: uv sync --all-packages
- working-directory: .
- timeout: 120
- health: `uv run pytest --version` exits 0 after the workspace environment is available
- provenance: derived

### run-research-tests

- kind: run
- run: uv run pytest tests/research -q -n auto --dist worksteal
- working-directory: workflows
- timeout: 120
- produces: pytest's terminal result for `tests/research`
- verify: [workflow test target](../../../../workflows/Makefile)
- provenance: derived

### confirm-research-tests-pass

- kind: verify
- run: uv run pytest tests/research -q -n auto --dist worksteal
- working-directory: workflows
- timeout: 120
- provenance: derived
