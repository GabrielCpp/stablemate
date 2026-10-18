---
type: flow
slug: name-a-storys-branch
title: Name a story's branch
---
# Name a story's branch

- start: a script needs the branch a story's work lands on
- steps:
  - [ostler path branch](../planning.md#ostler-path-branch)
- end: the caller reads the branch name
- verify: exit_status(code=0)
- verify: stdout(matches="^alpha$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a story named alpha
