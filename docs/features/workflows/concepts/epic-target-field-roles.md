---
type: concept
slug: epic-target-field-roles
title: Epic target field roles
---
# Epic target field roles

`EpicTarget` declares three independent string fields for one explicitly resolved epic. Its
source does not rank or supersede them: each field is retained because later states need a
different representation of that same target.

Use `epic` when identifying the requested epic by its canonical Ostler name, `epic_dir` when a
repository-relative epic directory is required, and `epic_path` when the repository-relative
`epic.md` file is required. They are not alternative target implementations and are normally
carried together after resolution.

- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicTarget`
- rule: select the field by the representation the caller requires; no field supersedes another
