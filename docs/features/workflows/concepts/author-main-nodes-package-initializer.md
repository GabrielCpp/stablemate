---
type: concept
slug: author-main-nodes-package-initializer
title: Author main nodes package initializer
---
# Author main nodes package initializer

The `workhorse_workflows.author.main.nodes` package groups by subject the deterministic work
only the main author flow calls, and establishes the blueprint for node registration. Importing
this package registers every node on the blueprint via their `@blueprint.node` decorators, and
re-exports both the blueprint and all node functions so the workflow composition can reach them
through one package import. The nodes several author machines call live in
`workhorse_workflows.author.shared.nodes` on their own blueprint.

The package contains four subject modules: `intake`, `stories`, `planner`, and `artifacts`. Each
groups nodes by the concern it addresses. The blueprint itself
is isolated in a submodule to break circular import cycles: subject modules import the blueprint to
register themselves, so the blueprint cannot import them back.

- code: `workflows/src/workhorse_workflows/author/main/nodes/__init__.py` @219a30d2fb7d
- code: `workflows/src/workhorse_workflows/author/main/nodes/_blueprint.py::blueprint` @6a9a28e94866
- tests: `workflows/tests/author/test_workflow.py::test_every_flat_stage_is_directly_registered`
- detail: [author main node exports](author-main-node-exports.md)
- detail: [author main package](author-main-package.md)
- detail: [author main composition layers](author-main-composition-layers.md)

## Blueprint

### blueprint
- type: `Blueprint`
- semantics: the registration point for the deterministic nodes only the main author flow calls
- code: `workflows/src/workhorse_workflows/author/main/nodes/_blueprint.py::blueprint` @6a9a28e94866

## Subject modules

The following modules contain decorated nodes grouped by subject:

### intake
- semantics: roadmap validation and advance. It checks that the approved roadmap owns one milestone and marks it authored
- contains: `validate_roadmap_milestone`, `mark_roadmap_authored`

### stories
- semantics: one story's mockup gate and the operator's notes on it
- contains: `check_story_feedback`, `check_mockup_needed`

### planner
- semantics: artifact-derived authoring unit planning — select the next work item at the planner level
- contains: `plan_author_step`

### artifacts
- semantics: the whole-run gates on what a run wrote
- contains: `validate_artifacts`, `verify_reconcile`

