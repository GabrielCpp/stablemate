---
type: flow
slug: unblock-a-story
title: Unblock a story
---
# Unblock a story

- start: a story was set aside with a Blocked status
- steps:
  - [ostler unblock](../planning.md#ostler-unblock)
- end: the caller reads how many stories the command returned to Not started
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="message", matches="^unblocked 1")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a story whose status starts with Blocked
