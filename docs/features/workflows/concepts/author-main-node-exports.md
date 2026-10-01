---
type: concept
slug: author-main-node-exports
title: Author main node exports
---
# Author main node exports

The package initializer is the public export boundary for the deterministic nodes only the
Author main flow calls. Importing it imports each subject module, so every imported node is
registered on the [`author` blueprint](author-main-package.md#blueprint). The initializer only
re-exports those callables and does not add another registration target. The nodes several
author machines call live in the shared nodes package instead. The node implementations remain
documented at their declaring modules rather than being duplicated here.

- code: `workflows/src/workhorse_workflows/author/main/nodes/__init__.py::__all__` @219a30d2fb7d
- tests: `workflows/tests/author/test_workflow.py::test_every_flat_stage_is_directly_registered`
- detail: [Author main package](author-main-package.md)

## Fields

### __all__

The explicit export list is the complete import surface the main flow consumes from this
package. It includes the blueprint and the node callables from intake, planning, artifact
gates, and story processing.

- type: `list[str]`
- default: `['blueprint', 'check_mockup_needed', 'check_story_feedback', 'mark_roadmap_authored', 'plan_author_step', 'validate_artifacts', 'validate_roadmap_milestone', 'verify_reconcile']`
- required: true
- semantics: importing the package exposes exactly the blueprint and the listed deterministic node callables
- verify: count(subject="author main node exports", equals=8)
- code: `workflows/src/workhorse_workflows/author/main/nodes/__init__.py::__all__` @219a30d2fb7d
