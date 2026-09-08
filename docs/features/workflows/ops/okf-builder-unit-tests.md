---
type: runbook
slug: okf-builder-unit-tests
title: OKF-builder unit tests
---
# OKF-builder unit tests

This pytest tier exercises the [OKF-builder workflow composition root](../concepts/okf-builder-workflow-composition-root.md)
and its preparation, worklist, checkpoint, coverage, prompt, and walkthrough boundaries against temporary Git
repositories. The `booked`, `unbooked`, and `dirty` fixtures construct source and feature-book states that real
workflow nodes inspect; agent replies and operator waits are the only scripted boundaries. The suite also renders
repair prompts and reads Ostler's doctor implementation to detect unclassified documentation defects.

Specs live at `workflows/tests/okf_builder/test_*.py`. Add a test beside the bounded workflow concern it covers and
use `tests/okf_builder/conftest.py` fixtures to construct the repository state rather than duplicating a feature
book. Run one test with pytest's node selector, for example `uv run pytest
tests/okf_builder/test_checkpoint.py::test_a_warning_is_a_standing_finding -q`. This CLI tier has no browser
controls, so it does not use book-derived UI locators. The repository test target invokes `$(MAKE) -C workflows
test`; this tier blocks that aggregate CI gate.

- driver: cli
- surfaces: [OKF-builder workflow composition root](../concepts/okf-builder-workflow-composition-root.md)
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

### run-okf-builder-tests

- kind: run
- run: uv run pytest tests/okf_builder -q -n auto --dist worksteal
- working-directory: workflows
- timeout: 120
- produces: pytest's terminal result for `tests/okf_builder`
- verify: [workflow test target](../../../../workflows/Makefile)
- provenance: derived

### confirm-okf-builder-tests-pass

- kind: verify
- run: uv run pytest tests/okf_builder -q -n auto --dist worksteal
- working-directory: workflows
- timeout: 120
- provenance: derived
