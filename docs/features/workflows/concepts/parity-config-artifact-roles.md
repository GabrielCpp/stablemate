---
type: concept
slug: parity-config-artifact-roles
title: Parity configuration artifact roles
---
# Parity configuration artifact roles

`ParityConfig` carries the resolved locations for every artifact a parity survey reads or
writes. Its fields are complementary coordinates, not alternative implementations: a caller
selects the field named for the artifact it needs.

`repo_root` supplies the absolute base for all other paths. `baseline_inventory` identifies
the pre-existing legacy surface list, while `target_features` identifies the feature book in
which that surface may already have an owner. `survey_dir` groups the survey's derived
artifacts: `inventory` is the frozen unit list, `findings_dir` holds one finding record per
unit, and `unit_manifest` is the emitted audit manifest. `backlog` identifies the file whose
parity marker section is replaced, and `epics_dir` identifies the existing epic directory to
search for ownership.

All paths other than `repo_root` remain repository-relative because they are recorded exactly
as emitted by the parity script. No field ranks over or replaces another; selecting a field for
a different artifact is a configuration error rather than a supported fallback.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig`
- rule: select the field named for the parity-survey artifact being read or written; the fields are complementary and none substitutes for another
- detail: [parity configuration documentation roles](parity-config-documentation-roles.md)
