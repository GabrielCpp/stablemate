---
type: flow
slug: carve-a-large-page-into-fragments
title: Carve a large page into fragments
---
# Carve a large page into fragments

- start: a page is past the page size limit
- steps:
  - [ostler edit carve fragments](../editing.md#ostler-edit-carve-fragments)
- end: the caller reads how many fragment pages were made and finds the page small again
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^carve docs/services/demo/concepts/ledger\\.md: 2 fragment page\\(s\\) from 1 section\\(s\\)$")
- verify: contents(subject="edit-scratch/docs/services/demo/concepts/ledger-rules-rule-1.md", matches="(?m)^type: fragment$")
- fixture: [edit scratch repo](../fixtures/edit-scratch-repo.md) with an edit scratch repo whose book and story have not been edited yet
