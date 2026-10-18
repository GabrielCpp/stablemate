---
type: flow
slug: check-a-page-is-canonical
title: Check a page is canonical
---
# Check a page is canonical

- start: a page has its frontmatter keys out of order and a wikilink in its prose
- steps:
  - [ostler fmt check](../editing.md#ostler-fmt-check)
- end: the caller reads which page would be reformatted and that the exit status is 1
- verify: exit_status(code=1)
- verify: stdout(matches="(?m)^would reformat: docs/features/demo/tidy\\.md$")
- fixture: [edit scratch repo](../fixtures/edit-scratch-repo.md) with an edit scratch repo whose book and story have not been edited yet
