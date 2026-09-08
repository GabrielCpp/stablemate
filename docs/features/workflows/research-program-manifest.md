---
type: format
slug: research-program-manifest
title: Research program manifest
---
# Research program manifest

- file: `<program-dir>/program.yml`
- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::main`
- detail: [research program scaffolder](concepts/research-program-scaffolder.md)

The manifest is a flat YAML file read by the research workflow's `load_program`. The scaffolder
always writes the machine envelope and containment policy; `progress_path` and `result_branch` are
written only when their CLI overrides are supplied, otherwise their effective values are derived
from the program directory and slug.

## Fields

### code_root

- type: repository-relative path string
- required: true
- semantics: directory where the program's experiments are written
- verify: persists(subject="program.yml code_root")
- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::main`
- detail: [research program manifest field selection](concepts/research-program-manifest-field-selection.md)

### progress_path

- type: repository-relative path string
- default: `<program-dir>/PROGRESS.md` when `--progress` is absent
- required: false
- semantics: path of the progress log consumed by the research run
- verify: persists(subject="program.yml progress_path")
- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::main`
- detail: [research program manifest field selection](concepts/research-program-manifest-field-selection.md)

### result_branch

- type: branch name string
- default: `<slug(program-dir)>/auto` when `--result-branch` is absent
- required: false
- semantics: branch where gate work is committed and pushed
- verify: persists(subject="program.yml result_branch")
- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::main`
- detail: [research program manifest field selection](concepts/research-program-manifest-field-selection.md)

### envelope_ram_gb

- type: non-negative integer
- default: `0`
- required: true
- semantics: usable RAM bound for experiments
- verify: json_path(path="$.envelope_ram_gb", equals=0)
- semantics: zero declares no RAM bound
- verify: json_path(path="$.envelope_ram_gb", equals=0)
- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::main`
- detail: [research program manifest field selection](concepts/research-program-manifest-field-selection.md)

### envelope_cpus

- type: non-negative integer
- default: `0`
- required: true
- semantics: usable CPU-core bound for experiments
- verify: json_path(path="$.envelope_cpus", equals=0)
- semantics: zero declares no CPU bound
- verify: json_path(path="$.envelope_cpus", equals=0)
- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::main`
- detail: [research program manifest field selection](concepts/research-program-manifest-field-selection.md)

### envelope_gpu

- type: GPU description string
- default: `none`
- required: true
- semantics: usable GPU resource bound
- verify: json_path(path="$.envelope_gpu", equals="none")
- semantics: `none` declares no GPU
- verify: json_path(path="$.envelope_gpu", equals="none")
- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::main`
- detail: [research program manifest field selection](concepts/research-program-manifest-field-selection.md)

### envelope_disk_gb

- type: non-negative integer
- default: `0`
- required: true
- semantics: usable scratch-disk bound for experiments
- verify: json_path(path="$.envelope_disk_gb", equals=0)
- semantics: zero declares no disk bound
- verify: json_path(path="$.envelope_disk_gb", equals=0)
- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::main`
- detail: [research program manifest field selection](concepts/research-program-manifest-field-selection.md)

### min_containment

- type: enumeration: `premium` | `best_effort` | `advisory`
- default: `premium`
- required: true
- semantics: weakest resource-containment tier under which a measurement may be trusted
- verify: json_path(path="$.min_containment", equals="premium")
- code: `workflows/src/workhorse_workflows/research/scaffold/new_program.py::main`
- detail: [research program manifest field selection](concepts/research-program-manifest-field-selection.md)
