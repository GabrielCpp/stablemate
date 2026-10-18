---
type: flow
slug: stamp-a-page
title: Stamp a page
---
# Stamp a page

- start: a page cites a source file in two code bullets
- steps:
  - [ostler stamp](../editing.md#ostler-stamp)
- end: the caller reads how many citations were stamped and finds the digests in the page
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^docs/features/demo/cli\\.md: 2 stamped$")
- verify: contents(subject="edit-scratch/docs/features/demo/cli.md", matches="src/demo\\.py::greet@[0-9a-f]+")
- fixture: [edit scratch repo](../fixtures/edit-scratch-repo.md) with an edit scratch repo whose book and story have not been edited yet
