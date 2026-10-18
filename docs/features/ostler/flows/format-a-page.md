---
type: flow
slug: format-a-page
title: Format a page
---
# Format a page

- start: a page has its frontmatter keys out of order and a wikilink in its prose
- steps:
  - [ostler fmt check](../editing.md#ostler-fmt-check)
  - [ostler fmt](../editing.md#ostler-fmt)
- end: the caller reads that the page was reformatted and finds the wikilink turned into a link
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^reformatted: docs/features/demo/tidy\\.md$")
- verify: contents(subject="edit-scratch/docs/features/demo/tidy.md", matches="See \\[rec\\]\\(rec\\) for the record")
- fixture: [edit scratch repo](../fixtures/edit-scratch-repo.md) with an edit scratch repo whose book and story have not been edited yet
