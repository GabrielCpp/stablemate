---
type: concept
slug: source-inventory-filter
title: Source inventory filtering and operational surface detection
---
# Source inventory filtering and operational surface detection

The machinery that partitions a source tree into coverage units: readable code modules + symbols
(the **code surface**) and documented run operations (the **operational surface**). A file matches
the code surface when it contains source in a supported language (Go, Python, TypeScript, PHP, Twig)
and is not filtered by the exclusion rules. The operational surface is the set of make/just targets,
docker-compose services, npm/poetry scripts, and entry points — evidence that the repository can be
run and thus must be documented by a runbook.

The two predicates are used together by the source inventory node (`inventory_source`) to separate
what counts as source from what does not. The filtering predicate ensures the code crawl is
exhaustive (no readable units slip through) and grounded (test fixtures and build artifacts are
counted only when intentionally cited as documentation subjects). The operational detector surfaces
the run recipes that force the runbook profile — an undocumented operational surface counts as a
coverage unit, making the book incomplete until a `runbook` node claims it.

- code: `workflows/src/workhorse_workflows/okf_builder/main/nodes/coverage.py`
- detail: [OKF-builder main build machine](okf-builder-main-build-machine.md) — `inventory_source` node

## Methods

### skipped

- sig: `skipped(path: Path, root: Path, excludes: list[str]) -> bool`
- does: returns `True` when the path matches any configured exclude pattern (exact match, directory prefix, or glob), when its directory parts include a known build/cache/vendor/test directory (`.git`, `__pycache__`, `node_modules`, `build`, `dist`, `vendor`, `tests`, `.venv`, etc.), when the filename has a generated suffix (`.gen.go`, `.generated.go`, `.d.ts`) or test suffix (`_test.py`, `.test.ts`, `.spec.tsx`, `Test.php`), when the filename starts with a test prefix (`test_`), or when the filename is `conftest.py`
- verify: json_path(path="return value", equals=true)
- returns: `False` when the path is readable source that should be inventoried
- verify: json_path(path="return value", equals=false)
- code: `workflows/src/workhorse_workflows/okf_builder/main/nodes/coverage.py::skipped`
- tests: `workflows/tests/okf_builder/test_inventory_skips.py::test_a_test_or_vendored_file_is_not_a_unit`
- tests: `workflows/tests/okf_builder/test_inventory_skips.py::test_a_source_file_is_a_unit`

The exclusions are service-scoped (read from the builder config) and checked three ways: exact
match, directory prefix, or glob. Built-in skips include `.git`, `__pycache__`, `node_modules`,
`build`, `dist`, `vendor`, `tests`, `.venv`, and similar paths — these are always skipped
regardless of config. A file ending in `.gen.go`, `.generated.go`, or `.d.ts` is filtered because
it is generated and not a documentation subject. Test files (`_test.py`, `.test.ts`, `.spec.tsx`,
`Test.php`, `conftest.py`) are filtered because tests are cited by `tests:` bullets, not covered as
first-class source. Test functions — prefixed `test_` — are likewise filtered at the symbol level.

### operational_units

- sig: `operational_units(source: Path, repo_root: Path, excludes: list[str], errors: list[str]) -> list[dict[str, str]]`
- does: scans the repository root and source tree for evidence of runnable operations
- verify: json_path(path="$", matches=".+")
- returns: a list of dicts, each naming a discovered operation `{"kind": "<operation_type>", "name": "<name>", "evidence": "<file>:<name>"}`
- verify: json_path(path="$.kind", matches="make-target|just-recipe|compose-service|package-script|console-script|entry-point")
- returns: the `evidence` field holds the repo-root-relative path and the extracted name, divided by a colon — this grounds the operation in the code that declares it
- verify: json_path(path="$.evidence", matches="[^:]+:[^:]+")
- code: `workflows/src/workhorse_workflows/okf_builder/main/nodes/coverage.py::operational_units`

The function discovers operations by scanning candidate files: all files at the repo root, plus
every non-filtered file in the source tree. It detects each kind of operation via parsing:

- **make/just targets** — extracts recipe names from `Makefile`/`makefile`/`GNUmakefile`/`justfile` via regex, excluding pattern rules (`%` names) and duplicates
- **docker-compose services** — extracts top-level `services:` children from compose files (YAML indent-based, no parser)
- **npm scripts** — extracts keys from the `scripts` object in `package.json`
- **poetry/setuptools scripts** — extracts both `[project.scripts]` and `[tool.poetry.scripts]` entries from `pyproject.toml`
- **entry points** — detects `__main__.py` files and names them by their package directory

Each discovered operation is added to the list once (deduplicated by evidence) and appended to the
`errors` list if file reading or parsing fails. The function is permissive: a malformed YAML or JSON
file does not abort the scan, it records the error and continues.

