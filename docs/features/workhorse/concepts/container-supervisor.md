---
type: concept
slug: container-supervisor
title: Container supervisor
---
# Container supervisor

The container supervisor is the process boundary between operator environment and a
workflow run. It performs preflight, constructs the workflow command, optionally runs
groom's observer, and makes the workflow's final exit status the container's status.
It is not PID 1: Docker's `init: true` supplies tini for signal delivery and zombie
reaping. The observer is optional and never changes the run's outcome.

- code: `workhorse/supervisor.py::main`
- tests: `workhorse/tests/test_supervisor.py`

## Fields

### claude_home
- type: `Path`
- default: `/claude-state`
- verify: json_path(path="Layout.claude_home", equals="/claude-state")
- required: false
- verify: json_path(path="Layout.claude_home.required", equals=false)
- semantics: persistent HOME containing Claude state, credentials, and onboarding data
- verify: json_path(path="Layout.claude_home.semantics", equals="persistent HOME containing Claude state, credentials, and onboarding data")
- code: `workhorse/supervisor.py::Layout`
- detail: [Layout storage locations](layout-storage-locations.md)

### workspace
- type: `Path`
- default: `/workspace`
- verify: json_path(path="Layout.workspace", equals="/workspace")
- required: false
- verify: json_path(path="Layout.workspace.required", equals=false)
- semantics: writable root where checked-out repositories are materialized
- verify: json_path(path="Layout.workspace.semantics", equals="writable root where checked-out repositories are materialized")
- code: `workhorse/supervisor.py::Layout`
- detail: [Layout storage locations](layout-storage-locations.md)

### runs
- type: `Path`
- default: `/runs`
- verify: json_path(path="Layout.runs", equals="/runs")
- required: false
- verify: json_path(path="Layout.runs.required", equals=false)
- semantics: writable root for run artifacts
- verify: json_path(path="Layout.runs.semantics", equals="writable root for run artifacts")
- code: `workhorse/supervisor.py::Layout`
- detail: [Layout storage locations](layout-storage-locations.md)

### settings_src
- type: `Path`
- default: `/mnt/claude-settings.json`
- verify: json_path(path="Layout.settings_src", equals="/mnt/claude-settings.json")
- required: false
- verify: json_path(path="Layout.settings_src.required", equals=false)
- semantics: optional read-only host settings seed copied on every start
- verify: json_path(path="Layout.settings_src.semantics", equals="optional read-only host settings seed copied on every start")
- code: `workhorse/supervisor.py::Layout`
- detail: [Layout storage locations](layout-storage-locations.md)

### credentials_src
- type: `Path`
- default: `/mnt/claude-credentials.json`
- verify: json_path(path="Layout.credentials_src", equals="/mnt/claude-credentials.json")
- required: false
- verify: json_path(path="Layout.credentials_src.required", equals=false)
- semantics: optional read-only host credentials seed used only when the persistent volume has no credentials
- verify: json_path(path="Layout.credentials_src.semantics", equals="optional read-only host credentials seed used only when the persistent volume has no credentials")
- code: `workhorse/supervisor.py::Layout`
- detail: [Layout storage locations](layout-storage-locations.md)

### observer_src
- type: `Path`
- default: `/mnt/groom-src`
- verify: json_path(path="Layout.observer_src", equals="/mnt/groom-src")
- required: false
- verify: json_path(path="Layout.observer_src.required", equals=false)
- semantics: optional host bind containing the observer source
- verify: json_path(path="Layout.observer_src.semantics", equals="optional host bind containing the observer source")
- code: `workhorse/supervisor.py::Layout`
- detail: [Layout storage locations](layout-storage-locations.md)

### live_root
- type: `Path`
- default: `/opt/live`
- verify: json_path(path="Layout.live_root", equals="/opt/live")
- required: false
- verify: json_path(path="Layout.live_root.required", equals=false)
- semantics: container-local root for complete per-generation source copies
- verify: json_path(path="Layout.live_root.semantics", equals="container-local root for complete per-generation source copies")
- code: `workhorse/supervisor.py::Layout`
- detail: [Layout storage locations](layout-storage-locations.md)

### image_workhorse
- type: `Path`
- default: `/app/workhorse`
- verify: json_path(path="Layout.image_workhorse", equals="/app/workhorse")
- required: false
- verify: json_path(path="Layout.image_workhorse.required", equals=false)
- semantics: in-image workhorse checkout supplied to the observer's editable environment
- verify: json_path(path="Layout.image_workhorse.semantics", equals="in-image workhorse checkout supplied to the observer's editable environment")
- code: `workhorse/supervisor.py::Layout`
- detail: [Layout storage locations](layout-storage-locations.md)

## Methods

### claude_dir
- sig: `Layout.claude_dir -> Path`
- returns: the `.claude` directory below `claude_home`
- verify: json_path(path="return value", equals="/claude-state/.claude")
- code: `workhorse/supervisor.py::Layout.claude_dir`

### credentials
- sig: `Layout.credentials -> Path`
- returns: the credentials file below `claude_dir`
- verify: json_path(path="return value", equals="/claude-state/.claude/.credentials.json")
- code: `workhorse/supervisor.py::Layout.credentials`

### onboarding_stub
- sig: `Layout.onboarding_stub -> Path`
- returns: the Claude onboarding marker below `claude_home`
- verify: json_path(path="return value", equals="/claude-state/.claude.json")
- code: `workhorse/supervisor.py::Layout.onboarding_stub`

### boundary_params
- sig: `Layout.boundary_params -> Path`
- returns: the JSON file below `claude_home` used to pass environment-derived parameters
- verify: json_path(path="return value", equals="/claude-state/boundary-params.json")
- code: `workhorse/supervisor.py::Layout.boundary_params`

### tool_bin
- sig: `Layout.tool_bin -> Path`
- returns: the local tool binary directory below `claude_home`
- verify: json_path(path="return value", equals="/claude-state/.local/bin")
- code: `workhorse/supervisor.py::Layout.tool_bin`

### observer
- sig: `Layout.observer -> Path`
- returns: the `groom-sidecar` executable path below `tool_bin`
- verify: json_path(path="return value", equals="/claude-state/.local/bin/groom-sidecar")
- code: `workhorse/supervisor.py::Layout.observer`

### require_writable
- sig: `require_writable(paths: Sequence[Path]) -> None`
- does: rejects every path that is not a directory writable by the current uid
- raises: exits with code `13` on the first missing, non-directory, or non-writable path
- returns: `None` after all paths pass the preflight check
- verify: exit_status(code=13)
- code: `workhorse/supervisor.py::require_writable`
- tests: `workhorse/tests/test_supervisor.py::test_unwritable_mount_fails_here_with_its_own_exit_code`

### seed_claude_home
- sig: `seed_claude_home(layout: Layout, env: Mapping[str, str]) -> None`
- does: creates the Claude directory and copies host settings when the settings source is a file
- does: preserves credentials already present in the persistent volume
- does: copies host credentials into an empty volume and changes the copied file mode to `0600`
- does: uses `CLAUDE_CODE_OAUTH_TOKEN` as the authentication source when it is non-empty
- does: writes the completed-onboarding JSON stub when it does not already exist
- returns: `None` after best-effort authentication and onboarding preparation
- verify: json_path(path="$.hasCompletedOnboarding", equals=true)
- code: `workhorse/supervisor.py::seed_claude_home`
- tests: `workhorse/tests/test_supervisor.py::test_credentials_already_in_the_volume_win_over_the_host_copy`, `workhorse/tests/test_supervisor.py::test_host_credentials_are_seeded_once_into_an_empty_volume`, `workhorse/tests/test_supervisor.py::test_an_explicit_token_beats_both_files`, `workhorse/tests/test_supervisor.py::test_settings_refresh_every_start_because_they_are_config_not_a_secret`

### configure_git
- sig: `configure_git(env: Mapping[str, str]) -> None`
- does: configures global Git safe-directory handling for every path
- verify: persists(subject="global Git safe-directory handling")
- does: sets the global Git author email from `GIT_AUTHOR_EMAIL` or `agent@example.com`
- verify: persists(subject="global Git author email")
- does: sets the global Git author name from `GIT_AUTHOR_NAME` or `Agent`
- verify: persists(subject="global Git author name")
- returns: `None` after all Git configuration commands succeed
- verify: exit_status(code=0)
- code: `workhorse/supervisor.py::configure_git`

### _git
- sig: `_git(*args: str) -> None`
- does: executes `git` with the supplied arguments and requires a successful exit
- verify: exit_status(code=0)
- returns: `None` after the Git subprocess exits successfully
- verify: exit_status(code=0)
- code: `workhorse/supervisor.py::_git`

### observer_source
- sig: `observer_source(layout: Layout) -> livesource.LiveSource`
- returns: a source descriptor named `groom` mounted from `observer_src` and staged below `live_root/groom`
- verify: json_path(path="return value.name", equals="groom")
- verify: json_path(path="return value.mount", equals="/mnt/groom-src")
- verify: json_path(path="return value.root", equals="/opt/live/groom")
- returns: a descriptor whose editable dependency is the image's `image_workhorse` checkout
- verify: json_path(path="return value.with_editable[0]", equals="/app/workhorse")
- code: `workhorse/supervisor.py::observer_source`

### install_observer
- sig: `install_observer(layout: Layout) -> list[str] | None`
- does: refreshes and installs the optional observer source into `tool_bin`
- returns: the observer executable command when the staged binary is executable
- returns: `None` when no bind, refresh, install, or executable is available
- verify: absent(subject="observer command when the observer binary is missing")
- code: `workhorse/supervisor.py::install_observer`
- tests: `workhorse/tests/test_supervisor.py::test_missing_observer_binary_is_not_discovered`

### run_params
- sig: `run_params(env: Mapping[str, str]) -> dict[str, str]`
- does: selects non-empty environment entries whose names begin with `AGENT_PARAM_`
- verify: count(subject="run parameters selected from non-empty AGENT_PARAM_ entries", equals=2)
- returns: a mapping whose keys remove the prefix and are lowercased
- verify: json_path(path="$.workspace_file", equals="/mnt/ws.code-workspace")
- returns: an empty mapping for unrelated or empty environment entries
- verify: count(subject="run parameters from unrelated and empty environment entries", equals=0)
- code: `workhorse/supervisor.py::run_params`
- tests: `workhorse/tests/test_supervisor.py::test_params_come_from_a_generic_prefix_not_a_workflows_vocabulary`

### write_boundary_params
- sig: `write_boundary_params(path: Path, params: Mapping[str, str]) -> Path`
- does: writes a sorted, indented JSON object followed by a newline at `path`
- returns: the same `path` passed by the caller
- verify: json_path(path="$.docs_path", equals="/docs")
- code: `workhorse/supervisor.py::write_boundary_params`
- tests: `workhorse/tests/test_supervisor.py::test_boundary_params_land_in_a_file_so_explicit_params_still_win`

### checkout
- sig: `checkout(env: Mapping[str, str], params: Mapping[str, str]) -> None`
- does: passes the `workspace_file` from run parameters to the workspace checkout helper
- verify: created(subject="workspace checkout selected by run parameters")
- does: passes repository URL, name, branch, source mode, and worktree root from the environment
- verify: created(subject="repository checkout selected by environment arguments")
- does: defaults workspace root to `/workspace`, repository name to `repo`, branch to `main`, and source mode to `clone`
- verify: created(subject="default clone checkout at /workspace/repo on main")
- returns: `None` after requesting workspace materialization
- verify: persists(subject="materialized workspace checkout")
- code: `workhorse/supervisor.py::checkout`
- tests: `workhorse/tests/test_supervisor.py::test_checkout_reads_the_workspace_file_from_the_params_not_a_second_variable`, `workhorse/tests/test_supervisor.py::test_the_worktree_choice_crosses_as_an_argument_not_as_environment`, `workhorse/tests/test_supervisor.py::test_a_container_with_no_launcher_still_clones`

### run_command
- sig: `run_command(env: Mapping[str, str], params_file: Path, extra: Sequence[str], *, bin_dir: Path | None = None) -> list[str]`
- does: resolves the executable as `workhorse-{WORKFLOW}` beside the selected Python interpreter or supplied `bin_dir`
- does: appends runs directory, run id, config, and profile flags only when their environment values are non-empty
- does: always starts the workflow with `run` and `--params-file`, then appends operator arguments last
- raises: exits with an explanatory error when `WORKFLOW` is unset
- raises: exits with an explanatory error when the workflow console script is not executable
- returns: the complete executable argument vector
- verify: exit_status(code=1)
- code: `workhorse/supervisor.py::run_command`
- tests: `workhorse/tests/test_supervisor.py::test_the_run_command_is_the_workflows_own_console_script`, `workhorse/tests/test_supervisor.py::test_an_unset_workflow_fails_at_spawn_not_mid_run`, `workhorse/tests/test_supervisor.py::test_a_workflow_this_image_does_not_carry_fails_at_spawn`, `workhorse/tests/test_supervisor.py::test_no_run_id_flag_when_the_launcher_minted_none`, `workhorse/tests/test_supervisor.py::test_the_profile_and_its_config_file_cross_the_boundary_as_flags`, `workhorse/tests/test_supervisor.py::test_no_profile_flags_when_the_launcher_selected_none`

### Child
- sig: `Child(cmd: Sequence[str], env: Mapping[str, str] = {}, proc: Process | None = None, stopping: bool = False)`
- does: stores the configured subprocess command for a later launch
- verify: json_path(path="$.child.cmd[0]", equals="workhorse-demo")
- does: stores the environment used to launch the configured subprocess
- verify: json_path(path="$.child.env.WORKFLOW", equals="demo")
- does: records a stop request so a signal arriving during spawn is honored after a process exists
- verify: emitted(event="SIGTERM forwarded to subprocess after spawn", count=1)
- code: `workhorse/supervisor.py::Child`

### start
- sig: `Child.start() -> asyncio.subprocess.Process`
- does: asynchronously creates the configured subprocess with a copied environment
- verify: created(subject="Child.start subprocess with copied environment")
- does: forwards `SIGTERM` immediately when a stop request was recorded during spawn
- verify: emitted(event="SIGTERM forwarded to subprocess after spawn", count=1)
- returns: the created subprocess handle
- code: `workhorse/supervisor.py::Child.start`
- tests: `workhorse/tests/test_supervisor.py::test_a_signal_arriving_during_the_spawn_is_not_lost`

### signal
- sig: `Child.signal(sig: int) -> None`
- does: records that the child is stopping
- verify: json_path(path="child.stopping", equals=true)
- does: sends the signal to a live child and ignores a process that has already disappeared
- verify: emitted(event="signal delivered to live child", count=1)
- returns: `None`
- verify: json_path(path="return value", equals="None")
- code: `workhorse/supervisor.py::Child.signal`
- tests: `workhorse/tests/test_supervisor.py::test_sigterm_reaches_the_run_so_docker_stop_stays_graceful`

### supervise_observer
- sig: `supervise_observer(child: Child, *, reload_code: int = 3, on_reload: Callable[[], object] | None = None) -> None`
- does: starts and waits for the observer repeatedly while it returns the reserved reload code
- does: calls `on_reload` between observer exit and restart when a reload is requested
- does: suppresses refresh failures and keeps the previous generation available for restart
- does: stops permanently on clean exit, crash, or any non-reload exit code
- returns: `None` without propagating observer or refresh failures
- verify: count(subject="observer starts before a clean exit after two reload requests", equals=3)
- code: `workhorse/supervisor.py::supervise_observer`
- tests: `workhorse/tests/test_supervisor.py::test_only_the_reload_code_restarts_the_observer`, `workhorse/tests/test_supervisor.py::test_a_reload_restages_the_source_before_restarting`, `workhorse/tests/test_supervisor.py::test_a_refresh_that_raises_still_restarts_on_the_old_generation`, `workhorse/tests/test_supervisor.py::test_a_reload_landing_on_broken_code_fails_safe_instead_of_storming`

### supervise
- sig: `supervise(run: Child, observer: Child | None = None, *, exit_notice: Callable[[int], Sequence[str]] | None = None, on_reload: Callable[[], object] | None = None, timeout_s: float = 10.0) -> int`
- does: starts the observer task before spawning the run when an observer is present
- does: installs SIGTERM and SIGINT handlers that signal only the run child
- does: restarts the run only when its exit code is the reserved reload code and it has not been stopped
- does: sends the final run exit code to the optional exit-notice process without changing that code
- does: terminates and waits for the observer after the run ends, bounded by `timeout_s`
- returns: the final workflow exit code as the container exit code
- verify: exit_status(code=7)
- code: `workhorse/supervisor.py::supervise`
- tests: `workhorse/tests/test_supervisor.py::test_run_completes_with_no_observer_at_all`, `workhorse/tests/test_supervisor.py::test_run_exit_code_is_the_containers_with_no_observer`, `workhorse/tests/test_supervisor.py::test_observer_that_crashes_immediately_does_not_touch_the_run`, `workhorse/tests/test_supervisor.py::test_observer_that_outlives_the_run_is_torn_down`, `workhorse/tests/test_supervisor.py::test_the_run_restarts_on_the_reload_code_with_the_source_restaged`, `workhorse/tests/test_supervisor.py::test_a_run_that_fails_after_a_reload_is_not_restarted_again`, `workhorse/tests/test_supervisor.py::test_exit_notice_carries_the_code_and_never_changes_it`, `workhorse/tests/test_supervisor.py::test_a_wedged_exit_notice_does_not_hold_the_container_open`

### main
- sig: `main(argv: Sequence[str] | None = None) -> int`
- does: configures logging, registers SIGUSR1 fault dumps, and sets a group-writable umask
- verify: created(subject="SIGUSR1 fault-dump handler")
- verify: json_path(path="$.umask", equals=2)
- does: pins HOME to the persistent Claude state directory and snapshots the process environment
- verify: json_path(path="$.child.environment.HOME", equals="/claude-state")
- does: checks writable mounts, seeds Claude state, configures Git, translates parameters, checks out repositories, and writes the boundary parameter file before spawning children
- verify: json_path(path="$.preflight.call_order", equals="require_writable,seed_claude_home,configure_git,run_params,checkout,write_boundary_params")
- does: installs the optional observer and supervises the workflow with a reload refresh callback
- verify: json_path(path="$.reload.source.name", equals="groom")
- returns: the workflow's final exit code
- verify: exit_status(code=7)
- code: `workhorse/supervisor.py::main`
