---
type: concept
slug: milestone-snapshot-field-roles
title: Milestone snapshot field roles
---
# Milestone snapshot field roles

`MilestoneSnapshot` records three complementary parts of a milestone's captured state. `name`
identifies the milestone, `source_items` records the source items it owns, and `epics` records the
epics registered under it.

The schema declares these as separate attributes with distinct types and empty-value defaults. It
contains no legacy marker, delegation, wrapper, or preference between them, so no field supersedes
another. Readers select the field for the part of the milestone state they need.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/edit.py::MilestoneSnapshot`
- rule: select `name` for the milestone identifier, `source_items` for owned source items, and `epics` for registered epics; the fields are complementary and no ranking exists
