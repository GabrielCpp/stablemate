---
type: concept
slug: workflow-kit-workspace
title: Workflow kit workspace
---
# Workflow kit workspace

The workspace kit reads the [`.code-workspace` format](../../workhorse/code-workspace-file.md),
derives a single-repository workspace from the supplied repository directory when no manifest is
present, and does not let `agents.yml` rename that repository key. Its checkout operation supports
the default disposable clone and a host-backed worktree: worktrees are detached, preserve committed
and uncommitted work across a restart, prune stale registrations, and refuse remote URLs because
both sides must share the host path.

- code: `workflows/src/workhorse_workflows/kit/workspace.py::resolve_workspace`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_read_workspace_file`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_repo_name_from_dir`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_git_network_command`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_has_unsynced_work`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_set_origin_url`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_add_worktree`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::checkout_workspace`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::get_repo_config`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::build_dispatch_list`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::get_affected_repos`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_main`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::SOURCE_MODES`
- code: `workflows/tests/test_kit_worktree.py::host_repo`
- tests: `workflows/tests/test_kit_workspace.py::test_resolve_workspace_uses_the_repo_dir_argument_over_cwd`
- tests: `workflows/tests/test_kit_workspace.py::test_a_repo_is_named_by_its_directory_not_by_its_agents_yml`
- tests: `workflows/tests/test_kit_workspace.py::test_git_network_command_uses_configured_token_env`
- tests: `workflows/tests/test_kit_worktree.py::test_two_concurrent_runs_each_get_their_own_tree_of_one_repo`
- tests: `workflows/tests/test_kit_worktree.py::test_uncommitted_work_survives_a_restart_too`
- tests: `workflows/tests/test_kit_worktree.py::test_a_remote_url_is_refused_with_the_reason`

## Methods

### _repo_name_from_dir

- sig: `_repo_name_from_dir(path: Path) -> str`
- does: derives the repository key from the directory basename
- verify: json_path(path="$.repo_name", matches="^[^._]*$")
- does: replaces periods and underscores with hyphens
- verify: json_path(path="$.repo_name", matches="^[^._]*$")
- does: replaces other non-alphanumeric or non-slash characters with hyphens
- verify: json_path(path="$.repo_name", matches="^[a-zA-Z0-9/-]+$")
- does: collapses repeated hyphens
- verify: json_path(path="$.repo_name", matches="^(?!.*--).*$")
- does: strips edge hyphens
- verify: json_path(path="$.repo_name", matches="^[^-].*[^-]$|^[^-]$")
- does: lowercases the result
- returns: the normalized directory-derived repository key
- verify: json_path(path="$.repo_name", matches="^[a-z0-9][a-z0-9/-]*$")
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_repo_name_from_dir`

### _read_workspace_file

- sig: `_read_workspace_file(workspace_file: str | Path) -> tuple[list[dict], Path] | None`
- does: returns no manifest when the supplied path is empty or does not exist
- verify: absent(subject="workspace manifest result")
- does: parses an existing manifest as JSONC through the shared JSON loader
- verify: count(subject="workspace folders parsed", equals=1)
- raises: propagates the JSON loader's parse error for malformed existing input
- verify: count(subject="malformed workspace parse errors", equals=1)
- returns: the manifest's `folders` list and the manifest parent directory
- verify: json_path(path="$.folders", equals="parsed workspace folders")
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_read_workspace_file`

### resolve_workspace

- sig: `resolve_workspace(workspace_file: str | Path = "", repo_dir: str | Path = "") -> dict[str, dict]`
- does: uses an existing workspace manifest when `workspace_file` names one
- verify: count(subject="workspace folders resolved from an existing manifest", equals=1)
- does: otherwise resolves `repo_dir` through the repository-root helper and synthesizes one folder rooted at that checkout
- verify: json_path(path="$.repo.path", matches=".*/repo")
- does: resolves each manifest folder path relative to the manifest directory
- verify: json_path(path="$.repo.path", matches=".*/repo")
- does: uses the normalized checkout directory name for the single-repository fallback key
- verify: json_path(path="$.repo", equals="normalized directory name")
- does: adds each folder's absolute `path` to the result
- verify: created(subject="each workspace folder path entry")
- verify: json_path(path="$.repo.path", matches="^/")
- does: merges a valid `agents.yml` `template` mapping and `workspace` mapping into that folder's record
- verify: json_path(path="$.repo.workspace_value", equals="configured value")
- does: degrades an absent, unreadable, or invalid `agents.yml` to a path-only record for that folder
- verify: json_path(path="$.repo.path", matches="^/")
- returns: a mapping keyed by manifest folder names or the normalized fallback name
- code: `workflows/src/workhorse_workflows/kit/workspace.py::resolve_workspace`
- tests: `workflows/tests/test_kit_workspace.py::test_resolve_workspace_uses_the_repo_dir_argument_over_cwd`
- tests: `workflows/tests/test_kit_workspace.py::test_resolve_workspace_falls_back_to_cwd_without_a_repo_dir`
- tests: `workflows/tests/test_kit_workspace.py::test_a_repo_is_named_by_its_directory_not_by_its_agents_yml`

### _has_unsynced_work

- sig: `_has_unsynced_work(dest: Path, branch: str) -> bool`
- does: detects uncommitted files in the destination working tree
- verify: json_path(path="$.unsynced", equals=true)
- does: detects commits in `HEAD` that are not reachable from `origin/<branch>`
- verify: json_path(path="$.unsynced", equals=true)
- returns: `true` when either local changes or local-only commits exist, otherwise `false`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_has_unsynced_work`

### _git_network_command

- sig: `_git_network_command(*args: str, token_env: str = credentials.GIT_CREDENTIAL_ENV) -> list[str]`
- does: returns the plain Git command when the named credential variable is absent
- verify: json_path(path="$.command", equals="git clone source")
- does: otherwise prepends a transient credential helper that names the variable without embedding its secret value
- verify: omits(subject="Git command credential helper", text="secret value")
- returns: a Git argument list suitable for clone or fetch
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_git_network_command`
- tests: `workflows/tests/test_kit_workspace.py::test_git_network_command_uses_configured_token_env`
- tests: `workflows/tests/test_kit_workspace.py::test_git_network_command_needs_no_token_for_public_or_local_clone`

### _set_origin_url

- sig: `_set_origin_url(dest: Path, url: str) -> None`
- does: leaves an existing `origin` unchanged when its URL already equals the configured URL
- verify: count(subject="origin URL changes for an already matching remote", equals=0)
- does: ensures an existing `origin` has the configured URL
- verify: json_path(path="$.origin.url", equals="configured URL")
- does: adds the destination's `origin` when it has no `origin`
- verify: created(subject="the destination's origin remote")
- returns: `None` after the remote has the configured URL
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_set_origin_url`

### _add_worktree

- sig: `_add_worktree(source: Path, dest: Path, ref: str, name: str, logger: logging.Logger) -> None`
- does: leaves an existing destination worktree untouched
- verify: unchanged(subject="existing worktree contents")
- does: refuses a source that is not a local Git repository
- verify: count(subject="invalid worktree source errors", equals=1)
- does: prunes registrations for deleted worktrees before adding a new one
- verify: absent(subject="stale deleted worktree registration")
- verify: created(subject="the source repository's worktree registration for dest")
- does: creates a detached worktree at `dest` from `ref`, sharing the source repository's objects and refs
- verify: created(subject="detached worktree at the destination")
- verify: json_path(path="$.worktree.head", equals="detached")
- raises: raises `ValueError` when the source is not a Git repository
- verify: count(subject="invalid worktree source errors", equals=1)
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_add_worktree`
- tests: `workflows/tests/test_kit_worktree.py::test_the_worktree_is_detached_so_the_branch_stays_free`
- tests: `workflows/tests/test_kit_worktree.py::test_a_deleted_run_directory_does_not_poison_the_path_forever`
- tests: `workflows/tests/test_kit_worktree.py::test_pruning_never_touches_a_live_worktree`

### checkout_workspace

- sig: `checkout_workspace(workspace_file: str | Path = "", workspace_root: str | Path = "/workspace", *, repo_url: str = "", repo_name: str = "repo", repo_branch: str = "main", token_env: str = credentials.GIT_CREDENTIAL_ENV, source_mode: str = "clone", worktree_root: str | Path = "") -> None`
- does: rejects every source mode except `clone` and `worktree`
- verify: count(subject="unknown checkout source mode errors", equals=1)
- does: uses every manifest folder carrying `url`, while skipping folders without `url`
- verify: count(subject="checked out URL-bearing folders", equals=2)
- does: falls back to one `repo_url` folder when no manifest exists
- verify: created(subject="single-repository checkout")
- does: returns without creating a checkout when neither a manifest nor `repo_url` is supplied
- verify: absent(subject="checkout destination")
- does: creates a clone under `workspace_root/<name>` with the selected branch and single-branch history
- verify: created(subject="clone checkout")
- does: fetches an existing clone and hard-resets only when it has no uncommitted changes or local-only commits
- verify: json_path(path="$.checkout.reset", equals=true)
- does: preserves an existing clone with unsynced work instead of resetting it
- verify: unchanged(subject="existing clone with unsynced work")
- does: creates a detached worktree under `worktree_root/<name>` in worktree mode
- verify: created(subject="detached worktree checkout")
- raises: propagates a failed Git subprocess as `CalledProcessError`
- verify: count(subject="failed Git checkout errors", equals=1)
- returns: `None` after all selected folders are processed
- code: `workflows/src/workhorse_workflows/kit/workspace.py::checkout_workspace`
- tests: `workflows/tests/test_kit_worktree.py::test_two_concurrent_runs_each_get_their_own_tree_of_one_repo`
- tests: `workflows/tests/test_kit_worktree.py::test_an_existing_worktree_is_left_exactly_as_it_is`
- tests: `workflows/tests/test_kit_worktree.py::test_uncommitted_work_survives_a_restart_too`
- tests: `workflows/tests/test_kit_worktree.py::test_a_remote_url_is_refused_with_the_reason`
- tests: `workflows/tests/test_kit_worktree.py::test_clone_mode_is_still_the_default`

### get_repo_config

- sig: `get_repo_config(repo_name: str, key: str, default=None, *, repos: dict | None = None, workspace_file: str | Path = "", repo_dir: str | Path = "")`
- does: resolves the workspace when `repos` is omitted
- verify: count(subject="workspace resolutions for omitted repository map", equals=1)
- does: returns the named repository setting when present
- verify: json_path(path="$.value", equals="configured repository setting")
- returns: `default` when the repository or setting is absent
- verify: json_path(path="$.value", equals="caller default")
- code: `workflows/src/workhorse_workflows/kit/workspace.py::get_repo_config`

### build_dispatch_list

- sig: `build_dispatch_list(plan_ctx: dict, repos: dict[str, dict], *, fallback: bool = False) -> list[dict]`
- does: indexes plan services by `<repo>::<path>` and follows `implementation_order` when it is non-empty
- verify: json_path(path="$.dispatch[0].service", equals="repo::service")
- does: otherwise preserves the services' declared order and skips unknown ordered keys
- verify: count(subject="dispatch records for known services", equals=1)
- does: projects repository paths and workspace QA settings into each dispatch record
- verify: json_path(path="$.dispatch[0].cwd", equals="resolved repository path")
- does: defaults service type to `unknown`, plan file to `plan.md`, QA mode to `cli`, and missing lists or verification to empty values
- verify: json_path(path="$.dispatch[0].type", equals="unknown")
- does: selects `backend_layer_name`, then `mobile_layer_name`, then service type as the label
- verify: json_path(path="$.dispatch[0].label", equals="selected layer label")
- does: emits one first-repository fallback record only when `fallback` is true, no dispatch records exist, and repositories are available
- verify: count(subject="fallback dispatch records", equals=1)
- returns: the ordered dispatch record list
- code: `workflows/src/workhorse_workflows/kit/workspace.py::build_dispatch_list`

### get_affected_repos

- sig: `get_affected_repos(plan_ctx: dict, repos: dict[str, dict]) -> list[str]`
- does: selects service repository names that exist in the resolved repository map
- verify: count(subject="affected repositories present in workspace", equals=1)
- does: removes duplicates and sorts the selected names
- verify: removed(subject="duplicate selected repository name")
- verify: json_path(path="$.affected", equals="sorted unique repository names")
- returns: the sorted, deduplicated repository-name list
- code: `workflows/src/workhorse_workflows/kit/workspace.py::get_affected_repos`

### _main

- sig: `_main(argv: list[str] | None = None) -> int`
- does: parses checkout settings from command-line flags and delegates them to `checkout_workspace`
- verify: count(subject="checkout delegations from the module CLI", equals=1)
- returns: exit status `0` after delegation returns
- verify: json_path(path="$.exit_status", equals=0)
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_main`
