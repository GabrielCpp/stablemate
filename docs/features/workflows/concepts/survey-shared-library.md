---
type: concept
slug: survey-shared-library
title: Author shared survey library
---
# Author shared survey library

The author and parity surveyors share this library's frozen-worklist protocol. Inventory
materialization creates a durable list of units; traversal selects pending entries and records
their status; the record gates make each assessment and the whole inventory auditable. The module
also declares the `surveyor` blueprint that owns registration for this shared node set. That
blueprint is separate from the author node blueprint because the surveyor and author graphs are
separate machines, while `author/workflow.py` merges both blueprints into one registry so either
survey flow can resolve the shared nodes. The merged registry still requires node names to be
globally unique, so survey-specific registrations use names such as `load_survey_config` rather
than colliding with the author's `load_config`. The package exports this blueprint alongside the
shared inventory, unit-walking, and record-validation operations.

- code: `workflows/src/workhorse_workflows/author/shared/survey/blueprint.py::blueprint`
- tests: `workflows/tests/author/shared/survey/test_inventory.py::test_an_existing_inventory_is_consumed_verbatim`
- detail: [survey record check](../record-check.md)
- detail: [survey verification result](../verify-result.md)

The package exports inventory, unit-walking, and record-validation operations. It does not own
the survey-specific planning, partitioning, parity expansion, or artifact emission nodes; those
remain in their respective flow packages and consume these results.

## Fields

### RULE_KINDS
- type: `set[str]`
- default: `{"folder", "file", "command"}`
- verify: count(subject="survey rule-kind defaults", equals=1)
- required: true
- verify: count(subject="survey rule-kind presence", equals=1)
- semantics: allowed enumeration rule kinds for inventory materialization
- verify: count(subject="survey rule-kind semantics", equals=1)
- verify: count(subject="survey rule-kind vocabularies", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/inventory.py::RULE_KINDS`

### UNIT_STATUSES
- type: `set[str]`
- default: `{"pending", "assessed", "clean", "blocked"}`
- verify: count(subject="survey inventory status defaults", equals=1)
- required: true
- verify: count(subject="survey inventory status presence", equals=1)
- semantics: inventory status vocabulary
- verify: count(subject="survey inventory status semantics", equals=1)
- semantics: only `pending` is selectable and `assessed` or `clean` are completed
- verify: count(subject="survey inventory status vocabularies", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/inventory.py::UNIT_STATUSES`

### RECORD_STATUSES
- type: `set[str]`
- default: `{"assessed", "clean", "blocked"}`
- verify: count(subject="survey record status defaults", equals=1)
- required: true
- verify: count(subject="survey record status presence", equals=1)
- semantics: statuses permitted in a per-unit finding record
- verify: count(subject="survey record status semantics", equals=1)
- verify: count(subject="survey record status vocabularies", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/records.py::RECORD_STATUSES`

### PATTERN_SLUG_RE
- type: compiled regular expression
- default: `^[a-z0-9]+(-[a-z0-9]+)*$`
- required: true
- semantics: finding remediation patterns must be non-empty lowercase kebab-case slugs so partitioning can cluster them
- verify: count(subject="kebab-case remediation pattern validation", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/records.py::PATTERN_SLUG_RE`

### EFFORTS
- type: `set[str]`
- default: `{"trivial", "small", "substantial"}`
- verify: count(subject="survey finding effort defaults", equals=1)
- required: true
- verify: count(subject="survey finding effort presence", equals=1)
- semantics: effort vocabulary permitted on a finding
- verify: count(subject="survey finding effort semantics", equals=1)
- verify: count(subject="survey finding effort vocabularies", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/records.py::EFFORTS`

### SURVEY_SCHEME
- type: `workhorse.worklist.Scheme`
- default: `done=assessed|clean, blocked=blocked`
- verify: count(subject="survey worklist scheme defaults", equals=1)
- required: true
- verify: count(subject="survey worklist scheme presence", equals=1)
- semantics: worklist classification used to calculate progress and choose the next unit
- verify: count(subject="survey worklist scheme semantics", equals=1)
- verify: count(subject="survey worklist schemes", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/units.py::SURVEY_SCHEME`

## Methods

### record_slug
- sig: `record_slug(unit_id: str) -> str`
- does: lowercases a unit id and replaces every non-alphanumeric run with one hyphen
- verify: count(subject="lowercased finding-record slugs", equals=1)
- does: removes hyphens from both ends so the result is safe as a finding filename stem
- verify: count(subject="trimmed finding-record slugs", equals=1)
- returns: the normalized stem used beneath the findings directory
- verify: count(subject="finding-record slug returns", equals=1)
- verify: count(subject="normalized finding-record slugs", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/inventory.py::record_slug`
- tests: `workflows/tests/author/shared/survey/test_inventory.py::test_a_record_slug_is_filename_safe_and_lowercased`

### expand_inventory
- sig: `expand_inventory(logger: logging.Logger, rules: str = "docs/survey/units.yml", inventory: str = "docs/survey/inventory.json", repo_dir: str = "") -> Expansion`
- does: uses `docs/survey/units.yml` when the rules argument is blank
- verify: json_path(path="$.inventory_note", matches=".*")
- does: uses `docs/survey/inventory.json` when the inventory argument is blank
- verify: json_path(path="$.inventory_note", matches=".*")
- does: resolves the consuming repository from `repo_dir`, or from the survey repository-root search when it is blank
- verify: count(subject="survey repository-root resolution for expansion", equals=1)
- does: consumes an existing inventory unchanged when it is valid JSON with a `units` list
- verify: count(subject="reused frozen inventories", equals=1)
- does: preserves the existing inventory's unit entries and statuses when reusing it
- verify: unchanged(subject="frozen survey inventory")
- does: rejects an existing inventory that is invalid JSON or lacks a `units` list without re-expanding rules
- verify: json_path(path="$.expand_ok", equals=false)
- does: rejects expansion when the rules file is absent
- verify: json_path(path="$.expand_errors", matches=".*rules file.*")
- does: rejects expansion when the rules document is not a mapping
- verify: json_path(path="$.expand_errors", matches=".*rules file root.*")
- does: rejects expansion when `rules` is absent, empty, or not a list
- verify: json_path(path="$.expand_errors", matches=".*rules.*non-empty list.*")
- does: reports every structural rule error before attempting expansion
- verify: count(subject="aggregated survey rule validation errors", equals=1)
- does: accepts `folder`, `file`, and `command` as rule kinds only
- verify: count(subject="survey enumeration rule kinds", equals=3)
- does: requires a non-empty `glob` for folder and file rules
- verify: count(subject="survey glob rule requirements", equals=1)
- does: requires a non-empty command and `unit_kind` for command rules
- verify: count(subject="survey command rule requirements", equals=1)
- does: expands folder and file rules in sorted repository-relative path order
- verify: count(subject="sorted survey glob expansions", equals=1)
- does: excludes glob matches whose repository-relative paths match any configured fnmatch exclusion
- verify: count(subject="excluded survey glob matches", equals=1)
- does: runs command rules from the resolved repository root with a five-minute timeout
- verify: count(subject="survey enumeration commands", equals=1)
- does: rejects command rules that fail to start or exit non-zero
- verify: json_path(path="$.expand_ok", equals=false)
- does: rejects command rules that emit no non-empty lines
- verify: json_path(path="$.expand_errors", matches=".*emitted no units.*")
- does: emits one pending unit for each non-empty command output line using the declared `unit_kind`
- verify: count(subject="command-enumerated survey units", equals=1)
- does: de-duplicates a unit id matched by more than one rule while retaining its first kind
- verify: count(subject="deduplicated survey units", equals=1)
- does: rejects distinct unit ids that normalize to the same finding-record slug
- verify: json_path(path="$.expand_errors", matches=".*collide on record slug.*")
- does: rejects a successful expansion that produces no units
- verify: json_path(path="$.expand_ok", equals=false)
- does: writes a version-one inventory containing the rules path and pending units only after all validation and expansion checks pass
- verify: created(subject="materialized survey inventory")
- does: applies the configured rules path and inventory path relative to the resolved repository root
- verify: count(subject="repository-relative survey inventory paths", equals=1)
- verify: count(subject="expanded survey rules", equals=1)
- returns: an `Expansion` whose `expand_ok` identifies whether the inventory is usable
- verify: json_path(path="$.expand_ok", equals=true)
- returns: an `Expansion` whose `unit_count` reports the number of frozen or materialized units
- verify: json_path(path="$.unit_count", equals=1)
- returns: an `Expansion` whose `inventory_note` describes reuse or materialization
- verify: count(subject="inventory expansion results", equals=1)
- verify: count(subject="frozen survey inventories", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/inventory.py::expand_inventory`
- tests: `workflows/tests/author/shared/survey/test_inventory.py::test_folder_rules_materialize_the_unit_list`
- tests: `workflows/tests/author/shared/survey/test_inventory.py::test_an_existing_inventory_is_consumed_verbatim`
- tests: `workflows/tests/author/shared/survey/test_inventory.py::test_structural_rule_errors_are_reported_together`
- tests: `workflows/tests/author/shared/survey/test_inventory.py::test_units_colliding_on_a_record_slug_are_rejected`

### split_unit
- sig: `split_unit(logger: logging.Logger, inventory: str, unit_id: str, repo_dir: str = "") -> SplitResult`
- does: refuses to access the repository when `inventory` or `unit_id` is blank
- verify: json_path(path="$.split_ok", equals=false)
- does: resolves the inventory relative to the survey repository root
- verify: count(subject="resolved survey split inventories", equals=1)
- does: rejects an unreadable or invalid inventory without modifying it
- verify: unchanged(subject="unreadable survey inventory")
- does: rejects a unit id that is absent from the inventory
- verify: json_path(path="$.split_errors", matches=".*not found.*")
- does: rejects a unit whose kind is not `folder`
- verify: json_path(path="$.split_errors", matches=".*only folder units can split.*")
- does: rejects a folder unit whose path is not a directory
- verify: json_path(path="$.split_errors", matches=".*not a directory.*")
- does: replaces one folder unit with its immediate non-hidden, non-excluded children
- verify: count(subject="replaced folder survey units", equals=1)
- does: classifies each child as `folder` when it is a directory and `file` otherwise
- verify: count(subject="classified survey split children", equals=1)
- does: ignores hidden children and children matching the exclusions recorded by the inventory's rules
- verify: count(subject="filtered survey split children", equals=1)
- does: ignores a child whose id is already present elsewhere in the inventory
- verify: count(subject="deduplicated survey split children", equals=1)
- does: rejects a folder with no eligible children without modifying the inventory
- verify: json_path(path="$.split_errors", matches=".*no splittable children.*")
- does: preserves the rest of the inventory and leaves every inserted child status pending
- verify: count(subject="preserved split inventories", equals=1)
- does: writes the updated inventory only after eligible children have been found
- verify: persists(subject="split survey inventory")
- returns: a `SplitResult` whose `split_ok` identifies whether replacement succeeded
- verify: json_path(path="$.split_ok", equals=true)
- returns: a `SplitResult` whose `children_count` reports the number of inserted children
- verify: json_path(path="$.children_count", equals=2)
- returns: a `SplitResult` whose `split_errors` contains the diagnostic reason on rejection
- verify: count(subject="survey unit split results", equals=1)
- verify: count(subject="survey unit splits", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/inventory.py::split_unit`
- tests: `workflows/tests/author/shared/survey/test_inventory.py::test_a_split_replaces_the_unit_in_place`
- tests: `workflows/tests/author/shared/survey/test_inventory.py::test_split_children_honor_the_rules_excludes`
- tests: `workflows/tests/author/shared/survey/test_inventory.py::test_only_folder_units_can_split`
- tests: `workflows/tests/author/shared/survey/test_inventory.py::test_a_folder_with_no_splittable_children_says_so`
- tests: `workflows/tests/author/shared/survey/test_inventory.py::test_splitting_an_unknown_unit_is_reported_not_raised`

### select_next_unit
- sig: `select_next_unit(logger: logging.Logger, inventory: str = "docs/survey/inventory.json", findings_dir: str = "docs/survey/findings", repo_dir: str = "") -> UnitPick`
- does: uses `docs/survey/inventory.json` when the inventory argument is blank
- verify: json_path(path="$.reason", matches=".*")
- does: uses `docs/survey/findings` when the findings directory argument is blank
- verify: json_path(path="$.record_path", matches=".*")
- does: reports no selectable unit instead of raising when the inventory file is absent
- verify: json_path(path="$.has_unit", equals=false)
- does: reports no selectable unit instead of raising when the inventory is invalid JSON or lacks a usable unit list
- verify: json_path(path="$.has_unit", equals=false)
- does: loads the inventory and selects its first unit that is neither done nor blocked
- verify: count(subject="selected pending survey units", equals=1)
- does: treats `assessed` and `clean` as done statuses and `blocked` as set aside
- verify: count(subject="survey done and blocked status handling", equals=1)
- does: derives the finding-record path from the selected unit id with `record_slug`
- verify: count(subject="derived survey finding paths", equals=1)
- does: falls back to the unit id when the selected unit has no usable top-level path
- verify: count(subject="survey unit path fallbacks", equals=1)
- does: reports progress and unit-kind counts from the same worklist snapshot used for selection
- verify: count(subject="survey selection snapshots", equals=1)
- returns: a `UnitPick` containing unit identity, source path, kind, record path, and progress when a unit exists
- verify: count(subject="survey unit pick results", equals=1)
- returns: a `UnitPick` with `has_unit` false and a coverage handoff reason when no pending unit remains
- verify: count(subject="empty survey unit picks", equals=1)
- verify: count(subject="pending survey-unit selections", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/units.py::select_next_unit`
- tests: `workflows/tests/author/shared/survey/test_units.py::test_the_first_pending_unit_is_the_one_selected`

### mark_unit
- sig: `mark_unit(logger: logging.Logger, inventory: str, unit_id: str, record_path: str, fallback: str = "", repo_dir: str = "") -> MarkResult`
- does: refuses to access the repository when inventory, unit_id, or record_path is blank
- verify: json_path(path="$.marked", equals=false)
- does: stamps the matching inventory entry with the valid status read from its finding record
- verify: count(subject="record-derived survey status marks", equals=1)
- does: uses the fallback reason when a missing record has no supplied assessment reason
- verify: count(subject="fallback survey gap reasons", equals=1)
- does: marks the unit blocked when its record is absent or invalid and writes a blocked stub when no record exists
- verify: count(subject="blocked survey status marks", equals=1)
- does: leaves an existing invalid record unchanged while marking its inventory unit blocked
- verify: unchanged(subject="invalid finding record")
- does: keeps the blocked reason in `openGaps` so the coverage gate can resurface the unresolved unit
- verify: count(subject="durable survey gap reasons", equals=1)
- does: returns the record-derived status even when the inventory is absent, unreadable, or does not contain the unit
- verify: json_path(path="$.unit_status", matches=".*")
- does: reports `marked` false when the inventory cannot be read or the unit is not found
- verify: json_path(path="$.marked", equals=false)
- returns: a `MarkResult` identifying whether the inventory entry was marked and the resulting status or diagnostic note
- verify: count(subject="survey unit mark results", equals=1)
- verify: count(subject="survey-unit status marks", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/units.py::mark_unit`
- tests: `workflows/tests/author/shared/survey/test_units.py::test_a_missing_record_becomes_a_blocked_stub_rather_than_a_wedge`

### load_record
- sig: `load_record(text: str) -> dict`
- does: requires the input to begin with a YAML front-matter fence
- verify: count(subject="leading survey front-matter fences", equals=1)
- does: locates the closed front-matter block through the shared markdown parser
- verify: count(subject="parsed survey front-matter blocks", equals=1)
- does: loads the raw front-matter as YAML
- verify: count(subject="loaded survey front-matter YAML", equals=1)
- raises: `ValueError` when the record has no leading fence, no closing fence, invalid YAML, or a non-mapping front-matter value
- verify: count(subject="rejected survey record parses", equals=1)
- returns: the parsed record mapping
- verify: count(subject="survey record mappings", equals=1)
- verify: count(subject="parsed survey finding records", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/records.py::load_record`
- tests: `workflows/tests/author/shared/survey/test_records.py::test_a_record_with_no_front_matter_cannot_be_parsed`

### check_record
- sig: `check_record(record: dict, unit_id: str) -> list[str]`
- does: requires the record type to be `survey-finding`
- verify: count(subject="survey finding record types", equals=1)
- does: requires the record unit to equal the selected inventory unit
- verify: count(subject="survey finding record unit identities", equals=1)
- does: requires the record status to be `assessed`, `clean`, or `blocked`
- verify: count(subject="survey finding record statuses", equals=1)
- does: requires every finding to be a mapping with non-empty description, kebab-case remediation pattern, allowed effort, and non-empty evidence
- verify: count(subject="complete survey finding entries", equals=1)
- does: rejects `assessed` records with no findings
- verify: count(subject="assessed survey records with findings", equals=1)
- does: rejects `clean` records that contain findings
- verify: count(subject="clean survey records without findings", equals=1)
- verify: count(subject="strict survey record structure checks", equals=1)
- does: requires a non-empty `openGaps` list when the record is blocked
- verify: count(subject="blocked survey records with open gaps", equals=1)
- does: accepts `disposition: accepted` only on blocked records and rejects every other disposition value
- verify: count(subject="strict survey blocked-gap checks", equals=1)
- returns: every structural error for the selected unit, or an empty list when the record is valid
- verify: count(subject="strict survey record error lists", equals=1)
- verify: count(subject="strict survey-record validation results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/records.py::check_record`
- tests: `workflows/tests/author/shared/survey/test_records.py::test_every_structural_error_in_a_finding_is_reported_together`

### record_errors
- sig: `record_errors(record: dict, unit_id: str) -> list[str]`
- does: applies the type, unit, status, finding-shape, evidence, and status/findings consistency rules with compact messages
- verify: count(subject="compact survey record checks", equals=1)
- does: reports a blocked record with empty `openGaps` as a coverage defect
- verify: count(subject="compact blocked-gap checks", equals=1)
- does: omits strict disposition validation because coverage rejects blocked records unless their disposition is `accepted`
- verify: count(subject="coverage disposition handling", equals=1)
- returns: every coverage-facing structural error, or an empty list when the record is valid
- verify: count(subject="compact survey record error lists", equals=1)
- verify: count(subject="compact survey-record validation results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/records.py::record_errors`
- tests: `workflows/tests/author/shared/survey/test_records.py::test_an_invalid_record_is_reported_with_the_compact_wording`

### validate_record
- sig: `validate_record(logger: logging.Logger, record_path: str, unit_id: str, repo_dir: str = "") -> RecordCheck`
- does: rejects missing `record_path` or `unit_id` before accessing the repository
- verify: count(subject="required survey validation arguments", equals=1)
- does: resolves the record path relative to the survey repository root
- verify: count(subject="resolved survey finding paths", equals=1)
- does: loads one finding record from the resolved repository
- verify: count(subject="loaded per-unit finding records", equals=1)
- does: reports a missing record without raising
- verify: count(subject="missing per-unit finding records", equals=1)
- does: reports unparsable records without raising
- verify: count(subject="unparsable per-unit finding records", equals=1)
- does: reports structurally invalid records without making an assessment judgment
- verify: count(subject="per-unit finding record refusals", equals=1)
- returns: `RecordCheck(record_ok=True)` only when the record is complete and internally consistent
- verify: count(subject="valid per-unit finding records", equals=1)
- verify: count(subject="validated per-unit finding records", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/records.py::validate_record`
- tests: `workflows/tests/author/shared/survey/test_records.py::test_a_complete_assessed_record_validates`

### verify_records
- sig: `verify_records(logger: logging.Logger, inventory: str = "docs/survey/inventory.json", findings_dir: str = "docs/survey/findings", ref: str = "HEAD", repo_dir: str = "") -> VerifyResult`
- does: treats a missing inventory as a successful no-survey result with `nothing_surveyed` true
- verify: count(subject="missing survey inventory results", equals=1)
- does: requires the inventory JSON to contain a `units` list when the inventory exists
- verify: count(subject="parseable survey inventories", equals=1)
- does: rejects every pending unit
- verify: count(subject="pending survey units rejected", equals=1)
- does: requires every non-pending current unit to have a matching valid finding record
- verify: count(subject="complete survey unit coverage", equals=1)
- does: rejects malformed units, invalid statuses, missing records, malformed records, and inventory/record status mismatches
- verify: count(subject="survey record and inventory mismatches", equals=1)
- does: rejects blocked records without an accepted disposition
- verify: count(subject="unaccepted blocked survey gaps", equals=1)
- does: rejects a unit dropped from the committed inventory unless current paths show split lineage beneath the old path
- verify: count(subject="dropped survey units", equals=1)
- verify: count(subject="survey coverage defects", equals=1)
- does: reports counts for assessed, clean, blocked, and pending units from the current inventory
- verify: count(subject="survey coverage counts", equals=1)
- returns: `VerifyResult(holds=True, nothing_surveyed=False)` with counts when coverage is complete
- verify: count(subject="complete survey coverage result", equals=1)
- returns: `VerifyResult(holds=True, nothing_surveyed=True)` when no inventory exists
- verify: count(subject="empty survey coverage results", equals=1)
- returns: `VerifyResult(holds=False)` with diagnostic errors and a coverage report when coverage is defective
- verify: count(subject="failed survey coverage result", equals=1)
- verify: count(subject="survey coverage results", equals=1)
- verify: count(subject="survey coverage gate results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/records.py::verify_records`
- tests: `workflows/tests/author/shared/survey/test_records.py::test_a_fully_covered_survey_holds`

The package also provides dry-run callback implementations for the registered gate nodes. They
return successful blank models so a dry-run exercises the success branches without creating
survey artifacts.

### expanded
- sig: `expanded(*_args: object, **_kwargs: object) -> Expansion`
- returns: an `Expansion` marked successful for dry-run inventory expansion
- verify: count(subject="dry-run inventory expansion results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/stubs.py::expanded`

### split
- sig: `split(*_args: object, **_kwargs: object) -> SplitResult`
- returns: a `SplitResult` marked successful for dry-run unit splitting
- verify: count(subject="dry-run unit split results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/stubs.py::split`

### recorded
- sig: `recorded(*_args: object, **_kwargs: object) -> RecordCheck`
- returns: a `RecordCheck` marked successful for dry-run record validation
- verify: count(subject="dry-run record validation results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/stubs.py::recorded`

### verified
- sig: `verified(*_args: object, **_kwargs: object) -> VerifyResult`
- returns: a `VerifyResult` marked successful for dry-run coverage verification
- verify: count(subject="dry-run coverage results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/stubs.py::verified`

### partitioned
- sig: `partitioned(*_args: object, **_kwargs: object) -> PartitionCheck`
- returns: a `PartitionCheck` marked successful for dry-run partition validation
- verify: count(subject="dry-run partition results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/stubs.py::partitioned`

### emitted
- sig: `emitted(*_args: object, **_kwargs: object) -> EmitResult`
- returns: an `EmitResult` marked successful for dry-run artifact emission
- verify: count(subject="dry-run artifact emission results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/stubs.py::emitted`
