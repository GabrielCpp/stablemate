---
type: flow
slug: rename-a-story
title: Rename a story
---
# Rename a story

- start: an epic lists a story by its slug
- steps:
  - [ostler edit rename](../editing.md#ostler-edit-rename)
- end: the caller reads the diff and finds the story folder under its new slug
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^applied: 2 file\\(s\\) changed, 1 move\\(s\\)$")
- verify: absent(subject="edit-scratch/art/epics/0001-first/stories/sx")
- verify: contents(subject="edit-scratch/art/epics/0001-first/stories/sy/story.md", matches="slug: sy")
- fixture: [edit scratch repo](../fixtures/edit-scratch-repo.md) with an edit scratch repo whose book and story have not been edited yet
