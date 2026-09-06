---
type: concept
slug: installed-workflow-discovery
title: Installed workflow discovery
---
# Installed workflow discovery

Workflow availability is derived from the machine's installed pipx distributions, not from
`agents.yml` or a separate registry. A distribution contributes a workflow for each exposed
`workhorse-<name>` console script, except the bare prefix and the `workhorse-agent` and
`workhorse-workflows` library scripts. The resulting names are sorted and duplicate names are
collapsed before the CLI's machine-readable output is printed.

The discovery record preserves the distribution name, version, origin, workflow names, and whether
the install was editable. A PyPI or VCS origin has no local path to mount. An origin that has path
shape remains a local path even after its directory disappears, so the human-readable command can
report the stale source instead of silently treating it as a package name.

`pipx list --json` is an external, versioned input. Missing pipx, a nonzero command result, an
unrecognizable JSON value, malformed JSON, or a changed metadata shape all mean that no workflows
are discoverable; they do not produce a traceback from the launcher path.

- code: `farrier/farrier/pipx.py::discover`
- code: `farrier/farrier/pipx.py::names`
- tests: `farrier/tests/test_pipx.py::test_a_workflow_is_a_workhorse_prefixed_console_script`
- tests: `farrier/tests/test_pipx.py::test_a_name_is_reported_once_even_from_two_distributions`
- tests: `farrier/tests/test_pipx.py::test_an_unrecognisable_payload_costs_workflows_not_a_traceback`
- tests: `farrier/tests/test_pipx.py::test_an_editable_install_whose_source_is_gone_is_flagged`

## Fields

### field: WORKFLOW_SCRIPT_PREFIX
- type: `str`
- required: true
- semantics: console-script prefix whose suffix names a runnable workflow
- code: `farrier/farrier/pipx.py::WORKFLOW_SCRIPT_PREFIX`

### field: distribution
- type: `str`
- required: true
- semantics: installed distribution name reported by pipx
- code: `farrier/farrier/pipx.py::Installed`

### field: workflows
- type: `tuple[str, ...]`
- required: true
- semantics: sorted workflow suffixes exposed by the distribution
- code: `farrier/farrier/pipx.py::Installed`

### field: origin
- type: `str`
- required: true
- semantics: pipx's verbatim PyPI name, remote URL, or host path
- code: `farrier/farrier/pipx.py::Installed`

### field: version
- type: `str`
- required: true
- semantics: installed distribution version reported by pipx
- code: `farrier/farrier/pipx.py::Installed`

### field: editable
- type: `bool`
- required: true
- semantics: whether pipx's install arguments include `--editable`
- code: `farrier/farrier/pipx.py::Installed`

## Methods

### method: local_path
- sig: `Installed.local_path -> Path | None`
- does: classifies remote-scheme origins as having no local source path
- does: classifies an absolute or slash-containing origin as a local path
- does: expands `~` in a local origin before returning it
- returns: `None` for PyPI names and VCS or HTTP origins
- returns: the expanded `Path` for a local origin even when the directory is absent
- verify: absent(subject="local path for a PyPI or remote origin")
- verify: json_path(path="$.local_path", matches="/.+/")
- code: `farrier/farrier/pipx.py::Installed.local_path`
- tests: `farrier/tests/test_pipx.py::test_a_pypi_install_has_no_local_path_to_mount`
- tests: `farrier/tests/test_pipx.py::test_a_vcs_install_has_no_local_path_either`
- tests: `farrier/tests/test_pipx.py::test_a_deleted_path_is_not_silently_reclassified_as_a_pypi_name`

### method: missing
- sig: `Installed.missing -> bool`
- does: reports true when the record has a local path and that path is not a directory
- does: reports false for remote or PyPI origins and existing local directories
- verify: json_path(path="$.missing", equals=true)
- code: `farrier/farrier/pipx.py::Installed.missing`
- tests: `farrier/tests/test_pipx.py::test_an_editable_install_whose_source_is_gone_is_flagged`

### method: workflows_from_apps
- sig: `workflows_from_apps(apps: object) -> tuple[str, ...]`
- does: returns an empty tuple when the apps value is not a list
- does: keeps string console scripts beginning with `workhorse-`, excluding the bare prefix and library scripts
- does: removes the `workhorse-` prefix and sorts the remaining workflow names
- returns: a tuple of workflow suffixes
- verify: count(subject="sorted workflow suffixes from console scripts", equals=3)
- code: `farrier/farrier/pipx.py::workflows_from_apps`
- tests: `farrier/tests/test_pipx.py::test_a_workflow_is_a_workhorse_prefixed_console_script`
- tests: `farrier/tests/test_pipx.py::test_the_bare_prefix_and_the_libraries_themselves_are_not_workflows`

### method: parse
- sig: `parse(payload: object) -> list[Installed]`
- does: returns an empty list for a non-mapping payload or a payload without a mapping `venvs`
- does: skips virtual environments whose metadata, main package, or workflow apps are absent or malformed
- does: constructs one immutable installed record from each workflow-providing main package
- does: marks a record editable only when `pip_args` is a list containing `--editable`
- does: sorts records by distribution name
- returns: discovered installed distributions with their workflow names, origin, version, and editability
- verify: count(subject="workflow-providing distributions parsed from a valid payload", equals=1)
- verify: count(subject="distributions returned for an unrecognizable payload", equals=0)
- code: `farrier/farrier/pipx.py::parse`
- tests: `farrier/tests/test_pipx.py::test_a_workflow_is_a_workhorse_prefixed_console_script`
- tests: `farrier/tests/test_pipx.py::test_venvs_that_provide_no_workflow_are_not_reported`
- tests: `farrier/tests/test_pipx.py::test_an_unrecognisable_payload_costs_workflows_not_a_traceback`

### method: discover
- sig: `discover() -> list[Installed]`
- does: runs `pipx list --json` through the module's subprocess seam
- does: returns no workflows when pipx cannot be executed or exits nonzero
- does: returns no workflows when stdout is malformed or decodes to an unrecognized payload
- returns: parsed installed workflow distributions
- verify: count(subject="workflows returned when pipx is unavailable or invalid", equals=0)
- code: `farrier/farrier/pipx.py::discover`
- tests: `farrier/tests/test_pipx.py::test_pipx_not_installed_means_no_workflows_not_a_broken_build`
- tests: `farrier/tests/test_pipx.py::test_pipx_failing_or_emitting_junk_means_no_workflows`
- tests: `farrier/tests/test_pipx.py::test_discover_reads_the_json_pipx_actually_emits`

### method: names
- sig: `names(found: list[Installed]) -> list[str]`
- does: collects every workflow suffix from every installed distribution
- does: removes duplicate suffixes when multiple distributions provide the same workflow
- does: sorts the resulting names alphabetically
- returns: a de-duplicated sorted list of runnable workflow names
- verify: count(subject="unique workflow names from duplicate providers", equals=2)
- code: `farrier/farrier/pipx.py::names`
- tests: `farrier/tests/test_pipx.py::test_a_name_is_reported_once_even_from_two_distributions`
