---
type: runbook
slug: farrier-tests
title: Farrier test suite
---
# Farrier test suite

This CLI test tier exercises Farrier's library resolution, configuration, rendering, generated
output ownership, hook wiring, scaffolding, diagnostics, and launcher behavior without booting an
external service. Tests create temporary libraries and repositories; the suite-wide fixtures in
`farrier/tests/conftest.py` prevent both network access and reads from the developer's real
configuration.

Specs live at `farrier/tests/test_*.py` across the 31 test modules: `test_agents_mk.py`, `test_base_fetch_on_install.py`,
`test_config_profiles_cli.py`, `test_config_resolution.py`, `test_copilot_open_skills.py`,
`test_doctor_command.py`, `test_drift_report.py`, `test_frontmatter_parsing.py`,
`test_gitignore_migration.py`, `test_group_prefix.py`, `test_hook_managers.py`,
`test_init_command.py`, `test_install_prefix.py`, `test_launcher_make.py`,
`test_library_browse.py`, `test_library_check.py`, `test_local_instruction_mapping.py`,
`test_makefile_include.py`, `test_pipx.py`, `test_policies.py`, `test_provenance_banner.py`,
`test_qa_evidence_ignore.py`, `test_scaffold_command.py`, `test_selection_misses.py`,
`test_skill_assets.py`, `test_skill_hooks.py`, `test_skill_lookup_prefix_fallback.py`,
`test_skill_tags.py`, `test_source_command.py`, `test_tagged_deletion.py`, and `test_user_install.py`.

Add a test beside the module for the behavior it exercises and use its temporary-path fixtures;
tests that need repository-wide isolation inherit `_no_base_fetch` and `_no_real_config` from
`farrier/tests/conftest.py`. Run one test with a pytest node selector, for example
`uv run pytest tests/test_frontmatter_parsing.py::test_front_matter_survives_crlf_and_a_missing_trailing_newline -q`.
The root `test` job runs `make test`, and the Farrier package target below is part of that blocking
CI gate.

- driver: cli
- environment: [Python and uv environment](farrier-python-environment.md)
- surfaces: [farrier CLI](../farrier.md)
- code: `farrier/Makefile::test`
- working-directory: farrier

## Steps

### prepare-workspace

- kind: prepare
- run: uv sync --all-packages
- working-directory: .
- timeout: 120
- provenance: derived

### run-farrier-tests

- kind: run
- run: uv run pytest tests -q -n auto --dist worksteal
- working-directory: farrier
- timeout: 120
- produces: pytest terminal result for `farrier/tests`
- verify: [Farrier test target](../../../../farrier/Makefile)
- provenance: derived

### confirm-farrier-tests-pass

- kind: verify
- run: uv run pytest tests -q -n auto --dist worksteal
- working-directory: farrier
- timeout: 120
- provenance: derived
