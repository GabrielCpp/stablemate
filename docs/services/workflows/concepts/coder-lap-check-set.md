---
type: concept
slug: coder-lap-check-set
title: Coder lap check set
---
# Coder lap check set

The lap's check set is every service whose gates a repair lap runs. It holds the plan's
services in plan order, then each declared service that owns a file the story changed, then
each declared service whose sources import a directory the story changed. A story that edits
a package another service imports runs that service's gates too, so a break in the importer
fails the lap that caused it. A changed directory that no declared service owns is shared
code, and QA reads it as one of the story's shared files. The set is resolved in the
[coder development flow](../flows/coder-dev.md) after the
[lap clone check](coder-lap-clone-check.md) and before any service gate.

- code: `workflows/src/workhorse_workflows/coder/shared/reach.py::__all__` @b0ced02578df
- rule: a shared directory has no gate of its own, because its importers' gates are the ones that exercise it
- rule: a story's reach is measured from its story base against the working tree, so an edit the turn has not committed still gates its importers
- rule: an importer is found by the names it imports the directory by, never by a substring of the directory's path, because a substring also matches a URL that happens to spell it
- rule: a quoted repository path or package name counts only after an import keyword, because a string literal such as a cloud account id can spell a package name
- rule: a repository whose services declare no path adds nothing to the set, because a file cannot be mapped to the service that owns it
- prefers: gating one service too many over missing an importer, because a missed importer ships a break the story caused to the next story
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_lap_gates_a_service_the_check_set_adds_after_the_plan_services`
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_check_set_receives_the_dispatch_and_the_story_identity`
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_check_set_is_not_consulted_when_the_clone_check_finds_a_copy`
- tests: `workflows/tests/coder/qa/test_flow.py::test_the_owner_is_told_the_plan_s_shared_packages_then_the_check_set_s_without_repeats`
- detail: [coder development flow](../flows/coder-dev.md)
- detail: [coder lap clone check](coder-lap-clone-check.md)

## Methods

### resolve_check_set

- sig: `resolve_check_set(logger, dispatch, story_slug="", story_id="", repo_dir="", workspace="") -> CheckSet`
- does: keeps every plan dispatch entry first, in plan order
- verify: json_path(path="$.checks[0].service", equals="acme::api")
- does: scans each code repository of the dispatch once, skipping `docs` entries
- verify: count(subject="check set scans per code repository", equals=1)
- does: holds each declared service that owns a changed file once, after the plan entries
- verify: count(subject="services added for owning a changed file", equals=1)
- does: holds each declared service with a file that imports a changed directory, after the owners
- verify: json_path(path="$.checks[1].service", equals="acme::report")
- does: lists each changed directory no declared service owns as `repo::path` in `shared`
- verify: json_path(path="$.shared[0]", matches="^acme::.+")
- raises: `WorkflowFailed` when a scanned repository has no story base
- verify: json_path(path="$.error", matches="^the check set found no story base in ")
- returns: a `CheckSet` equal to the dispatch, with empty `shared`, when the story changed only private code
- verify: json_path(path="$.shared", equals="[]")
- code: `workflows/src/workhorse_workflows/coder/shared/reach.py::resolve_check_set` @b0ced02578df
- tests: `workflows/tests/coder/shared/test_reach.py::test_a_changed_package_gates_the_service_that_imports_it_by_module_path`
- tests: `workflows/tests/coder/shared/test_reach.py::test_a_private_edit_gates_the_plan_only`
- tests: `workflows/tests/coder/shared/test_reach.py::test_an_uncommitted_edit_counts`
- tests: `workflows/tests/coder/shared/test_reach.py::test_a_plan_entry_spelled_with_a_trailing_slash_is_not_added_twice`
- tests: `workflows/tests/coder/shared/test_reach.py::test_a_repo_whose_services_declare_no_path_gates_the_plan_only`
- tests: `workflows/tests/coder/shared/test_reach.py::test_a_docs_entry_s_repo_is_not_scanned`
- tests: `workflows/tests/coder/shared/test_reach.py::test_a_repository_with_no_story_base_stops_the_run`

### edited_units

- sig: `edited_units(root: Path, base: str) -> list[str]`
- does: takes the files changed between `base` and the working tree, both sides of a rename, plus untracked files
- verify: count(subject="untracked files counted as changed", equals=1)
- returns: the sorted directories of those files, without the repository root and without Markdown files
- verify: json_path(path="$", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/reach.py::edited_units` @b0ced02578df

### unit_identities

- sig: `unit_identities(root: Path, unit: str) -> list[str]`
- does: names the directory as a quoted repository path after `from`, `import`, `require(` or `import(`, and in Python dot form when every segment is an identifier
- verify: json_path(path="$[0]", matches="^from \".+\"$")
- does: names the package of the nearest manifest above the directory: a quoted `go.mod` module path, a `package.json` name after an import keyword, a `pubspec.yaml` name or a `pyproject.toml` project name
- verify: json_path(path="$", matches="example\\.com/api/auth")
- does: starts the manifest walk from the nearest existing ancestor when the directory was deleted
- verify: count(subject="identities yielded for a deleted directory", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/reach.py::unit_identities` @b0ced02578df
- tests: `workflows/tests/coder/shared/test_reach.py::test_a_package_json_name_is_how_a_service_imports_a_sibling_package`
- tests: `workflows/tests/coder/shared/test_reach.py::test_a_pyproject_name_is_how_a_service_imports_a_sibling_library`
- tests: `workflows/tests/coder/shared/test_reach.py::test_a_string_literal_that_spells_a_package_name_is_not_an_import`
- tests: `workflows/tests/coder/shared/test_reach.py::test_a_deleted_directory_still_yields_its_manifest_identity`

### relative_importers

- sig: `relative_importers(root: Path, unit: str, paths: list[str]) -> list[str]`
- does: resolves each quoted `./` or `../` path in a service's source against its file
- verify: count(subject="relative imports resolved against their file", equals=1)
- returns: the files whose resolved path lands inside the directory
- verify: json_path(path="$[0]", matches="^packages/web/")
- code: `workflows/src/workhorse_workflows/coder/shared/reach.py::relative_importers` @b0ced02578df
- tests: `workflows/tests/coder/shared/test_reach.py::test_a_relative_import_into_a_shared_directory_gates_the_importer_and_marks_it_shared`

### owner

- sig: `owner(path: str, service_paths: list[str]) -> str | None`
- returns: the longest declared service path that holds `path`, where `.` holds every path
- verify: json_path(path="$", equals="packages/web")
- returns: `None` when no declared service holds `path`
- verify: json_path(path="$", equals="null")
- code: `workflows/src/workhorse_workflows/coder/shared/reach.py::owner` @b0ced02578df
- tests: `workflows/tests/coder/shared/test_reach.py::test_the_longest_declared_path_owns_a_file`
