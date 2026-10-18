---
type: flow
slug: move-pages-into-their-context-folder
title: Move pages into their context folder
---
# Move pages into their context folder

- start: a service keeps its concept pages beside its other pages
- steps:
  - [ostler edit migrate context](../editing.md#ostler-edit-migrate-context)
- end: the caller reads the moves and finds every link to a moved page pointing at the new place
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^applied: 2 file\\(s\\) changed, 2 move\\(s\\)$")
- verify: absent(subject="edit-scratch/docs/features/demo/idea.md")
- verify: contents(subject="edit-scratch/docs/features/demo/entries.md", matches="\\(concepts/idea\\.md\\)")
- fixture: [edit scratch repo](../fixtures/edit-scratch-repo.md) with an edit scratch repo whose book and story have not been edited yet
