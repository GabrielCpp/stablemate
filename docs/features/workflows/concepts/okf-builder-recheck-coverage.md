---
type: concept
slug: okf-builder-recheck-coverage
title: OKF-builder recheck coverage selection
---
# OKF-builder recheck coverage selection

The `recheck` heading on [the OKF-builder main build machine](okf-builder-main-build-machine.md#recheck)
is the canonical section for `workflows/src/workhorse_workflows/okf_builder/main/flow.py::OkfBuilder.recheck`.
The `enumerate_surfaces` heading on
[the same page](okf-builder-main-build-machine.md#enumerate_surfaces) is a name retained from the
pre-pyflow `workflows/workflows/okf-builder/workflow.yaml`, which carried `enumerate-surfaces` as
its own state and seeded the rest of the build from the entry-point surfaces — the diagram in
`workflows/docs/okf-builder.dot`, generated from the registered flows, carries only `recheck`
now; the book's heading is the sole place the old name survives. The port to `pyflow` collapsed that
state into `OkfBuilder.recheck`: the docstring on line 1128 reads "the only coverage judgement
left to an agent", and the role it now plays is precisely the adjudication of the computed
missing list the YAML split across two states. The book kept both headings, so two `method`
nodes ground themselves in one source symbol.

A reader arriving at either heading gets to the same `OkfBuilder.recheck` method, but the
`recheck` heading is the one whose name matches the symbol the code declares today; the
`enumerate_surfaces` heading is kept only because ripping it out would erase what happened in
the port.

- extends: [OKF-builder workflow composition root](okf-builder-workflow-composition-root.md)
- rule: read `recheck` for the current behaviour; reach `enumerate_surfaces` only when the
  history of the port matters — both still point at `OkfBuilder.recheck`
- prefers: [recheck](okf-builder-main-build-machine.md#recheck)
- deprecates: [enumerate_surfaces](okf-builder-main-build-machine.md#enumerate_surfaces)
