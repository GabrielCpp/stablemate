---
type: concept
slug: epic-author-context-field-roles
title: Epic author context field roles
---
# Epic author context field roles

`EpicAuthorContext` carries three complementary values for the one caller-selected epic. The
resolver first validates the requested `epic` name with Ostler, then derives `epic_dir` from the
resolved name and `epic_path` as that directory's `epic.md` path. They are not alternate inputs:
the name identifies the target, the directory scopes related artifacts, and the path identifies
the epic document.

No ranking exists among these fields. Each is used where its distinct representation is required;
the resolver derives the directory and document path from the selected name rather than choosing
one representation in place of another.

- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorContext`
- rule: use `epic` to identify the selected epic, `epic_dir` for its canonical directory, and `epic_path` for its `epic.md` document; none supersedes another
