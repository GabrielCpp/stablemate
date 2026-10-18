---
type: flow
slug: scaffold-a-node
title: Scaffold a node
---
# Scaffold a node

- start: a service has no widgets page
- steps:
  - [ostler scaffold](../editing.md#ostler-scaffold)
- end: the caller reads the path of the created page and finds the skeleton in it
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: contents(subject="edit-scratch/docs/features/demo/concepts/widgets.md", matches="type: concept")
- fixture: [edit scratch repo](../fixtures/edit-scratch-repo.md) with an edit scratch repo whose book and story have not been edited yet
