---
type: concept
slug: parity-surveyor-subflow
title: Author parity surveyor subflow
---
# Author parity surveyor subflow

The parity surveyor compares a required legacy baseline inventory with the current OKF feature
book. It freezes every non-rewrite baseline entry as a pending `legacy-surface`, assesses each
unit in the surveyed repository, validates and marks its finding record, requires complete
coverage, and emits one backlog bullet for each uncovered surface plus a manifest containing
both emitted and suppressed units. Existing survey record and worklist mechanics are shared with
the [author surveyor](author-surveyor-subflow.md); this subflow differs by having no planning,
splitting, or clustering stage.

- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor`
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::load_parity_config`
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::expand_parity_inventory`
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::emit_parity_backlog`
- code: `workflows/src/workhorse_workflows/author/shared/schemas/parity.py::ParityConfig`
- tests: `workflows/tests/author/parity_surveyor/test_flow.py::test_a_two_surface_baseline_surveys_both_and_emits_only_the_unowned_one`
- tests: `workflows/tests/author/parity_surveyor/test_parity.py::test_expand_freezes_one_unit_per_baseline_surface`
- detail: [parity configuration documentation roles](parity-config-documentation-roles.md)
- detail: [parity configuration](../parity-config.md)
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
- verify: json_path(path="$.baseline_inventory", matches=".*")
- semantics: an empty or unreadable path fails setup with failure class `parity-baseline-missing`
- verify: json_path(path="exception.failure_class", equals="parity-baseline-missing")
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor`
- detail: [parity surveyor input roles](parity-surveyor-input-roles.md)

### survey_dir
- type: string path
- default: `docs/survey/legacy-vs-new`
- required: false
- semantics: repository-relative directory containing the frozen inventory, finding records, and emitted unit manifest
- verify: json_path(path="$.survey_dir", equals="docs/survey/legacy-vs-new")
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor`
- detail: [parity surveyor input roles](parity-surveyor-input-roles.md)

## Methods

### setup
- sig: `setup() -> ParityConfig`
- does: resolves the baseline, target feature-book, survey artifacts, backlog, and epic paths before states run
- raises: raises `WorkflowFailed` when the baseline inventory is empty or absent
- returns: returns [parity configuration](../parity-config.md) containing all resolved comparison paths
- verify: count(subject="parity configuration results", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.setup`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### labels
- sig: `labels() -> dict[str, str]`
- does: reports no labels before the first unit selection
- does: reports the selected unit id and worklist progress after selection
- returns: returns a mapping containing `work_id` and `progress` when a selection exists
- verify: count(subject="parity survey label snapshots", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.labels`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### start
- sig: `start() -> Continue`
- does: freezes the baseline into the survey inventory, or consumes an existing frozen inventory verbatim
- raises: raises `WorkflowFailed` when the baseline cannot produce a valid non-rewrite unit list
- returns: continues to `pick` with the successful expansion result
- verify: count(subject="parity inventory freezes", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.start`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### pick
- sig: `pick() -> Continue`
- does: selects the first pending baseline unit and derives its finding-record path
- does: routes to coverage verification when no pending unit remains
- returns: continues to `assess` with the unit id, path, kind, record path, and progress
- verify: count(subject="parity unit selections", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.pick`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### assess
- sig: `assess(unit_id: str, unit_path: str, unit_kind: str, record_path: str, progress: str = "") -> Continue`
- does: asks one medium-power agent turn to compare the baseline surface with the target feature book, backlog, and epics
- does: runs the turn in the resolved surveyed repository
- does: supplies the unit identity, baseline path, baseline inventory, target feature path, backlog path, epics path, and record path to the turn
- does: requires the turn to write one `survey-finding` record rather than feature nodes, epics, stories, or source code
- returns: continues to `mark` with the agent assessment, unit id, and record path
- verify: count(subject="parity unit assessments", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.assess`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### mark
- sig: `mark(unit_id: str, record_path: str) -> Continue`
- does: validates the selected finding record before changing its inventory status
- does: marks a valid unit from the record status and returns to unit selection
- raises: raises `WorkflowFailed` naming the unit when record validation fails
- returns: continues to `pick`
- verify: count(subject="parity finding records marked", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.mark`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### verify
- sig: `verify() -> Continue`
- does: requires every frozen unit to have consistent inventory and finding-record coverage
- raises: raises `WorkflowFailed` when coverage fails or when the survey has no units to prove
- returns: continues to `emit` only when coverage holds
- verify: count(subject="parity coverage gates", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.verify`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### emit
- sig: `emit() -> Done`
- does: emits one backlog bullet for each assessed unit without an existing owner
- does: suppresses assessed units with `existing_owner` while retaining them in the manifest
- does: writes the generated parity section and a manifest containing every frozen unit
- returns: returns `Done` with the emission result, including bullet count and suppression note
- verify: count(subject="parity artifact emissions", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.emit`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### parity_slug
- sig: `parity_slug(value: str) -> str`
- does: converts a unit id to a lowercase hyphenated finding-record filename stem
- returns: returns the normalized stem with non-alphanumeric runs collapsed and edge hyphens removed
- verify: count(subject="parity record slug conversions", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::parity_slug`

### replace_parity_section
- sig: `replace_parity_section(text: str, section: str) -> str`
- does: replaces an existing parity marker section without changing text outside its markers
- does: appends the parity heading and marker section to a non-empty backlog when no marker exists
- returns: returns the resulting backlog text
- verify: count(subject="parity backlog section replacements", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::replace_parity_section`

### load_parity_config
- sig: `load_parity_config(logger: logging.Logger, baseline: str, survey_dir: str = "docs/survey/legacy-vs-new", repo_dir: str = "") -> ParityConfig`
- does: strips the baseline and survey-directory inputs and restores the default survey directory when blank
- raises: raises `WorkflowFailed` with failure class `parity-baseline-missing` when the baseline path is blank or absent
- raises: raises `WorkflowFailed` with failure class `parity-target-missing` when the target feature book is absent
- returns: returns a [parity configuration](../parity-config.md) with paths derived from the selected repository root
- verify: count(subject="loaded parity configurations", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::load_parity_config`

### expand_parity_inventory
- sig: `expand_parity_inventory(logger: logging.Logger, baseline: str, inventory: str, repo_dir: str = "") -> Expansion`
- does: consumes an existing frozen inventory without re-deriving it
- does: otherwise reads baseline `entries` and creates one pending unit per valid non-rewrite area/slug pair
- does: rejects malformed, duplicate, unreadable, and zero-unit baselines without writing a freeze
- returns: returns an `Expansion` identifying the frozen unit count and source note
- verify: count(subject="expanded parity inventories", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::expand_parity_inventory`

### emit_parity_backlog
- sig: `emit_parity_backlog(logger: logging.Logger, inventory: str, findings_dir: str, unit_manifest: str, repo_dir: str = "") -> EmitResult`
- does: reads each frozen unit's finding record and emits only assessed records without an existing owner
- does: replaces only the parity marker section in the backlog and preserves other backlog content
- does: writes a version-one manifest with each unit's path, status, owner, and emitted bullet id
- returns: returns an `EmitResult` with emitted bullet count and suppression summary
- verify: count(subject="emitted parity backlogs", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::emit_parity_backlog`
