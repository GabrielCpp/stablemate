---
type: concept
slug: okf-builder-seed-recheck
title: OKF-builder seed_recheck selection
---
# OKF-builder seed_recheck selection

The `seed_recheck` heading on [the OKF-builder main build machine](okf-builder-main-build-machine.md#seed_recheck)
is the canonical section for `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.seed_recheck`.
The `seed_surfaces` heading on [the same page](okf-builder-main-build-machine.md#seed_surfaces)
is a name retained from the pre-pyflow `workflows/workflows/okf-builder/workflow.yaml`,
which carried `seed-surfaces` as its own state and recorded the adjudicated gaps as pending
work. The port to `pyflow` collapsed that state into `OkfBuilder.seed_recheck`: the docstring
on line 1180 reads "queue what the adjudication ruled to be real work", and the role it now
plays is precisely the post-recheck worklist seed the YAML split across two states. The book
kept both headings, so two `method` nodes ground themselves in one source symbol.

A reader arriving at either heading gets to the same `OkfBuilder.seed_recheck` method, but the
`seed_recheck` heading is the one whose name matches the symbol the code declares today; the
`seed_surfaces` heading is kept only because ripping it out would erase what happened in the
port.

- extends: [OKF-builder workflow composition root](okf-builder-workflow-composition-root.md)
- rule: read `seed_recheck` for the current behaviour; reach `seed_surfaces` only when the
  history of the port matters — both still point at `OkfBuilder.seed_recheck`
- prefers: [seed_recheck](okf-builder-main-build-machine.md#seed_recheck)
- deprecates: [seed_surfaces](okf-builder-main-build-machine.md#seed_surfaces)
