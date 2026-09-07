---
type: concept
slug: work-item-fields
title: Work item fields
---
# Work item fields

`WorkItem` is a generic workflow-owned queue record. Its declared fields are optional so a
workflow can use only the parts its queue needs, while extra top-level fields preserve its own
schema. The model in `workhorse/workhorse/worklist.py::WorkItem` does not define alternative
implementations or a preferred field: each field carries a different part of one item's meaning.

Choose `id` to identify an item for selection, marking, or pruning; `status` for the
caller-defined lifecycle interpreted by `Scheme`; `kind` to scope a mixed worklist; `order` to
override backend sequence order; and `payload` for generic nested workflow metadata. Refer to
`WorkItem` when documenting the record as a whole. A workflow may omit any declared field, so no
ranking applies among these members.

- code: `workhorse/workhorse/worklist.py::WorkItem`
- rule: choose the field matching the queue concern being represented; these fields are complementary members of one optional record, with no preferred or deprecated alternative
