---
type: flow
slug: find-a-storys-page
title: Find a story's page
---
# Find a story's page

- start: a script needs a story's page
- steps:
  - [ostler path story](../planning.md#ostler-path-story)
- end: the caller reads the page path
- verify: exit_status(code=0)
- verify: stdout(matches="^.*/plan-scratch/art/epics/0001-first/stories/alpha/story\\.md$")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with a story named alpha
