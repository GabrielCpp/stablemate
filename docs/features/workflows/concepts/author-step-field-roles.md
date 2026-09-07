---
type: concept
slug: author-step-field-roles
title: Author step field roles
---
# Author step field roles

`workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep` is one
artifact-derived operation record. Its fields are complementary slots rather than competing
implementations: `kind` selects the next workflow phase; `roadmap`, `epic`, and `story` identify
the artifact relevant to that phase; and `reason` records why the planner selected it.

The schema declares defaults for every slot but no deprecation, replacement, or preference among
them. Choose each field by the information needed for the selected operation: read `kind` to
choose the phase, then read the applicable artifact identifier and `reason` to understand that
choice. An operation can require more than one of these fields; no field substitutes for another.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep`
- rule: use `kind` for the phase, `roadmap`, `epic`, and `story` for the phase's applicable artifact identifiers, and `reason` for the planner's rationale; none replaces another
