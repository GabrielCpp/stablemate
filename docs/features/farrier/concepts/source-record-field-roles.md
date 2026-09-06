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
the layer stack, such as test records. The source declaration does not rank these fields: callers
choose the field that matches the operation they are performing.

- code: `farrier/farrier/sources.py::Source`
- rule: choose the field by its role: category for `kind`, local I/O for `path`, root-relative provenance for `rel`, stable matching and lookup for `id`, and supplying-layer provenance for `layer`
- detail: [source record documentation roles](source-record-documentation-roles.md)
