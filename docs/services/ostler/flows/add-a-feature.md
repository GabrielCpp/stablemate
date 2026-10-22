---
type: flow
slug: add-a-feature
title: Add a feature
---
# Add a feature

- start: a plan repo holds two features
- steps:
  - [ostler create feature](../planning.md#ostler-create-feature)
- end: the caller reads the created feature's id
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="message", matches="^created feature 'gamma'")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with two features
