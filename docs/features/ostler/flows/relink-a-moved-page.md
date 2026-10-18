---
type: flow
slug: relink-a-moved-page
title: Relink a moved page
---
# Relink a moved page

- start: a story links a feature page by its path
- steps:
  - [ostler edit relink](../editing.md#ostler-edit-relink)
- end: the caller reads the diff of the story and finds the new path in it
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^applied: 1 file\\(s\\) changed, 0 move\\(s\\)$")
- verify: contents(subject="edit-scratch/docs/epics/0001-first/stories/sx/story.md", matches="features/area/record\\.md")
- fixture: [edit scratch repo](../fixtures/edit-scratch-repo.md) with an edit scratch repo whose book and story have not been edited yet
