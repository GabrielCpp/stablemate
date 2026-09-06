---
type: concept
slug: author-surveyor-subflow
title: Author surveyor subflow
---
# Author surveyor subflow

The `surveyor` flow is the exhaustive discovery machine reached by the `run` command's
`surveyor` selection in [workhorse-author](../workhorse-author.md). It resolves one rubric and
survey directory, freezes an inventory, assesses every pending unit, validates coverage, clusters
findings without loss, and returns only after writing the author backlog section and unit manifest.
Its agent turns make the planning, assessment, repair, partition, and diagnosis judgments; the
deterministic nodes validate the artifacts and route failed gates. A blocked gate always parks in
the operator context rather than allowing the resolver to decide for the operator.

The flow's own nodes are in `surveyor/`; inventory expansion, unit walking, record validation, and
the shared survey result models are intentionally shared with the parity surveyor. The default
rubric is `docs/survey/rubric.md`, the default artifact directory is `docs/survey`, and the default
operator mode is `auto`; any other operator-mode value follows the autonomous branch. The plan,
record-fix, and partition-rework loops allow 2, 2, and 3 local retries respectively. Each of the
plan, partition, and coverage gates allows 2 diagnostic resolver turns before subsequent blocks go
straight to the operator. The coverage resolver counter survives the per-unit loop and is not
reset by an await. A resume consumes the frozen inventory and on-disk finding records rather than
re-planning completed work.

- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor`
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::MAX_PLAN_REWORKS`
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::MAX_PLAN_RESOLVES`
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::MAX_RECORD_FIXES`
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::MAX_PARTITION_REWORKS`
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::MAX_PARTITION_RESOLVES`
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::MAX_VERIFY_RESOLVES`
- code: `workflows/src/workhorse_workflows/author/surveyor/nodes/config.py::load_survey_config`
- code: `workflows/src/workhorse_workflows/author/surveyor/nodes/config.py::check_inventory`
- code: `workflows/src/workhorse_workflows/author/surveyor/nodes/partition.py::validate_partition`
- code: `workflows/src/workhorse_workflows/author/surveyor/nodes/partition.py::emit_artifacts`
- tests: `workflows/tests/author/surveyor/test_flow.py::test_two_components_are_planned_assessed_verified_and_emitted`
- tests: `workflows/tests/author/surveyor/test_config.py::test_the_config_derives_every_path_from_survey_dir`
- tests: `workflows/tests/author/surveyor/test_partition.py::test_one_bullet_per_cluster_lands_in_the_fenced_section`
- detail: [shared survey library](survey-shared-library.md)
- detail: [author shared paths](author-shared-paths.md)
- detail: [author shared schemas](author-shared-schemas.md)

## Methods

### setup
- sig: `setup() -> SurveyConfig`
- does: resolves the rubric, survey directory, repository root, and all derived artifact paths
- raises: raises `WorkflowFailed` when the resolved rubric file does not exist
- returns: returns a `SurveyConfig` containing repo-relative survey paths and the resolved repository root
- verify: count(subject="survey configuration results", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.setup`
- tests: `workflows/tests/author/surveyor/test_config.py::test_the_config_derives_every_path_from_survey_dir`

### labels
- sig: `labels() -> dict[str, str]`
- does: reports the selected unit id and progress after a unit has been selected
- returns: returns an empty mapping before the first unit-selection node runs
- returns: returns `work_id` and `progress` labels from the latest unit selection
- verify: count(subject="surveyor work-label snapshots", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.labels`
- tests: `workflows/tests/author/surveyor/test_flow.py::test_the_labels_name_the_unit_and_the_progress`

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: combines work labels with the six survey budget counters carried by the current state
- returns: returns labels for plan rework, plan resolution, record fixes, coverage resolution, partition rework, and partition resolution
- verify: count(subject="surveyor state-label snapshots", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.state_labels`
- tests: `workflows/tests/author/surveyor/test_flow.py::test_the_labels_name_the_unit_and_the_progress`

### start
- sig: `start() -> Continue`
- does: checks whether a frozen inventory or pinned rules file already determines the survey units
- does: routes to planning only when neither inventory nor rules exists
- does: routes to inventory expansion when planning is unnecessary
- returns: returns a continuation for `plan` or `expand` with the inventory decision
- verify: count(subject="surveyor start routing decisions", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.start`
- tests: `workflows/tests/author/surveyor/test_config.py::test_an_existing_inventory_freezes_the_enumeration`

### plan
- sig: `plan(plan_rework: int = 0, plan_errors: str = "", plan_resolve: int = 0) -> Continue | Await`
- does: asks the agent to define the enumeration rules for the rubric and repository
- does: routes a blocked planning result to diagnosis or the operator according to operator mode and cumulative resolution budget
- does: routes a completed plan to inventory expansion without resetting the cumulative resolution counter
- returns: returns `Await` for a human decision when planning remains blocked
- verify: count(subject="surveyor planning outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.plan`
- tests: `workflows/tests/author/surveyor/test_flow.py::test_a_blocked_plan_waits_on_the_operator_then_resumes_the_planner`

### expand
- sig: `expand(plan_rework: int = 0, plan_resolve: int = 0) -> Continue | Await`
- does: materializes the unit inventory from rules or consumes the existing frozen inventory
- does: sends an empty or invalid expansion back to planning until the bounded rework limit is reached
- returns: returns a continuation for unit selection when the inventory is usable
- verify: count(subject="surveyor inventory expansion outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.expand`
- tests: `workflows/tests/author/surveyor/test_flow.py::test_rules_that_expand_to_nothing_send_the_flow_back_to_the_planner`

### resolve_plan
- sig: `resolve_plan(notes: str, plan_resolve: int = 0) -> Await`
- does: asks the diagnostic resolver to investigate a planning block and write findings to the operator context
- does: parks the flow for an operator decision without accepting the resolver's decision field
- returns: returns `Await` targeting planning with the local rework counter reset and cumulative resolution count incremented
- verify: count(subject="planning operator awaits", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.resolve_plan`

### pick
- sig: `pick(verify_resolve: int = 0) -> Continue`
- does: selects the first pending inventory unit and derives its finding-record path
- does: routes directly to coverage verification when no pending unit remains
- returns: returns a continuation carrying the selected unit identity, path, kind, record path, and progress
- verify: count(subject="surveyor unit-pick outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.pick`
- tests: `workflows/tests/author/surveyor/test_flow.py::test_the_labels_name_the_unit_and_the_progress`

### assess
- sig: `assess(unit_id: str, unit_path: str, unit_kind: str, record_path: str, progress: str = "", verify_resolve: int = 0) -> Continue`
- does: asks the agent to assess exactly one inventory unit against the rubric
- does: routes a unit that is too large for one assessment to splitting
- does: routes every other assessment result to record validation
- returns: returns a continuation carrying the unit and record identity needed by the next state
- verify: count(subject="surveyor unit assessments", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.assess`
- tests: `workflows/tests/author/surveyor/test_flow.py::test_the_assessor_is_handed_the_unit_the_rubric_and_the_context_file`

### split
- sig: `split(unit_id: str, record_path: str, verify_resolve: int = 0) -> Continue`
- does: replaces an oversized folder unit with its immediate children
- does: marks the unit blocked with split errors when it cannot be split
- returns: returns a continuation for selecting the next unit
- verify: count(subject="surveyor unit-split outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.split`
- tests: `workflows/tests/author/surveyor/test_flow.py::test_a_unit_too_big_to_assess_is_split_into_its_children`

### check
- sig: `check(unit_id: str, record_path: str, record_fix: int = 0, verify_resolve: int = 0) -> Continue`
- does: validates the finding record produced for the selected unit
- does: sends an invalid record through bounded repair before marking it blocked when repairs are exhausted
- does: marks a valid record and returns to unit selection
- returns: returns a continuation for repair or the next unit
- verify: count(subject="surveyor finding-record checks", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.check`
- tests: `workflows/tests/author/surveyor/test_flow.py::test_an_invalid_record_is_repaired_once_and_the_unit_lands_assessed`

### fix
- sig: `fix(unit_id: str, record_path: str, record_errors: str, record_fix: int = 0, verify_resolve: int = 0) -> Continue`
- does: asks the agent to repair one named set of finding-record validation errors
- does: revalidates the record regardless of the repair reply
- returns: returns a continuation for record checking with the repair counter incremented
- verify: count(subject="surveyor finding-record repairs", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.fix`

### verify
- sig: `verify(verify_resolve: int = 0) -> Continue | Await`
- does: checks that every frozen unit has a consistent, accounted-for finding record
- does: allows a no-inventory survey to pass as nothing surveyed
- does: routes a coverage failure to diagnosis or the operator after the cumulative resolution budget is exhausted
- returns: returns a continuation for partitioning when coverage holds
- verify: count(subject="surveyor coverage-gate outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.verify`
- tests: `workflows/tests/author/surveyor/test_flow.py::test_two_components_are_planned_assessed_verified_and_emitted`

### resolve_verify
- sig: `resolve_verify(notes: str, verify_resolve: int = 0) -> Await`
- does: asks the diagnostic resolver to investigate a coverage failure and write findings to the operator context
- does: parks for the operator and re-enters unit selection after an answer
- returns: returns `Await` with the cumulative coverage-resolution count incremented
- verify: count(subject="coverage operator awaits", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.resolve_verify`

### partition
- sig: `partition(partition_rework: int = 0, partition_errors: str = "", partition_resolve: int = 0) -> Continue | Await`
- does: asks the agent to cluster finding records into remediation work items
- does: validates that clusters are structurally valid and cover every assessed unit without inventing units
- does: retries invalid partitions within the bounded rework budget, then routes the block to diagnosis or the operator
- returns: returns a continuation for artifact emission when partition validation holds
- verify: count(subject="surveyor partition outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.partition`
- tests: `workflows/tests/author/surveyor/test_flow.py::test_a_partition_that_orphans_a_unit_is_sent_back_with_the_orphan_named`

### resolve_partition
- sig: `resolve_partition(notes: str, partition_resolve: int = 0) -> Await`
- does: asks the diagnostic resolver to investigate a partition block and write findings to the operator context
- does: parks the flow for an operator decision without allowing the resolver to resolve the block
- returns: returns `Await` targeting partitioning with local rework reset and cumulative resolution incremented
- verify: count(subject="partition operator awaits", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.resolve_partition`

### emit
- sig: `emit() -> Done`
- does: writes one generated backlog bullet per validated cluster inside the survey marker section
- does: writes a unit manifest containing every inventory unit and its covering cluster ids
- raises: raises `WorkflowFailed` when artifact emission fails
- returns: returns `Done` with the emission result after both artifacts are written
- verify: count(subject="surveyor completed emissions", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/flow.py::Surveyor.emit`
- tests: `workflows/tests/author/surveyor/test_partition.py::test_the_manifest_carries_every_unit_and_what_covers_it`

## Methods

### load_survey_config
- sig: `load_survey_config(logger: logging.Logger, rubric: str = "docs/survey/rubric.md", survey_dir: str = "docs/survey", repo_dir: str = "") -> SurveyConfig`
- does: strips blank rubric and survey-directory parameters back to their defaults
- does: derives rules, inventory, findings, partition, backlog, manifest, and context paths from the survey directory
- raises: raises `WorkflowFailed` with the resolved rubric path and parameter guidance when the rubric is absent
- returns: returns a `SurveyConfig` whose survey paths are repository-relative
- verify: count(subject="loaded survey configurations", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/nodes/config.py::load_survey_config`
- tests: `workflows/tests/author/surveyor/test_config.py::test_a_missing_rubric_halts_the_run`

### check_inventory
- sig: `check_inventory(logger: logging.Logger, inventory: str = "docs/survey/inventory.json", rules: str = "docs/survey/units.yml", repo_dir: str = "") -> InventoryCheck`
- does: prefers an existing inventory over all other choices
- does: skips planning when rules exist without an inventory
- does: requests planning only when neither inventory nor rules exists
- returns: returns the decision and a human-readable reason for the selected precedence branch
- verify: count(subject="inventory planning decisions", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/nodes/config.py::check_inventory`
- tests: `workflows/tests/author/surveyor/test_config.py::test_with_neither_the_planner_gets_its_one_judgment`

### validate_partition
- sig: `validate_partition(logger: logging.Logger, partition: str = "docs/survey/partition.yaml", inventory: str = "docs/survey/inventory.json", repo_dir: str = "") -> PartitionCheck`
- does: rejects missing or unparsable partition and inventory artifacts
- does: rejects duplicate or malformed cluster ids, empty titles, unknown strategies, invalid remediation patterns, and empty cluster unit lists
- does: rejects clusters that name unknown or non-assessed units
- does: rejects any assessed inventory unit absent from every cluster
- returns: returns a valid result only when every assessed unit is covered and no cluster invents work
- verify: count(subject="validated survey partitions", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/nodes/partition.py::validate_partition`
- tests: `workflows/tests/author/surveyor/test_partition.py::test_an_assessed_unit_in_no_cluster_is_the_gate`

### emit_artifacts
- sig: `emit_artifacts(logger: logging.Logger, partition: str = "docs/survey/partition.yaml", inventory: str = "docs/survey/inventory.json", unit_manifest: str = "docs/survey/unit-manifest.json", repo_dir: str = "") -> EmitResult`
- does: sorts clusters by explicit order and id before rendering backlog bullets
- does: replaces only the generated survey section in the backlog and preserves content outside its markers
- does: writes a versioned manifest containing each unit's path, kind, status, bullets, and clusters
- returns: returns the number of emitted bullets and manifest units after successful writes
- verify: count(subject="survey artifact emissions", equals=1)
- code: `workflows/src/workhorse_workflows/author/surveyor/nodes/partition.py::emit_artifacts`
- tests: `workflows/tests/author/surveyor/test_partition.py::test_re_emitting_replaces_the_section_and_nothing_else`
