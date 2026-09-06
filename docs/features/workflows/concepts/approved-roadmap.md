---
type: concept
slug: approved-roadmap
title: Approved roadmap
---
# Approved roadmap

This module discovers the single roadmap that the Author workflow is permitted to consume. It
uses the configured roadmaps directory, considers only its top-level Markdown files in sorted
order, and reads each candidate's own frontmatter. A caller cannot select an arbitrary file, and a
missing directory behaves like an empty candidate set. The exact frontmatter contract is
`type: roadmap` together with `status: approved`.

- code: `workflows/src/workhorse_workflows/author/shared/roadmap.py::approved_roadmap`
- detail: [author milestone subflow](author-milestone-subflow.md)

## Methods

### approved_roadmap
- sig: `approved_roadmap(root: Path) -> str`
- does: resolves the repository's configured roadmaps directory
- verify: count(subject="approved roadmap directory resolutions", equals=1)
- does: treats a missing or non-directory roadmaps location as having no candidates
- verify: count(subject="missing approved roadmap directory candidates", equals=0)
- does: considers only top-level `*.md` files and orders candidates by pathname
- verify: count(subject="approved roadmap markdown candidates", equals=1)
- does: selects the candidate whose frontmatter has exactly `type: roadmap` and `status: approved`
- verify: count(subject="selected approved roadmaps", equals=1)
- raises: `WorkflowFailed` when no candidate qualifies, including the directory and candidate count
- verify: count(subject="missing approved roadmap failures", equals=1)
- raises: `WorkflowFailed` when more than one candidate qualifies, naming every qualifying path
- verify: count(subject="ambiguous approved roadmap failures", equals=1)
- returns: the selected roadmap as a repository-relative POSIX path
- verify: json_path(path="$.roadmap", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/roadmap.py::approved_roadmap`
- tests: `workflows/tests/author/test_config.py::test_epic_authoring_requires_an_approved_roadmap`
- tests: `workflows/tests/author/test_config.py::test_epic_authoring_does_not_fall_back_to_a_backlog`
