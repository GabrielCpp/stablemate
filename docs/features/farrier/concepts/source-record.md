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

- code: `farrier/farrier/sources.py::Source` @38fd583de0b8
- detail: [library layer](library-layer.md)
- detail: [source record documentation roles](source-record-documentation-roles.md)

## Fields

### field: kind
- type: `str`
- required: true
- verify: json_path(path="$.kind", matches="^(skill|prompt|policy)$")
- semantics: identifies the source category being loaded, such as `skill`, `prompt`, or `policy`
- code: `farrier/farrier/sources.py::Source` @38fd583de0b8
- detail: [source record field roles](source-record-field-roles.md)

### field: path
- type: `Path`
- required: true
- verify: json_path(path="$.path", matches="^/.+")
- semantics: filesystem path of the source document
- code: `farrier/farrier/sources.py::Source` @38fd583de0b8
- detail: [source record field roles](source-record-field-roles.md)

### field: rel
- type: `str`
- required: true
- verify: json_path(path="$.rel", matches="^[^/\\\\]+(?:/[^/\\\\]+)*\\.md$")
- semantics: POSIX path relative to the content root
- code: `farrier/farrier/sources.py::Source` @38fd583de0b8
- detail: [source record field roles](source-record-field-roles.md)

### field: id
- type: `str`
- required: true
- semantics: normalized source identifier derived from the root-relative path
- verify: json_path(path="$.id", matches="^[a-z0-9][a-z0-9-]*(/[a-z0-9][a-z0-9-]*)*$")
- code: `farrier/farrier/sources.py::Source` @38fd583de0b8
- detail: [source record field roles](source-record-field-roles.md)

### field: layer
- type: `Layer | None`
- default: `None`
- required: false
- verify: json_path(path="$.layer", absent=true)
- semantics: identifies the library layer that supplied the record
- verify: json_path(path="$.layer.name", equals="base-library (base)")
- semantics: direct test-created records may omit the layer
- code: `farrier/farrier/sources.py::Source` @38fd583de0b8
- detail: [source record field roles](source-record-field-roles.md)
