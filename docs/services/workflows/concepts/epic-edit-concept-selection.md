---
type: concept
slug: epic-edit-concept-selection
title: Epic edit concept selection
---
# Epic edit concept selection

The epic-edit concepts are complementary views of one `EpicEdit` workflow, not alternative
implementations. Read [author epic edit subflow](author-epic-edit-subflow.md) for the complete
reconciliation lifecycle and its public fields and states. Read [epic edit documentation
selection](epic-edit-documentation-selection.md) for the map between those views, [epic edit input
selection](epic-edit-input-selection.md) for field binding, and [epic edit invocation
selection](epic-edit-invocation-selection.md) for the choice between a story-edit handoff and a
direct request.

The class accepts both invocation contexts and resolves them in `EpicEdit.start`: an intent whose
epic is already set is retained, while an invocation without one must provide both direct `epic`
and `change` values. No concept is preferred or deprecated because each answers a different reader
question about that single machine.

- rule: select the concept by whether the reader needs the full lifecycle, the documentation map, field binding, or invocation context; no implementation ranking exists
