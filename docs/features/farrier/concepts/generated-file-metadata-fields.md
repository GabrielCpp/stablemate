---
type: concept
slug: generated-file-metadata-fields
title: Generated-file metadata fields
---
# Generated-file metadata fields

The generated-file `metadata:` mapping is one provenance and recovery contract, not a choice
between alternative implementations. `generated_by` identifies managed output, `source` names
its portable library origin, `resolve` supplies the command that resolves that origin on the
current machine, and `do_not_edit` directs an editor through that recovery path before
regeneration. `tags` carries the source's capability labels only when the source declares them.

All five fields are current and complementary. Consumers should read the fields needed for their
task rather than select one as a replacement for another: ownership checks rely on
`generated_by`, `farrier source` uses `source` and `resolve`, the warning guides human edits, and
tag queries use `tags` when present.

- code: `farrier/farrier/renderer.py::skill_metadata_block`
- rule: use the fields together as one metadata contract; `tags` is omitted when the source has no tags, and no field supersedes another
