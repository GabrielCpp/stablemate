---
type: concept
slug: parity-surveyor-subflow
title: Author parity surveyor subflow
---
# Author parity surveyor subflow

The parity surveyor compares a required legacy baseline inventory with the current OKF feature
book. It freezes every non-rewrite baseline entry as a pending `legacy-surface`, assesses each
unit in the surveyed repository, validates and marks its finding record, requires complete
coverage, and files one record on the [debt register](../../ostler/concepts/the-debt-register.md) for each uncovered surface plus a manifest containing
both filed and suppressed units. Existing survey record and worklist mechanics are shared with
the [author surveyor](author-surveyor-subflow.md); this subflow differs by having no planning,
splitting, or clustering stage.

- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor` @b0663bd1c3b9
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::load_parity_config` @ec5f8b71f521
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::expand_parity_inventory` @ec5f8b71f521
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::emit_parity_records` @ec5f8b71f521
- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig` @40a9cc4079c3
- tests: `workflows/tests/author/parity_surveyor/test_flow.py::test_a_two_surface_baseline_surveys_both_and_emits_only_the_unowned_one`
- tests: `workflows/tests/author/parity_surveyor/test_parity.py::test_expand_freezes_one_unit_per_baseline_surface`
- tests: `workflows/tests/author/parity_surveyor/test_parity.py::test_emit_files_one_parity_record_per_uncovered_surface`
- detail: [parity configuration documentation roles](parity-config-documentation-roles.md)
- detail: [parity configuration](../formats/parity-config.md)
- detail: [shared survey library](survey-shared-library.md)
- detail: [parity surveyor concern boundaries](parity-surveyor-concern-boundaries.md)
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

The workflow is entered by the author composition root as the named `parity-surveyor` handoff.
Its `baseline_inventory` input is required in practice; `survey_dir` defaults to
`docs/survey/legacy-vs-new`. The run resolves the repository from the input or current working
directory and keeps derived paths repository-relative.

## Fields

### baseline_inventory
- type: string path
- default: empty string
- required: false
- semantics: repository-relative JSON inventory of legacy surfaces to compare
- verify: json_path(path="$.baseline_inventory", equals="example baseline inventory")
- semantics: an empty or unreadable path fails setup with failure class `parity-baseline-missing`
- verify: json_path(path="exception.failure_class", equals="parity-baseline-missing")
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor` @b0663bd1c3b9
- detail: [parity surveyor input roles](parity-surveyor-input-roles.md)

### survey_dir
- type: string path
- default: `docs/survey/legacy-vs-new`
- required: false
- semantics: repository-relative directory containing the frozen inventory, finding records, and emitted unit manifest
- verify: json_path(path="$.survey_dir", equals="docs/survey/legacy-vs-new")
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor` @b0663bd1c3b9
- detail: [parity surveyor input roles](parity-surveyor-input-roles.md)

## Methods

### setup
- sig: `setup() -> ParityConfig`
- does: resolves the baseline, target feature-book, survey artifacts, and epic paths before states run
- raises: raises `WorkflowFailed` when the baseline inventory is empty or absent
- returns: returns [parity configuration](../formats/parity-config.md) containing all resolved comparison paths
- verify: count(subject="parity configuration results", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.setup` @b0663bd1c3b9
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### labels
- sig: `labels() -> dict[str, str]`
- does: reports no labels before the first unit selection
- does: reports the selected unit id and worklist progress after selection
- returns: returns a mapping containing `work_id` and `progress` when a selection exists
- verify: count(subject="parity survey label snapshots", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.labels` @b0663bd1c3b9
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### start
- sig: `start() -> Continue`
- does: freezes the baseline into the survey inventory, or consumes an existing frozen inventory verbatim
- raises: raises `WorkflowFailed` when the baseline cannot produce a valid non-rewrite unit list
- returns: continues to `pick` with the successful expansion result
- verify: count(subject="parity inventory freezes", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.start` @b0663bd1c3b9
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### pick
- sig: `pick() -> Continue`
- does: selects the first pending baseline unit and derives its finding-record path
- does: routes to coverage verification when no pending unit remains
- returns: continues to `assess` with the unit id, path, kind, record path, and progress
- verify: count(subject="parity unit selections", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.pick` @b0663bd1c3b9
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### assess
- sig: `assess(unit_id: str, unit_path: str, unit_kind: str, record_path: str, progress: str = "") -> Continue`
- does: asks one medium-power agent turn to compare the baseline surface with the target feature book, the open records of the surveyed repository, and epics
- does: runs the turn in the resolved surveyed repository
- does: supplies the unit identity, baseline path, baseline inventory, target feature path, the listing of the open records of the surveyed repository, epics path, and record path to the turn
- does: requires the turn to write one `survey-finding` record rather than feature nodes, epics, stories, or source code
- returns: continues to `mark` with the agent assessment, unit id, and record path
- verify: count(subject="parity unit assessments", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.assess` @b0663bd1c3b9
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### mark
- sig: `mark(unit_id: str, record_path: str) -> Continue`
- does: validates the selected finding record before changing its inventory status
- does: marks a valid unit from the record status and returns to unit selection
- raises: raises `WorkflowFailed` naming the unit when record validation fails
- returns: continues to `pick`
- verify: count(subject="parity finding records marked", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.mark` @b0663bd1c3b9
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### verify
- sig: `verify() -> Continue`
- does: requires every frozen unit to have consistent inventory and finding-record coverage
- raises: raises `WorkflowFailed` when coverage fails or when the survey has no units to prove
- returns: continues to `emit` only when coverage holds
- verify: count(subject="parity coverage gates", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.verify` @b0663bd1c3b9
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### emit
- sig: `emit() -> Done`
- does: files one record for each assessed unit without an existing owner
- does: suppresses assessed units with `existing_owner` while retaining them in the manifest
- does: writes a manifest containing every frozen unit and the id of its record
- returns: returns `Done` with the emission result, including the count of surfaces that have a record and the suppression note
- verify: count(subject="parity artifact emissions", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.emit` @b0663bd1c3b9
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### parity_slug
- sig: `parity_slug(value: str) -> str`
- does: converts a unit id to a lowercase hyphenated finding-record filename stem
- returns: returns the normalized stem with non-alphanumeric runs collapsed and edge hyphens removed
- verify: count(subject="parity record slug conversions", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::parity_slug` @ec5f8b71f521

### load_parity_config
- sig: `load_parity_config(logger: logging.Logger, baseline: str, survey_dir: str = "docs/survey/legacy-vs-new", repo_dir: str = "") -> ParityConfig`
- does: strips the baseline and survey-directory inputs and restores the default survey directory when blank
- raises: raises `WorkflowFailed` with failure class `parity-baseline-missing` when the baseline path is blank or absent
- raises: raises `WorkflowFailed` with failure class `parity-target-missing` when the target feature book is absent
- returns: returns a [parity configuration](../formats/parity-config.md) with paths derived from the selected repository root
- verify: count(subject="loaded parity configurations", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::load_parity_config` @ec5f8b71f521

### expand_parity_inventory
- sig: `expand_parity_inventory(logger: logging.Logger, baseline: str, inventory: str, repo_dir: str = "") -> Expansion`
- does: consumes an existing frozen inventory without re-deriving it
- does: otherwise reads baseline `entries` and creates one pending unit per valid non-rewrite area/slug pair
- does: rejects malformed, duplicate, unreadable, and zero-unit baselines without writing a freeze
- returns: returns an `Expansion` identifying the frozen unit count and source note
- verify: count(subject="expanded parity inventories", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::expand_parity_inventory` @ec5f8b71f521

### read_parity_register
- sig: `read_parity_register(logger: logging.Logger, repo_dir: str = "") -> RegisterListing`
- does: lists the open records of the surveyed repository on the [debt register](../../ostler/concepts/the-debt-register.md) for the assessor to match a surface against
- returns: returns a `RegisterListing` whose text is `no open records` when the repository has none
- verify: count(subject="parity register listings", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::read_parity_register` @ec5f8b71f521
- tests: `workflows/tests/author/parity_surveyor/test_flow.py::test_the_assessor_reads_the_open_register_of_the_surveyed_repository`

### emit_parity_records
- sig: `emit_parity_records(logger: logging.Logger, inventory: str, findings_dir: str, unit_manifest: str, repo_dir: str = "") -> EmitResult`
- does: reads the frozen inventory and the finding record of each unit
- verify: count(subject="parity inventory reads", equals=1)
- does: files one record per unit marked `assessed` with an empty `existing_owner` field, on the [debt register](../../ostler/concepts/the-debt-register.md), for the surveyed repository with the filer `parity`
- verify: count(subject="filed parity records", equals=1)
- does: takes the first finding's description, flattened to one line, as the record summary, the unit's area as the record area, and `untriaged` as the pattern
- verify: count(subject="parity record fields", equals=1)
- does: writes the legacy surface id, the effort and the evidence of the first finding into the record body
- verify: count(subject="parity record bodies", equals=1)
- does: suppresses units whose assessment identified an existing owner in the new app
- verify: count(subject="parity-suppressed surfaces", equals=1)
- does: skips a surface whose summary an open `parity` record of the surveyed repository already states, and puts that record's id in the manifest
- verify: unchanged(subject="the register after an unchanged rerun")
- does: commits the new records in one artifacts commit
- verify: count(subject="parity artifacts commits", equals=1)
- does: writes the unit manifest containing every unit's id, path, status, existing owner, and the id of its record under the key `bullet`
- verify: created(subject="the parity unit manifest")
- verify: json_path(path="$.generatedBy", equals="parity-surveyor")
- returns: returns `EmitResult(emit_ok=true, bullet_count=<N>)` with the count of surfaces that have a record and a summary note
- verify: json_path(path="$.emit_ok", equals=true)
- returns: returns `EmitResult(emit_ok=false, emit_errors=...)` when the inventory or findings cannot be read, or when the register refuses a record
- verify: json_path(path="$.emit_ok", equals=false)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::emit_parity_records` @ec5f8b71f521
- tests: `workflows/tests/author/parity_surveyor/test_parity.py::test_emit_files_one_parity_record_per_uncovered_surface`
- tests: `workflows/tests/author/parity_surveyor/test_parity.py::test_emit_suppresses_a_surface_a_new_feature_already_owns`
- tests: `workflows/tests/author/parity_surveyor/test_parity.py::test_a_rerun_files_only_the_surface_that_is_new`
- tests: `workflows/tests/author/parity_surveyor/test_parity.py::test_emit_commits_every_record_of_one_emit_in_one_artifacts_commit`
