---
type: format
slug: parity-config
title: Parity survey configuration
---
# Parity survey configuration

The `ParityConfig` value is the resolved comparison context passed from setup to every parity
surveyor state. It inherits the author result model's input rules: each field has a default,
unknown input keys are ignored, and null input values are discarded before validation. The
configuration loader supplies the resolved values; the model itself does not resolve paths or
check that files exist. `repo_root` is absolute; all other paths are repository-relative. The
baseline is the legacy inventory, while the remaining artifacts identify the frozen worklist,
finding records, generated backlog section, manifest, target feature book, and epic search area.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig`
- detail: [author parity surveyor subflow](concepts/parity-surveyor-subflow.md)
- tests: `workflows/tests/author/parity_surveyor/test_parity.py::test_config_derives_every_path_under_the_survey_dir`
- tests: `workflows/tests/author/parity_surveyor/test_parity.py::test_config_honours_an_overridden_survey_dir`

## Fields

### repo_root
- type: string
- default: empty string before configuration resolves
- required: false
- semantics: absolute repository root used to resolve all repository-relative paths
- verify: json_path(path="$.repo_root", matches="^/.+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig`

### baseline_inventory
- type: string
- default: empty string before configuration resolves
- required: false
- semantics: repository-relative JSON inventory whose legacy entries define the parity baseline
- verify: json_path(path="$.baseline_inventory", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig`

### target_features
- type: string
- default: empty string before configuration resolves
- required: false
- semantics: repository-relative feature-book directory searched for ownership of each baseline surface
- verify: json_path(path="$.target_features", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig`

### survey_dir
- type: string
- default: empty string before configuration resolves
- required: false
- semantics: repository-relative directory containing parity inventory, findings, and manifest artifacts
- verify: json_path(path="$.survey_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig`

### inventory
- type: string
- default: empty string before configuration resolves
- required: false
- semantics: repository-relative frozen unit-list JSON path
- verify: json_path(path="$.inventory", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig`

### findings_dir
- type: string
- default: empty string before configuration resolves
- required: false
- semantics: repository-relative directory containing one finding record per frozen unit
- verify: json_path(path="$.findings_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig`

### unit_manifest
- type: string
- default: empty string before configuration resolves
- required: false
- semantics: repository-relative JSON path for the emitted audit manifest
- verify: json_path(path="$.unit_manifest", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig`

### backlog
- type: string
- default: empty string before configuration resolves
- required: false
- semantics: repository-relative backlog file whose parity marker section is replaced on emission
- verify: json_path(path="$.backlog", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig`

### epics_dir
- type: string
- default: empty string before configuration resolves
- required: false
- semantics: repository-relative epic directory searched for existing ownership of missing surfaces
- verify: json_path(path="$.epics_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig`
