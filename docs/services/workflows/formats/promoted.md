---
type: format
slug: promoted
title: Promoted record result
---
# Promoted record result

The story-mode promotion result names the register record that was closed as promoted and the
reason the close recorded. The [debt register](../../ostler/concepts/the-debt-register.md) keeps
the closed record on its shelf with that status and reason.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Promoted` @b91d7be769de
- detail: [author shared schemas](../concepts/author-shared-schemas.md)
- detail: [promoting a record](../concepts/promote-a-record.md)
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_promotes_an_open_record_and_does_not_commit_the_code_repo`

## Fields

### record_id
- type: string
- default: empty string
- required: false
- semantics: id of the register record that was closed as promoted
- verify: json_path(path="$.record_id", equals="b1")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Promoted` @b91d7be769de
- detail: [promoted record field roles](../concepts/promoted-field-roles.md)

### reason
- type: string
- default: empty string
- required: false
- semantics: the reason written on the closed record, `promoted to story <story> in epic <epic>`
- verify: json_path(path="$.reason", equals="promoted to story users-can-sign-in in epic accounts")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Promoted` @b91d7be769de
- detail: [promoted record field roles](../concepts/promoted-field-roles.md)
