---
type: runbook
slug: author-unit-tests
title: author-unit-tests
---
# Author unit tests

This pytest tier exercises the [Author workflow composition root](../concepts/author-workflow-composition-root.md)
and its named author subflows against temporary repositories. It runs real author nodes and Ostler graph
operations; only agent turns and waits at operator gates are scripted. The shared `repo` fixture initializes a
temporary Git repository, makes it the working directory, and provides a generated grill command, while
flow-level fixtures replace the engine's agent-runner seam and write the artifacts claimed by their replies.

Specs live at `workflows/tests/author/**/test_*.py`. Add coverage beside the flow or node it exercises, use the
shared fixtures from `tests/author/conftest.py`, and make a scripted agent create every artifact the subsequent
real node reads. Run one test with pytest's node selector, for example
`uv run pytest tests/author/test_config.py::test_epic_authoring_requires_an_approved_roadmap -q`; this tier has no
browser controls, so it does not use book-derived UI locators. The repository `test` target invokes
`$(MAKE) -C workflows test`, so this tier blocks that aggregate CI gate.

- driver: cli
- surfaces: [Author workflow composition root](../concepts/author-workflow-composition-root.md)
- code: `workflows/Makefile::test`
- working-directory: workflows

## Steps

### provision-test-environment

- kind: service
- run: uv sync --all-packages
- working-directory: .
- timeout: 120
- health: `uv run pytest --version` exits 0 after the workspace environment is available
- provenance: derived

### run-author-tests

- kind: run
- run: uv run pytest tests/author -q -n auto --dist worksteal
- working-directory: workflows
- timeout: 120
- produces: pytest's terminal result for `tests/author`
- verify: [workflow test target](../../../../workflows/Makefile)
- provenance: derived

### confirm-author-tests-pass

- kind: verify
- run: uv run pytest tests/author -q -n auto --dist worksteal
- working-directory: workflows
- timeout: 120
- provenance: derived
