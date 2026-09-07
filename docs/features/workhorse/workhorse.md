---
type: cli
slug: workhorse
title: workhorse — fail-soft runner for Python agent workflows
---
# workhorse

Drives a workflow written as a **Python state machine** — states are methods on a
`Workflow` subclass, and each returns the transition to the next one — checkpointing
before every state so a run resumes exactly where it stopped, built to run unattended for
days. The walk itself is [drive](concepts/pyflow-driver.md); the shape an author writes is
the [workflow format](workflow-format.md). The agent harness a run drives is an
[AgentBackend](concepts/agent-backend.md), chosen per run via
[get_backend](concepts/get-backend.md) from the `--cli` flag.
The vendored shared runtime supplies the [clock](concepts/clock.md), [base-library
discovery](concepts/base-library-discovery.md), [base-library cache](concepts/base-library-cache.md),
and [library layout](concepts/library-layout.md) used by the engine.
Run directory selection follows [run identity](concepts/run-identity.md), durable records use the
[run record models](concepts/run-records.md), and agent visit archives use the [visit key](concepts/visit-key.md)
and [session chains](concepts/session-chains.md). Repository metadata is an [observation](concepts/repository-observation.md);
disposable machine state uses [machine scratch](concepts/machine-scratch.md), and run limits use
[per-run configuration](concepts/run-configuration.md).
The operator-facing live process channel is the [control channel](concepts/control-channel.md);
operator notes use the [run inbox](concepts/run-inbox.md), and both commands share [run target
resolution](concepts/run-target-resolution.md).
Reload decisions follow the [reload policy](concepts/reload-policy.md); gate files use the
[operator gate file](operator-gate-file.md) format and inbox persistence uses [run inbox JSONL]
(inbox-jsonl.md).
[Detached jobs](concepts/job-supervisor.md) measure long-running commands outside agent turns;
[generic worklists](concepts/worklist.md) provide workflow-agnostic selection and progress
summaries; and [packaged workflow directories](concepts/packaged-workflow.md) reject prompt
packages that cannot be read from a real filesystem directory.
CLI assembly and registry binding are specified by [CLI composition](concepts/cli-composition.md),
and the package-root public API is [workhorse package exports](concepts/package-exports.md);
workflow input merging is [parameter loading](concepts/workflow-parameter-loading.md), and the
run boundary's library roots follow [CLI library resolution](concepts/cli-library-resolution.md).
Run observation uses [OpenTelemetry instrumentation](concepts/telemetry-instrumentation.md),
[console and OpenTelemetry logging](concepts/logging-setup.md), and
[activity labels from flagged logs](concepts/activity-labels.md).
The pyflow implementation contracts are [blueprints](concepts/pyflow-blueprints.md),
[registry](concepts/pyflow-registry.md), [transitions](concepts/pyflow-transitions.md),
[engine seams](concepts/pyflow-engine.md), [name indexes](concepts/pyflow-names.md),
[errors](concepts/pyflow-errors.md), [run invocation](concepts/pyflow-run.md), and
[activity tracking](concepts/pyflow-activity.md).
The complete executable test-module inventory is [test evidence](concepts/test-evidence-inventory.md).
Engine contributors use the [local development runbook](ops/workhorse-local-development.md) for the
package-local Make drivers.

**Workhorse ships no executable.** It is a library, and the only command line it owns is
the one a *workflow* binds: a distribution declares `workhorse-<name> =
"<pkg>.workflow:main"` in `[project.scripts]`, where `main = console_script(
workflow.entry_point(Coder))`. That callable carries the `Registry` object itself, so
there is no name to resolve, no catalogue of what is installed, and no path to hand
anywhere — the retired YAML front-end that read a `workflow.yaml` off disk is gone along
with its loader, and so is the entry-point group that replaced it.

- binary: `workhorse-<name>` — one per installed workflow, e.g. `workhorse-coder`
- code: `workhorse/workhorse/cli/__init__.py::console_script`,
  `workhorse/workhorse/cli/__init__.py::main`
- detail: [live-source generation staging](concepts/live-source.md)
- detail: [CLI composition](concepts/cli-composition.md)

**Flows:** end-to-end journeys across these commands — [install a workflow and run
it](flows/workhorse-setup-and-run.md), [author, visualize, and run a
workflow](flows/workhorse-author-visualize-run.md), [author and run a workflow's test
suite](flows/workhorse-author-test.md), [choose the agent CLI backend and
power tier](flows/workhorse-choose-backend-and-power.md), [crash and resume in
place](flows/workhorse-crash-resume.md) (see [Flows](#flows) below).

**One parser, every workflow.** The subcommands below are defined once, in this package,
and every workflow's command gets all of them — which is the point of shipping the wiring
rather than letting each distribution hand-write an argument parser that would drift from
the engine it feeds. `console_script` returns the entry callable rather than calling it,
because a `[project.scripts]` target is imported and *then* called; a module-level call
would fire on import and could not be a script target at all. It rejects a bare workflow
**name** by type, since a name is no longer enough to reach a workflow.

**Exit codes:** `0` when the machine reaches `Done` (and when `--dry-run` finds nothing
wrong), `1` when it fails, `130` on a `KeyboardInterrupt` — which pauses the run rather
than ending it, printing the command that resumes it. With no recognized subcommand, a
bare `workhorse-<name> [<flow>]` is treated as `run`; a bare `--help`/`-h` is not, so it
still shows the subcommand listing.

## Commands

### run
- usage: `workhorse-<name> run [<flow>] [--params JSON]` (the default command)
- flags:
  - `--context-file <path>` — the per-repo [context manifest](context-manifest.md) (JSON)
    that library prompts render against (template values, instruction/prompt path maps,
    selected-skills set). When omitted, auto-detected as
    `$AGENT_REPO_DIR/.agents/agents-context.$AGENT_CLI.json` then
    `$AGENT_REPO_DIR/.agents/agents-context.json`; if neither exists the run proceeds with
    an empty manifest. If given explicitly, the path must exist — a typo is a hard error.
  - `--params <json>` / `--params-file <path>` — set the workflow's inputs (its class
    attributes) on a *fresh start*; ignored on resume, which reads them back off the
    checkpoint. Merged when both are given (`--params-file` first, then `--params` — inline
    wins on key overlap); each source must decode to a JSON object or the run errors out.
  - `--cli <name>` — pick the agent harness for the run: selects an
    [AgentBackend](concepts/agent-backend.md) implementation via
    [get_backend](concepts/get-backend.md); `<name>` ∈ `claude` (default) · `codex` ·
    `copilot` · `cline` · `opencode`. Per run, not per state.
  - `--profile <name>` — resolve this run's models from the config's
    [`[profiles.<name>]`](concepts/config.md#profiles) tables instead of its top-level ones. A
    profile **replaces** them — nothing outside it is inherited — and is an axis independent of
    `--cli`, which chooses whose entries in it apply. Per run, not per state; recorded in
    [`run.json`](run-artifacts.md#runjson) so a flagless `--resume-run` re-applies it.
  - `--config <path>` — read the [shared config file](concepts/config.md) from this path instead
    of the discovered one. Means what `$STABLEMATE_CONFIG` means — *this* file, entirely, with no
    merge against the machine's — so it must itself carry `library_dir`/`base_dir`/`stablemate_dir`
    if the run needs them. Overrides `$STABLEMATE_CONFIG`, which overrides `$WORKHORSE_CONFIG`.
  - `--runs-dir <dir>` — where run artifacts are written (default `<cwd>/.agents/runs`).
  - `--run-id <id>` — name the stable run dir (`<workflow>-<id>`). Default: a digest of
    `--params`, so distinct params get distinct dirs and never collide on one run; with no
    params, `default`.
  - `--dry-run` — check the workflow without doing its work, then exit (`0` clean, `1` on
    the first problem). The `--dry-run` bullet below says what it actually checks.
  - `--resume-run <path-or-id>` / `--resume-latest` / `--no-cache` — mutually exclusive
    with each other. `--resume-run`/`--resume-latest` resume a checkpointed run instead of
    the default auto-resume-in-place. `--no-cache` deletes the stable run dir before
    starting, forcing a clean run from scratch.
- args:
  - `<flow>` — optional: run one of the registry's named flows standalone, as a re-entry
    point, instead of the entry class. It is the command's **only** positional — which
    workflow runs is settled by which console script started the process.
- does:
  - run: take the `Registry` off the parsed namespace, where the console script put it
    (`workhorse/workhorse/cli/__init__.py::main` sets `args.registry`). Nothing is looked
    up: passing the registry is also what lets the command work with the package merely on
    `sys.path`, uninstalled
  - run: call `Registry.directory()` **eagerly**, before any state, because it is what
    refuses a zip-imported or namespace package — deferring it to the first prompt render
    turns "this wheel is packed wrong" into a `TemplateNotFound` several states into a
    run. A `PackagedWorkflowError` prints `error: <exc>` to stderr and exits `1`
  - run: pin `AGENT_REPO_DIR` to the launch directory (`Path.cwd()`) when unset, so a
    node resolves the consuming repo rather than the directory the installed workflow
    package happens to sit in
  - run: `--config`, if given, is written back to `$STABLEMATE_CONFIG`
    ([`CONFIG_PATH_ENV`](concepts/config.md#location)) before anything reads the file
  - verify: exit_status(code=0)
  - run: the config is re-read per node and by every subprocess the run spawns, each through
    its own `config_path()`, so the selected file remains consistent throughout the run
  - verify: exit_status(code=0)
  - run: a `--config` path that is not a file exits `1` rather than reading as an empty config
  - verify: exit_status(code=1)
  - run: without `--config`, `$STABLEMATE_CONFIG` is not written, so `load_config` retains its
    legacy per-tool merge instead of treating a discovered path as explicit
  - verify: exit_status(code=0)
  - run: select the [profile](concepts/config.md#profiles) from `--profile`, or from the resumed
    run's [`run.json`](run-artifacts.md#runjson) after resolving its directory
  - verify: exit_status(code=0)
  - run: a resumed run re-applies its recorded profile unless `--profile` overrides it, so its
    nodes do not silently resolve against the machine's global model set
  - verify: exit_status(code=0)
  - run: an undefined profile prints `UnknownProfileError`, including the known names, and exits
    `1`
  - verify: exit_status(code=1)
  - run: select the CLI from `--cli`, `AGENT_CLI`, the profile's
    [`default_cli`](concepts/config.md#resolve_default_cli), the top-level default, or `claude`
  - verify: exit_status(code=0)
  - run: write the resolved CLI name to `AGENT_CLI` so later readers use the selected backend
    rather than re-deriving it
  - verify: exit_status(code=0)
  - run: eagerly validate the selected [AgentBackend](concepts/agent-backend.md) through
    [get_backend](concepts/get-backend.md) before any state runs
  - verify: exit_status(code=0)
  - run: an unknown CLI backend prints an error to stderr and exits `1` before any state runs
  - verify: exit_status(code=1)
  - run: refuse a profile that has no model for the selected backend, preventing a harness
    default model from being used silently
  - verify: exit_status(code=1)
  - run: report a profile keyed by an unknown backend name as the same error class as an unknown
    `--cli` value
  - verify: exit_status(code=1)
  - run: validate the selected profile and backend under `--dry-run` as well as a live run
  - verify: exit_status(code=1)
  - run: resolve `runs_dir` (`--runs-dir`, else `<cwd>/.agents/runs`)
  - run: load `--params`/`--params-file` into a starting-params dict via
    `load_params` (`workhorse/workhorse/cli/params.py::load_params`):
      - starts from `params = {}`. If `--params-file` is given, reads its path as text
        (`Path(file).read_text()`)
      - an `OSError` while reading `--params-file` (missing file, permission error, …) prints
        `error: cannot read --params-file <file>: <error>` to stderr and exits `1`
      - processes the two sources **in file-then-inline order** — the `--params-file` text
        first, then `--params` itself — skipping whichever wasn't given (`None`)
      - parses each non-`None` source with `json.loads`. A `json.JSONDecodeError` prints
        `error: <label> is not valid JSON: <error>` to stderr and exits `1`, where `<label>`
        is `--params-file` or `--params` matching the source
    - a source that parses to something other than a JSON object (e.g. a list or scalar)
      prints `error: <label> must be a JSON object (key→value map)` to stderr and exits `1`
      - folds each valid source dict into `params` with `dict.update`, so **`--params` wins over
        `--params-file`** on overlapping keys because inline is merged second
      - returns `{}` when neither parameter source is given
  - run: load the `--context-file`/auto-detected manifest into a starting manifest dict
    (`load_context_manifest`)
  - run: resolve `resume_run_dir` from the mutually-exclusive resume flags — `--resume-run`
    accepts an absolute path, an existing relative path, or a name under `runs_dir`
  - run: a `--resume-run` target that is not a directory exits `1`
  - run: `--resume-latest` resolves the newest unfinished run directory under `runs_dir` through
    `workhorse/workhorse/rundir.py::find_latest_resumable`:
    - a `runs_dir` that doesn't exist on disk yields no candidates
    - otherwise scans `runs_dir`'s immediate children
    - a child is a candidate only when it is a directory with a
      [checkpoint file](run-artifacts.md#checkpointjson) (`ArtifactWriter.CHECKPOINT_FILE`, or
      `checkpoint.json`)
    - a directory that has not reached its first state is never resumable
    - reads and parses each candidate's [`run.json`](run-artifacts.md#runjson)
    - silently drops a candidate whose `run.json` is missing or invalid JSON instead of failing
      the whole scan
    - a candidate survives only if its `run.json` `terminal` key is `null`/absent — a
      finished run is never returned by `--resume-latest`
    - chooses the surviving candidate whose `checkpoint.json` has the newest mtime
    - with no surviving candidate, prints `error: no resumable run found under <runs_dir>` to
      stderr and exits `1`
    - with neither flag given, `resume_run_dir` stays `None` and the auto-resume-in-place
      rule inside `run_pyflow` decides
  - run: hand everything to the driver as one
    `workhorse/workhorse/pyflow/run.py::RunInvocation`, and `sys.exit()` with
    `run_pyflow`'s return code. That is where the run actually happens:
    - **reference preflight** — warns about unresolved skill or prompt references in the manifest
      before the first state, because an unresolved reference renders as prose in a live agent
      prompt instead of failing
    - under `--dry-run`, treats the same unresolved-reference list as an exit code
    - **`--dry-run`** — the [static preflight](concepts/pyflow-state-graph.md) first (every
      prompt path resolves, every state name binds, no state is unreachable, the machine
      can terminate), then the machine is driven **for real** with nodes and agent turns
      substituted for stand-ins, so imports, `setup()` and the transitions along one path
      are exercised too. It runs in its own `dry-run` run dir, always cleared, so a smoke
      test can never overwrite the checkpoint of a live week-long run. Reaching the fail
      terminal is reported but *not* an error unless the workflow declared
      `stub_agents({…})` — undeclared, every agent reply is a blank model and any workflow
      with a reachable failure can be walked into one
    - **run identity** — an explicit `--resume-run` wins
    - otherwise, resumes the stable directory for this `(workflow, run-id)` when it holds an
      unfinished checkpoint
    - otherwise, starts fresh in that same stable directory
    - **the flow a checkpoint belongs to** — a resume re-enters the flow that wrote the
      checkpoint. Asking for a different `<flow>` in the same run dir is refused by name:
      the checkpoint's state and params mean nothing to another flow
    - **inputs are a model** — the workflow class's own fields are the parameter contract,
      so a missing or mistyped `--params` key is reported by name by pydantic before the
      first state
    - **interrupt** — `Ctrl-C` terminates the active agent, records the interrupt against
      the state in flight, prints the `--resume-run` command, and exits `130`
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/run.py::add_arguments`
- code: `workhorse/workhorse/cli/run.py::run`
- code: `workhorse/workhorse/cli/run.py::invocation`
- detail: [workflow parameter loading](concepts/workflow-parameter-loading.md)
- detail: [CLI library-directory resolution](concepts/cli-library-resolution.md)
- tests: `workhorse/tests/test_run_options.py::test_profile_travels_to_the_run_and_carries_its_default_cli`,
  `workhorse/tests/test_run_options.py::test_cli_flag_still_wins_over_a_profiles_default`,
  `workhorse/tests/test_run_options.py::test_an_unknown_profile_is_refused_before_the_first_state`,
  `workhorse/tests/test_run_options.py::test_a_profile_with_nothing_for_the_chosen_backend_is_refused`,
  `workhorse/tests/test_run_options.py::test_a_flagless_resume_re_applies_the_recorded_profile`,
  `workhorse/tests/test_run_options.py::test_an_explicit_profile_overrides_the_recorded_one`
- tests: `workhorse/tests/test_console_script.py::test_every_flag_reaches_the_engine`,
  `workhorse/tests/test_console_script.py::test_the_cli_reports_the_zip_failure_and_exits`,
  `workhorse/tests/test_resume_auto.py::test_find_latest_resumable_picks_newest_of_several_unfinished`,
  `workhorse/tests/test_resume_auto.py::test_resume_latest_still_errors_when_none`

`workhorse-coder run qa --params '{"story":"ACME-1234"}'` runs the coder workflow's `qa`
flow standalone. `workhorse-coder run docs --params '{"story":"ACME-1234"}'` independently
runs the same hard [documentation gate](flows/coder-documentation-gate.md) that the full
coder pipeline executes before QA and again before commit.

### dot
- usage: `workhorse-<name> dot [--name ID] [-o out.dot]`
- flags:
  - `--name <id>` — type `str`, default: none (falls back to the registry's own name).
    Overrides the rendered `digraph` identifier.
  - `-o, --output <path>` — type `str` (path), default: none (write to stdout). Writes the
    DOT text to `<path>` instead.
- does:
  - run: take the `Registry` off the namespace, exactly as `run` does
  - verify: count(subject="flow graphs rendered from a namespace carrying a one-flow registry", equals=1)
  - run: render whichever workflow's console script started the process, without accepting
    a workflow selection argument
  - verify: omits(subject="dot command usage after the dot token", matches="(?:<workflow>|--workflow)")
  - run: derive one graph per distinct flow class from the registry (`registry_graphs`)
  - verify: count(subject="graphs for a registry with two distinct flow classes", equals=2)
  - run: render each flow graph with `to_dot` as one `subgraph cluster_*`
  - verify: count(subject="subgraph clusters in DOT output for a two-flow registry", equals=3)
  - run: read each flow graph off its states' own source
  - verify: omits(subject="DOT output for a workflow state renamed with aliases=[…]", text="qa")
  - run: render live state names only, so an `aliases=[…]` rename never shows up as a second
    state
  - verify: omits(subject="DOT output", text="qa")
  - run: if `--output` is given, write the DOT text to that path
  - run: if `--output` is given, print `[workhorse] wrote <path>` to stderr
  - run: if `--output` is not given, write the DOT text to stdout
The state-source rule is described in the [state graph](concepts/pyflow-state-graph.md).
- verify: exit_status(code=0)
- code: `workhorse/workhorse/cli/dot.py::run`
- code: `workhorse/workhorse/cli/dot.py::add_arguments`
- tests: `workhorse/tests/test_pyflow_graph.py::test_dot_renders_a_python_workflow_from_its_registry`

There are no `--pin`/`--leaf` flags. They collapsed a *declared* branch node into one
edge, and a Python workflow's branches are ordinary `if` statements in a state body —
there is nothing declared to pin.

### version
- usage: `workhorse-<name> version`
- does:
  - run: read the installed version of the `workhorse-agent` distribution via
    `importlib.metadata.version("workhorse-agent")` (the PyPI/installed package name; the
    import package is `workhorse`) and print it to stdout. It reports the **engine's**
    version, not the workflow distribution's — every workflow's command answers the same
  - run: return with no explicit `sys.exit` (exit `0`)
  - run: raise uncaught if `workhorse-agent` isn't installed as a package, since no fallback is
    attempted
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/version.py::run`
- code: `workhorse/workhorse/cli/version.py::add_arguments`

### control
- usage: `workhorse-<name> control {reload,status,questions,answer,switch-cli,switch-profile} [NAME] [options]`
- flags:
  - `--run ID|DIR` — select a run by run id, run-directory name, or path; default: the newest
    unfinished run under `--runs-dir`
  - `--runs-dir DIR` — run-directory root; default: `<cwd>/.agents/runs`
  - `--gate PATH` — for `answer` only, target this absolute gate path; default: the gate the run
    is currently waiting on
  - `--text TXT` — for `answer` only, use this answer body; default: read all non-terminal stdin
  - `--core` — for `reload` and `switch-cli`, also replace workhorse itself
  - `--at-boundary` — for `reload` and `switch-cli`, defer re-entry until the current streaming
    turn reaches a state boundary
- args:
  - `NAME` — for `switch-cli`, the agent CLI to use after re-entry; for `switch-profile`, the
    profile used from the next turn; absent for every other action
- does:
  - parse exactly one of `reload`, `status`, `questions`, `answer`, `switch-cli`, or
    `switch-profile`
  - reject a target name on an action other than `switch-cli` or `switch-profile`
  - reject either switch action when its target name is absent
  - reject `--gate` or `--text` on an action other than `answer`
  - reject `answer` when no `--text` is supplied and stdin is a terminal
  - resolve the target locally, then ask groom for a named run that is not local
  - send one request to the selected run and print action-specific evidence
- errors: print the resolution or control-socket error to stderr when no target or listener can receive the request
- exits: return `1` for invalid action arguments, target resolution failure, or socket delivery failure
- exits: return `0` after a request is delivered, except `answer` and a refused `switch-profile`, which return `1` when the run does not confirm the action
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/control.py::add_arguments`
- code: `workhorse/workhorse/cli/control.py::run`
- detail: [control channel](concepts/control-channel.md)
- tests: `workhorse/tests/test_control_command.py::_control`

### inbox
- usage: `workhorse-<name> inbox {read,reply} [ID] [TEXT] [options]`
- flags:
  - `--all` — for `read`, include replied messages; default: outstanding messages only
  - `--run ID|DIR` — select a run by id, directory name, or path; default: newest unfinished run
  - `--runs-dir DIR` — run directory root; default: `<cwd>/.agents/runs`
- args:
  - `action` — required action, either `read` or `reply`
  - `message_id` — optional message id, used by `reply`
  - `text` — optional reply text, used by `reply`
- does:
  - select exactly one `read` or `reply` action
  - dispatch the selected action against the resolved run inbox
- errors: refuse an action other than `read` or `reply`
- errors: report target-resolution failures before accessing an inbox
- exits: return `2` when argparse rejects the action or another command-line shape
- exits: return `1` when reply validation or target resolution fails
- exits: return `0` after the selected action completes
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- verify: exit_status(code=2)
- code: `workhorse/workhorse/cli/inbox.py::add_arguments`
- code: `workhorse/workhorse/cli/inbox.py::run`
- detail: [run inbox](concepts/run-inbox.md)
- tests: `workhorse/tests/test_inbox_command.py::_inbox`

### reload
- usage: `workhorse-<name> control reload [--run ID|DIR] [--runs-dir DIR] [--core] [--at-boundary]`
- parent: [control](#control)
- flags:
  - `--run ID|DIR` — select a run by id, directory name, or path; default: newest unfinished run
  - `--runs-dir DIR` — run directory root; default: `<cwd>/.agents/runs`
  - `--core` — reload workhorse and the workflow package
  - `--at-boundary` — finish the current streaming turn before re-entry
- does:
  - send `action=reload` to the selected live run, preserving `--core` and `--at-boundary`
- does:
  - report the socket reply, process liveness, and last checkpoint position without waiting for re-entry
- errors: report a missing target or a run with no listening control socket
- exits: return `1` when target resolution or socket delivery fails
- exits: return `0` after the request is delivered
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/control.py::run`
- detail: [control channel](concepts/control-channel.md)
- tests: `workhorse/tests/test_control_command.py::test_reload_says_it_on_the_socket_the_run_is_listening_on`, `workhorse/tests/test_control_command.py::test_a_run_that_does_not_exist_is_an_error_not_a_new_directory`

### status
- usage: `workhorse-<name> control status [--run ID|DIR] [--runs-dir DIR]`
- parent: [control](#control)
- flags: `--run ID|DIR` and `--runs-dir DIR` — select the run as for [reload](#reload)
- does:
  - send a status query that the run answers without ending its current wait
- does:
  - print the run's self-reported fields when the socket replies
- does:
  - print process liveness and checkpoint position when the run does not answer before the control timeout
- errors: report a missing target or a run with no listening control socket
- exits: return `1` when target resolution or socket delivery fails
- exits: return `0` for an answered or timed-out status query
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/control.py::run`
- detail: [control channel](concepts/control-channel.md)
- tests: `workhorse/tests/test_control_command.py::test_status_is_answered_by_the_run_and_not_by_the_run_dir`, `workhorse/tests/test_control_command.py::test_a_run_that_never_answered_reports_from_disk_and_says_which_it_is`

### questions
- usage: `workhorse-<name> control questions [--run ID|DIR] [--runs-dir DIR]`
- parent: [control](#control)
- flags: `--run ID|DIR` and `--runs-dir DIR` — select the run as for [reload](#reload)
- does:
  - send a questions query that the run answers without ending its current wait
- does:
  - print each pending gate's path, kind, timestamp, and question text
- does:
  - report that the run is not blocked when the live reply contains an empty question list
- does:
  - report a timeout separately when the run does not answer
- errors: report a missing target or a run with no listening control socket
- exits: return `1` when target resolution or socket delivery fails
- exits: return `0` for an answered or timed-out question query
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/control.py::run`
- detail: [control channel](concepts/control-channel.md)
- tests: `workhorse/tests/test_control_command.py::test_questions_prints_the_gate_the_run_is_parked_on`, `workhorse/tests/test_control_command.py::test_questions_says_when_the_run_is_not_blocked`

### answer
- usage: `workhorse-<name> control answer [--run ID|DIR] [--runs-dir DIR] [--gate PATH] [--text TXT]`
- parent: [control](#control)
- flags:
  - `--run ID|DIR` and `--runs-dir DIR` — select the run as for [reload](#reload)
  - `--gate PATH` — absolute gate path; default: the gate currently awaited by the run
  - `--text TXT` — answer text; default: read all text from non-terminal stdin
- does:
  - send `action=answer` with the selected gate path and answer body over the control channel
- does:
  - read all stdin text when `--text` is omitted and stdin is non-terminal
- does:
  - report the gate path only after the run confirms that it wrote the answer
- errors: refuse an answer with no text source
- errors: report the run's refusal when the gate is unavailable or already answered
- errors: report missing acknowledgement as an error because no gate write was confirmed
- exits: return `1` when validation, target resolution, delivery, or run confirmation fails
- exits: return `0` after the run confirms the answer was written
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/control.py::run`
- detail: [control channel](concepts/control-channel.md)
- tests: `workhorse/tests/test_control_command.py::test_an_answer_carries_the_gate_and_the_text_and_reports_the_landing`, `workhorse/tests/test_control_command.py::test_a_refused_answer_exits_nonzero`

### switch-cli
- usage: `workhorse-<name> control switch-cli CLI [--run ID|DIR] [--runs-dir DIR]`
- parent: [control](#control)
- flags: `--run ID|DIR` and `--runs-dir DIR` — select the run as for [reload](#reload)
- args: `CLI` — required agent CLI name to use after re-entry
- does:
  - encode `switch-cli CLI` as `action=reload`, `core=true`, and `cli=CLI`
- errors: refuse a missing CLI name or a name supplied to a non-switch action
- exits: return `1` when validation, target resolution, or socket delivery fails
- exits: return `0` after the switch request is delivered
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/control.py::run`
- detail: [control channel](concepts/control-channel.md)
- tests: `workhorse/tests/test_control_command.py::test_a_cli_switch_travels_as_a_core_reload_naming_the_cli`, `workhorse/tests/test_control_command.py::test_a_switch_with_no_cli_and_a_reload_with_one_are_both_refused`

### switch-profile
- usage: `workhorse-<name> control switch-profile PROFILE [--run ID|DIR] [--runs-dir DIR]`
- parent: [control](#control)
- flags: `--run ID|DIR` and `--runs-dir DIR` — select the run as for [reload](#reload)
- args: `PROFILE` — required profile name for subsequent model resolution
- does:
  - send `action=switch-profile` with the named profile and without a core reload
- does:
  - print that the profile applies from the next turn rather than waiting for the switch to complete
- errors: refuse a missing profile name or report the run's profile-resolution refusal
- exits: return `1` when validation, target resolution, socket delivery, or profile resolution fails
- exits: return `0` after the run accepts the profile request
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/control.py::run`
- detail: [control channel](concepts/control-channel.md)
- tests: `workhorse/tests/test_control_command.py::test_a_profile_switch_is_its_own_verb_carrying_the_name`, `workhorse/tests/test_control_command.py::test_a_refused_profile_switch_exits_nonzero`

### read
- usage: `workhorse-<name> inbox read [--all] [--run ID|DIR] [--runs-dir DIR]`
- parent: [inbox](#inbox)
- flags:
  - `--all` — include replied messages; default: outstanding messages only
  - `--run ID|DIR` and `--runs-dir DIR` — select the run using shared target resolution
- args: no message id or text is consumed by this action
- does:
  - print each selected message id, timestamp, reply state, and body
- does:
  - print a no-messages notice when the selected set is empty
- does:
  - leave every message in the run inbox unchanged
- errors: report a target-resolution failure before reading the inbox
- exits: return `0` after reading the inbox
- exits: return `1` when target resolution fails
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- verify: unchanged(subject="run inbox")
- code: `workhorse/workhorse/cli/inbox.py::run`
- detail: [run inbox](concepts/run-inbox.md)
- tests: `workhorse/tests/test_inbox_command.py::test_read_prints_outstanding_messages_by_default`, `workhorse/tests/test_inbox_command.py::test_read_all_includes_replied_messages`

### reply
- usage: `workhorse-<name> inbox reply ID TEXT [--run ID|DIR] [--runs-dir DIR]`
- parent: [inbox](#inbox)
- flags: `--run ID|DIR` and `--runs-dir DIR` — select the run using shared target resolution
- args:
  - `ID` — required id of the message to answer
  - `TEXT` — required reply text
- does:
  - attach the reply text and current UTC timestamp to the message with the selected id
- does:
  - atomically persist the updated inbox and report the replied message id
- errors: refuse a missing id or text
- errors: report a missing message id
- errors: report a target-resolution failure before modifying the inbox
- exits: return `1` when validation, target resolution, or message lookup fails
- exits: return `0` after the reply is persisted
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/inbox.py::run`
- detail: [run inbox](concepts/run-inbox.md)
- tests: `workhorse/tests/test_inbox_command.py::test_reply_persists_and_is_read_back_as_answered`, `workhorse/tests/test_inbox_command.py::test_reply_to_a_missing_id_is_an_error`

## Flows

End-to-end journeys across these commands:

- [Install a workflow and run it](flows/workhorse-setup-and-run.md) — get a workflow's
  distribution installed so its command is on `PATH`, then `run` it.
- [Author, visualize, and run a workflow](flows/workhorse-author-visualize-run.md) — write
  the package, sanity-check it with `--dry-run` and `dot`, then `run` it.
- [Author and run a workflow's test suite](flows/workhorse-author-test.md) — write
  `tests/*.py` that substitute the node index and drive them with plain `pytest`; the
  declared stand-ins are shared with `run --dry-run`.
- [Choose the agent CLI backend and power tier](flows/workhorse-choose-backend-and-power.md)
  — point `run --cli` at a different harness, set its power tier in the [shared config
  file](concepts/config.md), and select a whole named set of models for one run with
  `--profile`.
- [Crash and resume in place](flows/workhorse-crash-resume.md) — an unattended `run` dies
  mid-machine and is re-launched with the identical command to resume from its last
  checkpoint.

## Invocations

### control
- on: [control](#control)
- trigger: a human invokes the workflow console script with the `control` token
- does:
  - parse one live-run action and its action-specific arguments
- does:
  - resolve the target run before sending any request
- does:
  - construct and send the corresponding [control channel](concepts/control-channel.md) request
- does:
  - report the reply and on-disk liveness/checkpoint evidence for actions that do not have a dedicated report
- auth: the operator who can access the run directory and its control socket
- verify: exit_status(code=0)
- code: `workhorse/workhorse/cli/control.py::run`
- detail: [control channel](concepts/control-channel.md)
- tests: `workhorse/tests/test_control_command.py::_control`

### inbox
- on: [inbox](#inbox)
- trigger: a human invokes the workflow console script with the `inbox` token
- does:
  - resolve the target run before reading or updating its inbox file
- does:
  - dispatch `read` to outstanding or all-message retrieval according to `--all`
- does:
  - dispatch `reply` to update the message selected by `ID` with `TEXT` and a UTC timestamp
- errors: report invalid reply arguments or a missing message id on stderr and exit non-zero
- errors: report a target-resolution failure on stderr and exit non-zero
- auth: the operator who can access the run directory and its inbox file
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/inbox.py::run`
- detail: [run inbox](concepts/run-inbox.md)
- tests: `workhorse/tests/test_inbox_command.py::_inbox`

### reload
- on: [reload](#reload)
- trigger: the operator invokes `control reload`
- does:
  - send `action=reload`, preserving `--core` and `--at-boundary`
- does:
  - print the run's reply, liveness, and checkpoint position without waiting for the reload to finish
- auth: the operator who can connect to the run's 0600 control socket
- verify: exit_status(code=0)
- code: `workhorse/workhorse/cli/control.py::run`
- detail: [control channel](concepts/control-channel.md)
- tests: `workhorse/tests/test_control_command.py::test_the_flags_that_were_typed_are_the_flags_that_are_sent`

### status
- on: [status](#status)
- trigger: the operator invokes `control status`
- does:
  - obtain the run's status reply without ending its current wait
- does:
  - fall back to on-disk liveness and checkpoint evidence when the reply is empty
- auth: the operator who can connect to the run's control socket
- verify: exit_status(code=0)
- code: `workhorse/workhorse/cli/control.py::run`
- detail: [control channel](concepts/control-channel.md)
- tests: `workhorse/tests/test_control_command.py::test_status_is_answered_by_the_run_and_not_by_the_run_dir`

### questions
- on: [questions](#questions)
- trigger: the operator invokes `control questions`
- does:
  - obtain the run's current operator-gate list without ending its current wait
- does:
  - print each gate entry or state that no operator gate is pending
- auth: the operator who can connect to the run's control socket
- verify: exit_status(code=0)
- code: `workhorse/workhorse/cli/control.py::run`
- detail: [control channel](concepts/control-channel.md)
- tests: `workhorse/tests/test_control_command.py::test_questions_prints_the_gate_the_run_is_parked_on`

### answer
- on: [answer](#answer)
- trigger: the operator invokes `control answer`
- does:
  - send the selected gate path and answer body to the live run
- does:
  - report success only after the run confirms that it wrote the answer into the gate file
- auth: the operator authorized to answer the run's gate
- verify: exit_status(code=0)
- code: `workhorse/workhorse/cli/control.py::run`
- detail: [control channel](concepts/control-channel.md)
- tests: `workhorse/tests/test_control_command.py::test_an_answer_carries_the_gate_and_the_text_and_reports_the_landing`

### switch-cli
- on: [switch-cli](#switch-cli)
- trigger: the operator invokes `control switch-cli CLI`
- does:
  - send a core reload request carrying the named CLI
- does:
  - print that the run will re-enter on the named CLI
- auth: the operator who can connect to the run's control socket
- verify: exit_status(code=0)
- code: `workhorse/workhorse/cli/control.py::run`
- detail: [control channel](concepts/control-channel.md)
- tests: `workhorse/tests/test_control_command.py::test_a_cli_switch_travels_as_a_core_reload_naming_the_cli`

### switch-profile
- on: [switch-profile](#switch-profile)
- trigger: the operator invokes `control switch-profile PROFILE`
- does:
  - send the named profile for resolution on the next turn without a reload
- does:
  - return non-zero when the live run rejects the profile
- auth: the operator who can connect to the run's control socket
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/control.py::run`
- detail: [control channel](concepts/control-channel.md)
- tests: `workhorse/tests/test_control_command.py::test_a_profile_switch_is_its_own_verb_carrying_the_name`, `workhorse/tests/test_control_command.py::test_a_refused_profile_switch_exits_nonzero`

### read
- on: [read](#read)
- trigger: the operator invokes `inbox read`
- does:
  - read outstanding messages by default or all messages with `--all`
- does:
  - print message bodies and any stored replies without modifying the inbox
- errors: report a target-resolution failure before reading the inbox
- auth: the operator who can read the run directory
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/inbox.py::run`
- detail: [run inbox](concepts/run-inbox.md)
- tests: `workhorse/tests/test_inbox_command.py::test_read_prints_outstanding_messages_by_default`

### reply
- on: [reply](#reply)
- trigger: the operator invokes `inbox reply ID TEXT`
- does:
  - rewrite the identified inbox entry with the reply text and UTC reply timestamp
- does:
  - report the identified message after persistence
- errors: report missing reply arguments or a missing message id on stderr
- errors: report a target-resolution failure before modifying the inbox
- auth: the operator who can write the run directory
- verify: exit_status(code=0)
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/inbox.py::run`
- detail: [run inbox](concepts/run-inbox.md)
- tests: `workhorse/tests/test_inbox_command.py::test_reply_persists_and_is_read_back_as_answered`
