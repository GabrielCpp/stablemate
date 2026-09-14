---
type: concept
slug: author-epic-selector-roles
title: Author epic selector roles
---
# Author epic selector roles

The Author main flow uses two current selectors in sequence rather than alternative implementations.
`select_epic_document` is the selector for the milestone-level documentation pass: it returns the
first queued epic without an `epic.md` or researched seeds. Once every queued epic has those
inputs, the flow moves to story authoring and `select_epic` returns the first epic that Ostler does
not consider fully authored. The latter verdict requires the epic document, at least one listed
story, and written required prose in every listed story document.

Neither selector supersedes the other. The documentation selector remains the correct choice while
the authoring inputs are incomplete; the fully-authored selector is the correct choice only after
that pass has completed. Both use the roadmap-owned milestone queue when a roadmap is supplied,
which keeps an authoring run from selecting an epic owned by another roadmap.

- rule: use `select_epic_document` to finish each queued epic's `epic.md` and researched seeds before story authoring; then use `select_epic` to resume the first epic Ostler does not report as fully authored
