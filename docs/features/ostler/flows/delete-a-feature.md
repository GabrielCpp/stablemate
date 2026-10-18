---
type: flow
slug: delete-a-feature
title: Delete a feature
---
# Delete a feature

- start: a feature was recorded by mistake
- steps:
  - [ostler delete feature](../planning.md#ostler-delete-feature)
- end: the caller sees the feature deleted
- verify: exit_status(code=0)
- verify: stdout(matches="^deleted feature 'beta'$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with two features
