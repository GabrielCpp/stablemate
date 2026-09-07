---
type: concept
slug: parity-surveyor-input-roles
title: Parity surveyor input roles
---
# Parity surveyor input roles

`baseline_inventory` and `survey_dir` are separate inputs to the same parity-surveyor
workflow, not alternative implementations. A run needs `baseline_inventory` to identify the
legacy surfaces it compares; setup rejects a blank or unreadable value. `survey_dir` instead
locates the survey's derived inventory, finding records, and manifest, and defaults to
`docs/survey/legacy-vs-new` when the caller does not select another repository-relative
location.

Neither field ranks over or replaces the other: provide a readable baseline for every parity
survey, and set the survey directory only when its default artifact location is unsuitable.

- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor`
- rule: select `baseline_inventory` for the required comparison source and `survey_dir` for the optional artifact location; neither is a substitute for the other
