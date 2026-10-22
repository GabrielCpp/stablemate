---
type: concept
slug: story-split-flow-concept-selection
title: Story-split flow concept selection
---
# Story-split flow concept selection

`StorySplitFlow` is one workflow, not a choice among three implementations. The flow requires
both `epic` and `operator_mode`: `epic` identifies the one epic to process, while
`operator_mode` controls whether blocked work awaits an operator immediately or can first use
the bounded automatic-resolution path.

Read [story-split flow inputs](story-split-flow-inputs.md) for the combined run-input contract,
[story-split input fields](story-split-input-fields.md) for the individual field definitions, and
[Author story-split subflow](story-split-subflow.md) for the full processing lifecycle. These are
complementary views of the same `StorySplitFlow`; none supersedes or ranks the others.

- rule: use the inputs concept to select a valid run configuration, the fields concept to inspect an individual input, and the subflow concept to understand processing after validation
