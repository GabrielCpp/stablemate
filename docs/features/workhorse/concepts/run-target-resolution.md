---
type: concept
slug: run-target-resolution
title: Run target resolution
---
# Run target resolution

Control and inbox commands resolve a named target locally before using groom as a fallback.
The accepted local spellings are a run id, its `<workflow>-<run-id>` directory name, or a path.
With no `--run`, the newest directory with a checkpoint and no terminal record is selected.
Groom lookup is restricted to the command's workflow and only accepts a returned directory that
exists on the current machine; failures become an actionable stderr message rather than a new
directory. The fallback returns a [live lookup result](../live-lookup.md) so the caller can
distinguish a local miss, an unavailable groom service, and a directory that cannot be opened here.

- code: `workhorse/workhorse/cli/target.py::resolve_target`
- code: `workhorse/workhorse/cli/target.py::groom_live_run`
- tests: `workhorse/tests/test_control_command.py::test_a_run_is_found_by_its_id_its_dir_name_or_its_path`
- tests: `workhorse/tests/test_control_command.py::test_an_id_groom_knows_resolves_to_the_run_dir_groom_names`
- tests: `workhorse/tests/test_control_command.py::test_a_groom_row_for_another_workflow_is_not_this_run`
- tests: `workhorse/tests/test_control_command.py::test_with_no_run_named_the_newest_unfinished_run_is_taken`
- tests: `workhorse/tests/test_control_command.py::test_a_run_that_does_not_exist_is_an_error_not_a_new_directory`
- tests: `workhorse/tests/test_inbox_command.py::test_an_id_groom_knows_is_read_from_the_run_dir_groom_names`

## Methods

### groom_live_run
- sig: `groom_live_run(run_id: str, workflow: str, url: str) -> LiveLookup`
- does: requests live-run rows from `<url>/api/live?run=<url-encoded run_id>`
- does: accepts exactly one returned directory when its workflow matches and the directory exists locally
- does: rejects rows for another workflow, malformed top-level responses, unavailable groom, and ambiguous or non-local directories as misses with explanatory notes
- returns: a [live lookup result](../live-lookup.md) containing the usable directory or no directory and the reason
- verify: json_path(path="$.run_dir", matches=".+")
- code: `workhorse/workhorse/cli/target.py::groom_live_run`

### resolve_target
- sig: `resolve_target(spec: str | None, runs_dir: Path, workflow_name: str, *, live: LiveLookupFn = groom_live_run) -> Path`
- does: resolves a named target locally before invoking the injected live lookup
- does: uses `GROOM_URL` when set, otherwise `http://127.0.0.1:8787`, for a named target that is absent locally
- does: writes the successful groom resolution note to stderr
- does: exits with status 1 and an error explaining the local search and live-lookup result when a named target cannot be resolved
- does: selects the newest unfinished checkpoint directory when no target name is supplied
- does: exits with status 1 when no unfinished checkpoint directory exists and instructs the operator to provide `--run`
- raises: `SystemExit(1)` when a named target is unavailable or no unfinished run exists
- verify: exit_status(code=1)
- returns: the resolved run directory for a named local target, a usable groom target, or the newest unfinished local run
- code: `workhorse/workhorse/cli/target.py::resolve_target`
