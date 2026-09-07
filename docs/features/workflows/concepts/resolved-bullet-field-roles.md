---
type: concept
slug: resolved-bullet-field-roles
title: Resolved bullet field roles
---
# Resolved bullet field roles

`ResolvedBullet` carries the result of normalizing one add-story bullet reference. Its fields
answer complementary questions rather than providing alternatives: `id` identifies the resolved
backlog item or normalized literal, `source_bullet` preserves the original scope text, and
`from_backlog` records whether that resolution came from the configured backlog.

The schema declares each field independently with its own default and contains no preference,
deprecation, delegation, or migration path. Consumers select the field that answers their
question; no field replaces or ranks above another.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::ResolvedBullet`
- rule: select the field for the identity, source text, or backlog-origin question at hand; the three fields are complementary and no ranking exists
