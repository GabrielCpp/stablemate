---
type: concept
slug: author-parity-surveyor-subflow
title: Author parity surveyor subflow
---
# Author parity surveyor subflow

The `parity_surveyor` flow asks one question of a rewrite — which legacy surfaces have no home in the new app. It operates as an exhaustiveness survey: one frozen unit per baseline surface, one finding record each, and the empty pending set as the proof. The flow transcribes the baseline inventory into a frozen list, then walks the list in a per-unit loop — pick, assess (asking an agent to judge coverage), mark, and loop — then verifies all units were accounted for and emits one backlog bullet per uncovered surface. Unlike the general surveyor, parity findings are not clustered: each missing surface is its own gap. The subflow is reachable only through the `run` command's `parity-surveyor` selection in the composition root.

- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor`
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/__init__.py`
- tests: `workflows/tests/author/parity_surveyor/test_flow.py::test_every_baseline_surface_is_either_assessed_or_suppressed`
- tests: `workflows/tests/author/parity_surveyor/test_parity.py::test_emitting_each_baseline_surface_as_its_own_bullet`
- detail: [parity assessment prompt](../parity-assessment-prompt.md)
- detail: [shared survey library](survey-shared-library.md)
- detail: [author shared paths](author-shared-paths.md)
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)
- detail: [author shared survey blueprint](author-shared-survey-blueprint.md)

## Methods

### setup
- sig: `setup() -> ParityConfig`
- does: calls `load_parity_config` with the workflow's baseline inventory and survey-directory parameters
- verify: count(subject="parity configuration node calls", equals=1)
- does: carries the returned repository root and repository-relative artifact paths into the workflow context
- verify: count(subject="parity configuration contexts", equals=1)
- raises: raises `WorkflowFailed` when the baseline inventory file does not exist or is not readable
- verify: count(subject="missing parity baseline failures", equals=1)
- raises: raises `WorkflowFailed` when the target feature-book directory does not exist
- verify: count(subject="missing parity target-features failures", equals=1)
- returns: returns a `ParityConfig` containing the resolved repository root, baseline inventory path, target feature-book path, and derived artifact paths
- verify: count(subject="parity configuration results", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.setup`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### labels
- sig: `labels() -> dict[str, str]`
- does: returns empty labels before the first unit is picked
- verify: count(subject="parity work-label keys", equals=0)
- does: reports the selected unit id and progress percentage after a unit has been selected
- returns: returns `work_id` (the unit id) and `progress` (human-readable progress text) from the latest pick
- verify: count(subject="parity work-label snapshots", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.labels`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)
- tests: `workflows/tests/author/parity_surveyor/test_flow.py::test_every_baseline_surface_is_either_assessed_or_suppressed`

### start
- sig: `start() -> Continue`
- does: calls `expand_parity_inventory` to transcribe the baseline into a frozen unit list
- verify: count(subject="parity inventory expansions", equals=1)
- does: raises `WorkflowFailed` if the baseline cannot be frozen into the inventory
- verify: count(subject="parity freeze failures", equals=1)
- returns: returns a continuation targeting `pick` with the expansion result
- verify: count(subject="parity start transitions", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.start`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### pick
- sig: `pick() -> Continue`
- does: calls `select_next_unit` to retrieve the next pending unit from the frozen inventory
- verify: count(subject="parity unit selections", equals=1)
- does: routes to the coverage gate `verify` when no units remain in the pending set
- verify: count(subject="parity pick-to-verify transitions", equals=1)
- does: routes to the agent assessment when a unit is available
- verify: count(subject="parity pick-to-assess transitions", equals=1)
- returns: returns a continuation targeting `assess` or `verify` with the unit id, path, kind, and record path
- verify: count(subject="parity pick route outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.pick`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### assess
- sig: `assess(unit_id: str, unit_path: str, unit_kind: str, record_path: str, progress: str = "") -> Continue`
- does: asks a medium-power agent to judge whether the legacy surface named by the unit is covered by the new app
- verify: count(subject="parity unit assessments", equals=1)
- does: passes the baseline inventory path, target features path, backlog path, and epics directory to the agent
- verify: json_path(path="$.baseline_inventory", matches=".+")
- does: logs the unit kind, id, and progress percentage with the `activity` flag
- verify: visible(locator="activity log", text="assessing parity")
- returns: returns the agent's `UnitAssessment` response containing the finding record and existing-owner claim
- verify: count(subject="parity assessment results", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.assess`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### mark
- sig: `mark(unit_id: str, record_path: str) -> Continue`
- does: calls `validate_record` to check the finding record the assessment wrote
- verify: count(subject="parity record validations", equals=1)
- does: raises `WorkflowFailed` if the record is invalid, blocking further units
- verify: count(subject="parity mark failures", equals=1)
- does: calls `mark_unit` to remove the assessed unit from the pending set
- verify: count(subject="parity unit markings", equals=1)
- returns: returns a continuation targeting `pick` to process the next unit
- verify: count(subject="parity mark-to-pick transitions", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.mark`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### verify
- sig: `verify() -> Continue`
- does: calls `verify_records` to confirm every frozen unit has been accounted for in the findings directory
- verify: count(subject="parity coverage gates", equals=1)
- does: raises `WorkflowFailed` if the coverage gate fails or if the survey assessed zero units
- verify: count(subject="parity verify failures", equals=1)
- returns: returns a continuation targeting `emit` when all units are accounted for
- verify: count(subject="parity verify-to-emit transitions", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.verify`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

### emit
- sig: `emit() -> Done`
- does: calls `emit_parity_backlog` to write one backlog bullet per assessed surface not already owned by the new app
- verify: count(subject="parity backlog emissions", equals=1)
- does: logs emission even if no surfaces were output or if the result reports `emit_ok=false`
- verify: visible(locator="emission log", text="missing-surface")
- returns: returns `Done` with the `EmitResult` containing the bullet count and unit manifest
- verify: count(subject="completed parity surveys", equals=1)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor.emit`
- detail: [parity surveyor concept selection](parity-surveyor-concept-selection.md)

## Nodes

### load_parity_config
- sig: `load_parity_config(logger: logging.Logger, baseline: str, survey_dir: str = "docs/survey/legacy-vs-new", repo_dir: str = "") -> ParityConfig`
- does: resolves the repository root from `repo_dir`
- verify: count(subject="parity-config repository resolutions", equals=1)
- consistency: parity-baseline-inventory — rejects a blank or non-readable baseline inventory path by raising `WorkflowFailed` naming the missing file
- verify: count(subject="missing parity baseline failures", equals=1)
- does: rejects a target feature-book directory that does not exist
- raises: raises `WorkflowFailed` naming the missing target directory
- verify: count(subject="missing parity target-features failures", equals=1)
- does: normalizes empty `survey_dir` to the default path
- verify: json_path(path="$.survey_dir", matches="docs/survey")
- returns: returns a `ParityConfig` with the resolved repository root, baseline inventory path, target feature-book path, and derived paths for the inventory, findings directory, unit manifest, backlog, and epics directory
- verify: json_path(path="$.repo_root", matches=".+")
- verify: json_path(path="$.baseline_inventory", matches=".+")
- verify: json_path(path="$.target_features", matches=".+")
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::load_parity_config`

### expand_parity_inventory
- sig: `expand_parity_inventory(logger: logging.Logger, baseline: str, inventory: str, repo_dir: str = "") -> Expansion`
- does: reads the baseline inventory JSON file containing legacy surface entries
- verify: count(subject="baseline inventory reads", equals=1)
- does: consumes an existing frozen inventory verbatim when already present on disk, without re-deriving it
- verify: count(subject="inventory frozen states", equals=1)
- does: transcribes non-rewrite surfaces from the baseline into a frozen unit list, assigning each unit an id of the form `legacy/{area}/{slug}`
- verify: json_path(path="$.unit_count", matches="[1-9]")
- does: rejects blank area or slug fields in any baseline entry
- raises: raises `Expansion` with `expand_ok=false` when a baseline entry lacks required fields
- verify: json_path(path="$.expand_ok", equals=false)
- consistency rule: parity-unit-id — rejects duplicate surface ids found in the baseline
- raises: raises `Expansion` with `expand_ok=false` when a duplicate id is detected
- verify: json_path(path="$.expand_ok", equals=false)
- does: raises `Expansion` error when the baseline contains no non-rewrite surfaces
- verify: json_path(path="$.expand_ok", equals=false)
- returns: returns `Expansion(expand_ok=true, unit_count=<N>)` with the count of frozen units and a note describing the freeze outcome
- verify: json_path(path="$.expand_ok", equals=true)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::expand_parity_inventory`
- tests: `workflows/tests/author/parity_surveyor/test_parity.py::test_expanding_creates_one_unit_per_non_rewrite_surface`

### emit_parity_backlog
- sig: `emit_parity_backlog(logger: logging.Logger, inventory: str, findings_dir: str, unit_manifest: str, repo_dir: str = "") -> EmitResult`
- does: reads the frozen inventory and the findings records for each unit
- verify: count(subject="parity inventory reads", equals=1)
- does: renders one backlog bullet per unit marked `assessed` with an empty `existing_owner` field
- verify: visible(locator="legacy-parity bullets", text="legacy-parity-")
- does: suppresses units whose assessment identified an existing owner in the new app
- verify: count(subject="parity-suppressed surfaces", equals=1)
- persistence: parity-backlog-section — writes the parity-surveyor fenced section into the backlog file, replacing the previous section if present or creating the backlog file if it does not exist
- verify: created(subject="the parity backlog section")
- verify: unchanged(subject="backlog content outside parity markers")
- does: writes the unit manifest containing every unit's id, path, status, existing owner, and bullet id
- verify: created(subject="the parity unit manifest")
- verify: json_path(path="$.generatedBy", equals="parity-surveyor")
- returns: returns `EmitResult(emit_ok=true, bullet_count=<N>)` with the count of emitted bullets and a summary note
- verify: json_path(path="$.emit_ok", equals=true)
- returns: returns `EmitResult(emit_ok=false, emit_errors=...)` when the inventory or findings cannot be read
- verify: json_path(path="$.emit_ok", equals=false)
- code: `workflows/src/workhorse_workflows/author/parity_surveyor/nodes/parity.py::emit_parity_backlog`
- tests: `workflows/tests/author/parity_surveyor/test_parity.py::test_emitting_each_baseline_surface_as_its_own_bullet`

