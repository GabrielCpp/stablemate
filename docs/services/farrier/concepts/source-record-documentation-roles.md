---
type: concept
slug: source-record-documentation-roles
title: Source record documentation roles
---
# Source record documentation roles

`Source` is one immutable record with fields for source category, filesystem access,
root-relative provenance, stable matching, and layer provenance. The source declaration
assigns those distinct roles but does not rank the two descriptions of the record.

Use [library source record](source-record.md) to understand the record passed through
discovery, matching, lookup, and rendering. Use [source record field roles](source-record-field-roles.md)
when selecting the field appropriate to an operation. Neither concept replaces the other.

- rule: use the record overview for the `Source` lifecycle and field roles when choosing `kind`, `path`, `rel`, `id`, or `layer`; the source declares no ranking between the two concepts
