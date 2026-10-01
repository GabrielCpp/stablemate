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
author machines call live in the shared nodes package instead, and the nodes one subflow calls
live with that subflow. The node implementations remain
documented at their declaring modules rather than being duplicated here.

- code: `workflows/src/workhorse_workflows/author/main/nodes/__init__.py::__all__` @71db78d78b3d
- tests: `workflows/tests/author/test_workflow.py::test_every_flat_stage_is_directly_registered`
- detail: [Author main package](author-main-package.md)

## Fields

### __all__

The explicit export list is the complete import surface the main flow consumes from this
package. It includes the blueprint and the planner node.

- type: `list[str]`
- default: `['blueprint', 'plan_author_step']`
- required: true
- semantics: importing the package exposes exactly the blueprint and the planner node
- verify: count(subject="author main node exports", equals=2)
- code: `workflows/src/workhorse_workflows/author/main/nodes/__init__.py::__all__` @71db78d78b3d
