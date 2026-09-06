---
type: concept
slug: source-record
title: Library source record
---
# Library source record

`Source` is the immutable record passed from library discovery into matching, lookup, and
rendering. Its `id` is derived from the source's root-relative location; `rel` preserves the
machine-independent POSIX path used by selection and provenance, while `path` retains the actual
filesystem path used to read content. A record may carry the layer that supplied it so later
resolution can explain shadowing and provenance. The compatibility facade continues to expose this
same record as `farrier.install.Source`; its declaration remains in `sources.py`.

- code: `farrier/farrier/sources.py::Source`
- detail: [library layer](library-layer.md)

## Fields

### field: kind
- type: `str`
- required: true
- semantics: identifies the source category being loaded, such as `skill`, `prompt`, or `policy`
- code: `farrier/farrier/sources.py::Source`

### field: path
- type: `Path`
- required: true
- semantics: filesystem path of the source document
- code: `farrier/farrier/sources.py::Source`

### field: rel
- type: `str`
- required: true
- semantics: POSIX path relative to the content root
- code: `farrier/farrier/sources.py::Source`

### field: id
- type: `str`
- required: true
- semantics: normalized source identifier derived from the root-relative path
- code: `farrier/farrier/sources.py::Source`

### field: layer
- type: `Layer | None`
- default: `None`
- required: false
- semantics: library layer that supplied the record; direct test-created records may omit it
- code: `farrier/farrier/sources.py::Source`
