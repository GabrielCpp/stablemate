---
type: concept
slug: author-main-nodes-package-initializer
title: Author main nodes package initializer
---
# Author main nodes package initializer

The `workhorse_workflows.author.main.nodes` package groups deterministic work by subject and
establishes the shared blueprint for node registration. Importing this package registers every
node on the blueprint via their `@blueprint.node` decorators, and re-exports both the blueprint
and all node functions so the workflow composition can reach them through one package import.

The package contains seven subject modules — `config`, `intake`, `epics`, `stories`, `planner`,
`coverage`, and `artifacts` — each grouping nodes by the concern they address. The blueprint itself
is isolated in a submodule to break circular import cycles: subject modules import the blueprint to
register themselves, so the blueprint cannot import them back.

- code: `workflows/src/workhorse_workflows/author/main/nodes/__init__.py`
- code: `workflows/src/workhorse_workflows/author/main/nodes/_blueprint.py::blueprint`
- tests: `workflows/tests/author/test_workflow.py::test_every_flat_stage_is_directly_registered`
- detail: [author main node exports](author-main-node-exports.md)
- detail: [author main package](author-main-package.md)
- detail: [author main composition layers](author-main-composition-layers.md)

## Blueprint

### blueprint
- type: `Blueprint`
- semantics: the shared registration point for all author main deterministic nodes
- code: `workflows/src/workhorse_workflows/author/main/nodes/_blueprint.py::blueprint`

## Subject modules

The following modules contain decorated nodes grouped by subject:

### config
- semantics: workflow configuration loading — the run's input parameters and settings
- contains: `load_config`

### intake
- semantics: roadmap validation and adoption — verify provenance and retain story-mode bullet adoption
- contains: `validate_roadmap_milestone`, `adopt_backlog`, `mark_roadmap_authored`

### epics
- semantics: epic selection — pick the next epic to work on
- contains: `select_epic`, `select_epic_document`

### stories
- semantics: story processing — lifecycle from seeding through validation and feedback
- contains: `seed_story`, `select_story`, `validate_story`, `check_story_grounding`, `check_story_feedback`, `check_mockup_needed`, `prune_bullet`, `record_attempt`, `remove_story`

### planner
- semantics: artifact-derived authoring unit planning — select the next work item at the planner level
- contains: `plan_author_step`

### coverage
- semantics: coverage validation — verify that an epic's stories cover all its requirements
- contains: `validate_coverage`

### artifacts
- semantics: artifact gates and git tail — whole-run gates, commit, and push the shipped artifacts
- contains: `validate_artifacts`, `verify_integrity`, `verify_reconcile`, `commit_author`

