---
type: concept
slug: survey-shared-library
title: Author shared survey library
---
# Author shared survey library

The author and parity surveyors share this library's frozen-worklist protocol. Inventory
materialization creates a durable list of units; traversal selects pending entries and records
their status; the record gates make each assessment and the whole inventory auditable. The
surveyor blueprint is separate from the author node blueprint, but the author registry merges it
so both flows resolve the same shared nodes.

- code: `workflows/src/workhorse_workflows/author/shared/survey/blueprint.py::blueprint`
- tests: `workflows/tests/author/shared/survey/test_inventory.py::test_an_existing_inventory_is_consumed_verbatim`

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
- semantics: inventory status vocabulary; only `pending` is selectable and `assessed` or `clean` are completed
- verify: count(subject="survey inventory status semantics", equals=1)
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
- does: consumes an existing parseable inventory unchanged, including its pending statuses
- verify: count(subject="reused frozen inventories", equals=1)
- does: validates non-empty rules and expands folder, file, or command rules while applying exclusions
- verify: count(subject="expanded survey rules", equals=1)
- does: rejects empty matches, command failures, invalid rule structure, and record-slug collisions
- verify: count(subject="rejected survey expansions", equals=1)
- does: writes a version-one JSON inventory only after successful non-empty expansion
- verify: count(subject="written survey inventories", equals=1)
- returns: an `Expansion` reporting success, unit count, and the materialization or frozen-inventory note
- verify: count(subject="inventory expansion results", equals=1)
- verify: count(subject="frozen survey inventories", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/inventory.py::expand_inventory`
- tests: `workflows/tests/author/shared/survey/test_inventory.py::test_an_existing_inventory_is_consumed_verbatim`

### split_unit
- sig: `split_unit(logger: logging.Logger, inventory: str, unit_id: str, repo_dir: str = "") -> SplitResult`
- does: replaces one folder unit with its immediate non-hidden, non-excluded children
- verify: count(subject="replaced folder survey units", equals=1)
- does: preserves the rest of the inventory and leaves child statuses pending
- verify: count(subject="preserved split inventories", equals=1)
- does: rejects missing inputs, unreadable inventories, non-folder units, absent directories, and folders with no eligible children
- verify: count(subject="rejected survey unit splits", equals=1)
- returns: a `SplitResult` with the child count on success or a diagnostic error on rejection
- verify: count(subject="survey unit split results", equals=1)
- verify: count(subject="survey unit splits", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/inventory.py::split_unit`
- tests: `workflows/tests/author/shared/survey/test_inventory.py::test_a_split_replaces_the_unit_in_place`

### select_next_unit
- sig: `select_next_unit(logger: logging.Logger, inventory: str = "docs/survey/inventory.json", findings_dir: str = "docs/survey/findings", repo_dir: str = "") -> UnitPick`
- does: loads the inventory and selects its first unit that is neither done nor blocked
- verify: count(subject="selected pending survey units", equals=1)
- does: derives the finding-record path from the selected unit id with `record_slug`
- verify: count(subject="derived survey finding paths", equals=1)
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
- does: stamps the matching inventory entry with the valid status read from its finding record
- verify: count(subject="record-derived survey status marks", equals=1)
- does: marks the unit blocked when its record is absent or invalid and writes a blocked stub when no record exists
- verify: count(subject="blocked survey status marks", equals=1)
- does: keeps the blocked reason in `openGaps` so the coverage gate can resurface the unresolved unit
- verify: count(subject="durable survey gap reasons", equals=1)
- returns: a `MarkResult` identifying whether the inventory entry was marked and the resulting status or diagnostic note
- verify: count(subject="survey unit mark results", equals=1)
- verify: count(subject="survey-unit status marks", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/units.py::mark_unit`
- tests: `workflows/tests/author/shared/survey/test_units.py::test_a_missing_record_becomes_a_blocked_stub_rather_than_a_wedge`

### load_record
- sig: `load_record(text: str) -> dict`
- does: parses the leading YAML front-matter block with the shared markdown parser before loading its YAML mapping
- verify: count(subject="parsed survey front-matter blocks", equals=1)
- raises: `ValueError` when the record has no leading fence, no closing fence, invalid YAML, or a non-mapping front-matter value
- verify: count(subject="rejected survey record parses", equals=1)
- returns: the parsed record mapping
- verify: count(subject="survey record mappings", equals=1)
- verify: count(subject="parsed survey finding records", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/records.py::load_record`
- tests: `workflows/tests/author/shared/survey/test_records.py::test_a_record_with_no_front_matter_cannot_be_parsed`

### check_record
- sig: `check_record(record: dict, unit_id: str) -> list[str]`
- does: checks record type, matching unit id, allowed status, finding shape, evidence, and status/findings consistency
- verify: count(subject="strict survey record structure checks", equals=1)
- does: requires a non-empty `openGaps` list for blocked records and accepts only `accepted` dispositions on blocked records
- verify: count(subject="strict survey blocked-gap checks", equals=1)
- returns: every structural error for the selected unit, or an empty list when the record is valid
- verify: count(subject="strict survey record error lists", equals=1)
- verify: count(subject="strict survey-record validation results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/records.py::check_record`
- tests: `workflows/tests/author/shared/survey/test_records.py::test_every_structural_error_in_a_finding_is_reported_together`

### record_errors
- sig: `record_errors(record: dict, unit_id: str) -> list[str]`
- does: applies the record validation rules with compact messages suitable for a coverage report
- verify: count(subject="compact survey record checks", equals=1)
- returns: every coverage-facing structural error, or an empty list when the record is valid
- verify: count(subject="compact survey record error lists", equals=1)
- verify: count(subject="compact survey-record validation results", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/records.py::record_errors`
- tests: `workflows/tests/author/shared/survey/test_records.py::test_an_invalid_record_is_reported_with_the_compact_wording`

### validate_record
- sig: `validate_record(logger: logging.Logger, record_path: str, unit_id: str, repo_dir: str = "") -> RecordCheck`
- does: loads one finding record from the resolved repository and validates it against its selected unit
- verify: count(subject="loaded per-unit finding records", equals=1)
- does: reports missing, unparsable, or structurally invalid records without making an assessment judgment
- verify: count(subject="per-unit finding record refusals", equals=1)
- returns: `RecordCheck(record_ok=True)` only when the record is complete and internally consistent
- verify: count(subject="valid per-unit finding records", equals=1)
- verify: count(subject="validated per-unit finding records", equals=1)
- code: `workflows/src/workhorse_workflows/author/shared/survey/records.py::validate_record`
- tests: `workflows/tests/author/shared/survey/test_records.py::test_a_complete_assessed_record_validates`

### verify_records
- sig: `verify_records(logger: logging.Logger, inventory: str = "docs/survey/inventory.json", findings_dir: str = "docs/survey/findings", ref: str = "HEAD", repo_dir: str = "") -> VerifyResult`
- does: requires every current inventory unit to be non-pending and backed by a matching valid finding record
- verify: count(subject="complete survey unit coverage", equals=1)
- does: rejects malformed units, missing records, status mismatches, unaccepted blocked gaps, and dropped units without split lineage
- verify: count(subject="survey coverage defects", equals=1)
- does: treats a missing inventory as an explicit no-survey result rather than an error
- verify: count(subject="empty survey coverage results", equals=1)
- returns: `VerifyResult(holds=True)` with counts when coverage is complete, or diagnostic errors when it is not
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
