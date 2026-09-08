---
type: flow
slug: author-parity-surveyor
title: Author parity surveyor
---
# Author parity surveyor

The parity surveyor is a subflow of the author workflow, invoked when the author runs in
`parity-surveyor` mode. It answers one question: which baseline surfaces have no home in the
current OKF book? It is a *survey*, so it carries the exhaustiveness guarantee: one frozen unit
per baseline surface, one finding record each, and the empty pending set as the proof.

The flow reuses the surveyor's per-unit mechanics (`select_next_unit`, `validate_record`,
`mark_unit`, `verify_records`) but differs at the ends: the frozen list comes from a baseline
inventory file rather than enumerated rules, and emission suppresses any surface already claimed
by an existing backlog item or epic. No partition step exists — each missing surface is its own
gap, and clustering would merge exactly what a parity backlog needs kept separate.

- start: the author runs with `mode="parity-surveyor"` and provides a baseline inventory path.
- start: a readable baseline inventory file exists at the path provided in `baseline_inventory`.
- start: the current OKF feature book exists under the repo's `docs/features/` root.
- start: survey artifacts (inventory, findings records, manifest) are either absent (first run) or present and consistent (resumed run).
- steps:
  - [load configuration](#load-configuration)
  - [freeze the baseline inventory](#freeze-the-baseline-inventory)
  - [per-unit assessment loop](#per-unit-assessment-loop)
  - [verify exhaustive coverage](#verify-exhaustive-coverage)
  - [emit parity backlog](#emit-parity-backlog)
- end: the survey has produced a durable backlog of findings (`backlog.yml`) and unit manifest, representing an exhaustive assessment of all baseline surfaces against the current book, with every missing surface attributed to one backlog bullet.
- verify: persists(subject="the survey backlog and manifest")
- verify: persists(subject="the frozen unit inventory")
- verify: unchanged(subject="the unit inventory after coverage verification")
- detail: [parity surveyor subflow](../concepts/parity-surveyor-subflow.md)
- detail: [parity surveyor input roles](../concepts/parity-surveyor-input-roles.md)
- tests: `workflows/tests/author/parity_surveyor/test_parity.py::test_expand_freezes_one_unit_per_baseline_surface`
- tests: `workflows/tests/author/parity_surveyor/test_parity.py::test_emit_writes_one_bullet_per_uncovered_surface`

## Load configuration

The setup phase resolves and validates both sides of the comparison: the baseline inventory file
and the target feature book. Both must exist before the flow proceeds — a parity survey with no
baseline has nothing to be exhaustive about, and one with no target feature book would report
every legacy surface as missing. Paths for the survey's own artifacts (inventory, findings
records, manifest) are derived from `survey_dir`.

Configuration is implemented by
`workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::load_parity_config`.

## Freeze the baseline inventory

Once configuration is validated, the flow materializes the frozen unit list by reading the
baseline inventory file. If this is the first run, the list is new. If a frozen inventory already
exists (from a prior run or a resume), the new read is verified to be identical — a silent
mismatch would corrupt the coverage claim.

If the baseline inventory is malformed or missing, the flow fails with a diagnostic
`parity-baseline-missing` or `parity-baseline-invalid` class and will not proceed.

Expansion is implemented by
`workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::expand_parity_inventory`.

## Per-unit assessment loop

Once the unit inventory is frozen, the flow enters a loop that processes each unit until none
remain. For each unit, it invokes an agent to assess whether the unit is covered by the current
OKF book, writes a finding record, validates the record, and marks the unit as completed. A unit
record can optionally name an existing owner (backlog bullet or epic) that already covers it,
which suppresses a duplicate emission.

If a record fails validation, the flow fails outright rather than attempting repair, because the
parity record *is* the finding and a malformed one would emit a bullet nobody can act on.

Assessment is implemented by
`workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.assess`, which
invokes an agent against `parity_surveyor/prompts/assess-parity-unit.md`. Validation is
implemented by `workflows/src/workhorse_workflows/author/shared/survey/records.py::validate_record`.
Marking is implemented by `workflows/src/workhorse_workflows/author/shared/survey/units.py::mark_unit`.

## Verify exhaustive coverage

Once every unit in the frozen inventory has been marked, the flow verifies that coverage is
exhaustive: all units are accounted for, no units are missing from the pending set, and the
manifest is consistent.

If coverage verification fails or no inventory was surveyed at all (inventory is empty), the flow
fails with a diagnostic message and will not proceed.

Verification is implemented by
`workflows/src/workhorse_workflows/author/shared/survey/records.py::verify_records`.

## Emit parity backlog

Once coverage is verified, the flow emits one backlog bullet per assessed surface that lacks
coverage in the current OKF book. Surfaces the record marks as already owned by an existing
backlog item or epic are suppressed — the finding record is retained for audit, but no duplicate
bullet is emitted.

The manifest carries *every* unit, including the suppressed ones and their owners, so the
coverage decision stays an auditable claim rather than an absence.

Emission is implemented by
`workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::emit_parity_backlog`.
The result's `bullet_count` is handed back to the author workflow as its return value.

