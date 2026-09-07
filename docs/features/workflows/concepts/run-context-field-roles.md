---
type: concept
slug: run-context-field-roles
title: Run context field roles
---
# Run context field roles

`RunContext` is the stable path configuration for one author run. `setup()` writes it once and a
resume restores it verbatim; values that change during authoring belong in workflow state instead.

The fields are complementary rather than interchangeable. `repo_root` anchors resolution on the
current machine; `backlog_path`, `roadmap_path`, `epics_dir`, and `features_dir` name
repository-relative planning inputs; and `layers` carries the local-instruction skill paths used as
prompt hints. No field supersedes another, and consumers select the field whose role matches the
path or prompt input they need.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::RunContext`
- rule: use `repo_root` for the run's resolved repository root, each repository-relative path for
  its named planning input, and `layers` for prompt-layer hints; none is an alternative to another
