---
type: flow
slug: pick-the-next-story
title: Pick the next story
---
# Pick the next story

- start: an epic holds nine unfinished stories
- steps:
  - [ostler next story](../planning.md#ostler-next-story)
- end: the caller reads the runnable story's slug, path and unwritten sections
- verify: exit_status(code=0)
- verify: json_path(path="slug", equals="alpha")
- verify: json_path(path="status", equals="Not started")
- fixture: [plan scratch repo](../fixtures/plan-scratch-repo.md) with nine stories in order, the first with no dependency
