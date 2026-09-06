---
type: concept
slug: author-main-node-exports
title: Author main node exports
---
# Author main node exports

The package initializer is the public export boundary for the deterministic nodes used by the
Author main flow. Importing it imports each subject module, so every imported node is registered
on the shared [`author` blueprint](author-main-package.md#blueprint); the initializer itself only
re-exports those callables and does not add another registration target. The node implementations
remain documented at their declaring modules rather than being duplicated here.

- code: `workflows/src/workhorse_workflows/author/main/nodes/__init__.py::__all__`
- tests: `workflows/tests/author/test_workflow.py::test_every_flat_stage_is_directly_registered`
- detail: [Author main package](author-main-package.md)

## Fields

### __all__

The explicit export list is the complete import surface consumed by the main flow and by the
two edit flows that reuse its deterministic nodes. It includes the shared blueprint and the
node callables from configuration, intake, epic selection, planning, coverage, artifact gates,
and story processing.

- type: `list[str]`
- default: `['blueprint', 'adopt_backlog', 'check_mockup_needed', 'check_story_feedback', 'check_story_grounding', 'commit_author', 'load_config', 'mark_roadmap_authored', 'plan_author_step', 'prune_bullet', 'record_attempt', 'remove_story', 'seed_story', 'select_epic', 'select_epic_document', 'select_story', 'validate_artifacts', 'validate_coverage', 'validate_roadmap_milestone', 'validate_story', 'verify_integrity', 'verify_reconcile']`
- required: true
- semantics: importing the package exposes exactly the shared blueprint and the listed deterministic node callables
- verify: count(subject="author main node exports", equals=22)
- code: `workflows/src/workhorse_workflows/author/main/nodes/__init__.py::__all__`
