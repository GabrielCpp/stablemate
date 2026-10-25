---
type: concept
slug: generated-file-metadata-fields
title: Generated-file metadata fields
---
# Generated-file metadata fields

The generated-file `metadata:` mapping is one provenance and recovery contract, not a choice
between alternative implementations. `name` gives the library name of the source, `generated_by` identifies managed output, `source` names
its portable library origin, `resolve` supplies the command that resolves that origin on the
current machine, and `do_not_edit` directs an editor through that recovery path before
regeneration. `tags` carries the source's capability labels only when the source declares them.

All six fields are current and complementary. Consumers should read the fields needed for their
task rather than select one as a replacement for another: ownership checks rely on
`generated_by`, references resolve by `name`, `farrier source` uses `source` and `resolve`, the warning guides human edits, and
tag queries use `tags` when present.

- code: `farrier/farrier/renderer.py::skill_metadata_block` @3c56f2f75d1f
- rule: use the fields together as one metadata contract; `tags` is omitted when the source has no tags, and no field supersedes another
