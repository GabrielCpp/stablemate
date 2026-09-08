---
type: concept
slug: author-shared-survey-blueprint
title: Author shared survey blueprint
---
# Author shared survey blueprint

This module owns the single `Blueprint("surveyor")` instance that registers the survey
nodes shared by the [author surveyor](author-surveyor-subflow.md) and the
[author parity surveyor subflow](author-parity-surveyor-subflow.md). Importing
`workhorse_workflows.author.shared.survey` decorates every node in that package
against this object, and the parity surveyor's own freeze and emission nodes register
on the same blueprint beside them. The author composition root imports the object as
`survey_blueprint` and folds it into the merged registry through `add_blueprints`,
alongside the main `Blueprint("author")` defined under
[`main/nodes/_blueprint.py`](../../../../workflows/src/workhorse_workflows/author/main/nodes/_blueprint.py).

Two graphs, one registration surface. The surveyor and the parity surveyor are
separate state machines that happen to ship in the same package, and keeping their
registration on a distinct blueprint lets a reader of `surveyor/flow.py` see which
nodes belong to it without scanning the main author's. `Registry.add_blueprints`
merges the survey blueprint with the main author blueprint into one index, so node
names must still be globally unique across the pair — which is why the surveyor's
start node is `load_survey_config` rather than the author flow's `load_config`.

The shared node inventory, unit-walking, record-validation, and coverage-gate
operations are described in the [author shared survey library](survey-shared-library.md).
The surveyor's own non-shared nodes (its planning, splitting, partition, and
artifact-emission nodes) and the parity surveyor's own non-shared nodes (its baseline
freeze and backlog-emission nodes) are documented in their respective subflow concepts
and import this blueprint to register on it.

- code: `workflows/src/workhorse_workflows/author/shared/survey/blueprint.py::blueprint`
- rule: the same `blueprint` instance is the registration object for both the surveyor and parity-surveyor flows; a node reaching either subflow resolves through this single object, and a node name shared across both flows is a collision, not a coincidence
- detail: [author shared survey library](survey-shared-library.md)
- detail: [author parity surveyor subflow](author-parity-surveyor-subflow.md)
- detail: [author surveyor subflow](author-surveyor-subflow.md)
