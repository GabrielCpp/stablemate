---
type: concept
slug: author-config-field-origin
title: Author configuration field origin
---
# Author configuration field origin

`Config` is the canonical declaration of the author workflow's repository root, document paths,
and prompt-layer hints: it declares `repo_root`, `backlog_path`, `roadmap_path`, `epics_dir`,
`features_dir`, and `layers` with their defaults. Read the fields in Author workflow configuration
when choosing or resolving this configuration at the start of a run.

Epic author context carries the same six values into the epic-writing subflow alongside its
epic-specific fields. Read those fields when determining the complete checkpoint context available
to that subflow; they do not define a second configuration source or change the values declared by
`Config`.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- rule: use Author workflow configuration for the canonical resolved configuration; use Epic author context only for that configuration as carried into the epic-writing subflow
- prefers: [author workflow configuration](../author-config.md)
