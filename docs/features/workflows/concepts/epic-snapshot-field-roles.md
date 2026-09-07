---
type: concept
slug: epic-snapshot-field-roles
title: Epic snapshot field roles
---
# Epic snapshot field roles

`EpicSnapshot` captures one immutable baseline before an epic edit is planned. Its fields are
complementary parts of that baseline, not alternate ways to represent the same value: `epic`,
`epic_dir`, and `epics_dir` identify and locate the epic; `title` and `epic_hash` preserve its
current metadata and content identity; and `seeds`, `stories`, and `milestones` preserve the
related graph state used to detect a stale plan.

The schema declares each field directly with a distinct type and empty-value default. It contains
no legacy marker, delegation, wrapper, or preference between fields, so no field supersedes
another. Readers select the field for the part of the baseline they need.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::EpicSnapshot`
- rule: select the field for the needed part of the pre-edit baseline; the eight fields are complementary and no ranking exists
