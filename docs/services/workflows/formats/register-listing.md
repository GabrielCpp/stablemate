---
type: format
slug: register-listing
title: Register listing
---
# Register listing

The epic-edit planner reads the open records of the debt register as one block of text. The
`read_register_listing` node returns this value, and the planning prompt receives its `text`.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::RegisterListing` @f582abc9a049
- detail: [author shared schemas](../concepts/author-shared-schemas.md)
- detail: [debt register](../../ostler/concepts/the-debt-register.md)
- tests: `workflows/tests/author/test_workflow.py::test_the_epic_edit_planner_reads_the_register_listing_of_a_filed_record`

## Fields

### text
- type: string
- default: empty string
- required: false
- semantics: a header line `id`, `repo`, `area`, `status`, `pattern`, `summary` separated by tabs, then one tab-separated line per open record of every repository, or `no open records` when the register holds none
- verify: json_path(path="$.text", equals="no open records")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::RegisterListing` @f582abc9a049
