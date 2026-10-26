---
type: concept
slug: source-record-field-roles
title: Source record field roles
---
# Source record field roles

`Source` fields describe different aspects of one discovered library document; none is an
alternative representation that can replace another. Use `kind` to select the source category,
`path` to read the document from this machine, and `rel` for the content-root-relative POSIX path.
Use `id` as the normalized, stable source identifier for matching and lookup. `layer` identifies
the library layer that supplied a loaded source and is absent only on records constructed outside
the layer stack, such as test records. `local`, default `false`, marks a hand-written source that
is not in the library tree, so provenance lookups (`library_source_path`) use `rel` directly
instead of anchoring it at a `library/` segment. The source declaration does not rank these
fields: callers choose the field that matches the operation they are performing.

- code: `farrier/farrier/sources.py::Source` @3121386a99df
- rule: choose the field by its role: category for `kind`, local I/O for `path`, root-relative provenance for `rel`, stable matching and lookup for `id`, supplying-layer provenance for `layer`, and hand-written-vs-library provenance for `local`
- detail: [source record documentation roles](source-record-documentation-roles.md)
