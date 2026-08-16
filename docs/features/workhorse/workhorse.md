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
    ([`CONFIG_PATH_ENV`](concepts/config.md#location)) before anything reads the file — the
    config is re-read per node and by every subprocess the run spawns, each through its own
    `config_path()`, so a flag that only reached the resolver here would name one file while
    the per-node re-read named another. A path that is not a file exits `1` rather than
    reading as an empty config; with the flag absent nothing is written back, since stamping
    the *discovered* path would suppress `load_config`'s legacy per-tool merge on a machine
    nobody asked to migrate
  - run: select the [profile](concepts/config.md#profiles) — `--profile`, else the name
    recorded in the resumed run's [`run.json`](run-artifacts.md#runjson) (which is why the
    resume dir is resolved first). A resume is a continuation, not a new decision: re-resolving
    the same nodes against the machine's global model set is a substitution nothing in the
    output would show, so the recorded name is re-applied unless this command line overrides
    it. `select_profile` narrows the loaded config; an undefined name prints
    `UnknownProfileError` (which lists the known ones) and exits `1`
  - run: `--cli` (else `AGENT_CLI`, else the config's
    [`default_cli`](concepts/config.md#resolve_default_cli) — the **profile's** first, then the
    top level's, which is why the profile is selected first — else `claude`) sets `AGENT_CLI` for
    the run — the resolved name is written back, so every later reader of that variable answers
    with the CLI actually chosen rather than re-deriving it; select and
    eagerly validate the [AgentBackend](concepts/agent-backend.md) via
    [get_backend](concepts/get-backend.md) — an unknown name prints to stderr and exits `1`
    before any state runs, rather than failing mid-run
  - run: refuse a profile that maps no model for the backend just chosen — `--profile` and
    `--cli` are independent axes, so an opencode-only profile run with `--cli claude` would
    otherwise spend the whole run on the harness's own default model with nothing to say so.
    Checked with [`profile_has_backend`](concepts/config.md#profiles), and a profile keying a
    backend name no registry knows is reported the same way a typo'd `--cli` is; both exit `1`.
    It runs under `--dry-run` too, that being the check's point
  - run: resolve `runs_dir` (`--runs-dir`, else `<cwd>/.agents/runs`)
  - run: load `--params`/`--params-file` into a starting-params dict via
    `load_params` (`workhorse/workhorse/cli/params.py::load_params`):
    - starts from `params = {}`. If `--params-file` is given, reads its path as text
      (`Path(file).read_text()`); an `OSError` (missing file, permission error, …) prints
      `error: cannot read --params-file <file>: <error>` to stderr and exits `1`
    - processes the two sources **in file-then-inline order** — the `--params-file` text
      first, then `--params` itself — skipping whichever wasn't given (`None`); each
      non-`None` source is `json.loads`-parsed, and a `json.JSONDecodeError` prints
      `error: <label> is not valid JSON: <error>` to stderr and exits `1`, where `<label>`
      is `--params-file` or `--params` matching the source
    - a source that parses to something other than a JSON object (e.g. a list or scalar)
      prints `error: <label> must be a JSON object (key→value map)` to stderr and exits `1`
    - each valid source's dict is folded into `params` via `dict.update` — so **`--params`
      wins over `--params-file`** on overlapping keys, since inline is merged second; with
      neither flag given, returns `{}`
  - run: load the `--context-file`/auto-detected manifest into a starting manifest dict
    (`load_context_manifest`)
  - run: resolve `resume_run_dir` from the mutually-exclusive resume flags — `--resume-run`
    (an absolute path, an existing relative path, or else a name under `runs_dir`;
    not-a-directory exits `1`) or `--resume-latest` (the newest unfinished run dir under
    `runs_dir`, found by `workhorse/workhorse/rundir.py::find_latest_resumable`):
    - a `runs_dir` that doesn't exist on disk yields no candidates
    - otherwise scans `runs_dir`'s immediate children; a child is a candidate only if it's
      a directory **and** holds a [checkpoint file](run-artifacts.md#checkpointjson)
      (`ArtifactWriter.CHECKPOINT_FILE`, i.e. `checkpoint.json`) — a dir with no checkpoint
      yet (never reached its first state) is never resumable
    - each candidate's [`run.json`](run-artifacts.md#runjson) is read and `json.loads`-parsed;
      a candidate whose `run.json` is missing or not valid JSON is silently dropped rather
      than failing the whole scan
    - a candidate survives only if its `run.json` `terminal` key is `null`/absent — a
      finished run is never returned by `--resume-latest`
    - among the survivors, the one whose `checkpoint.json` has the newest mtime wins; with
      no survivors, `run` prints `error: no resumable run found under <runs_dir>` to
      stderr and exits `1`
    - with neither flag given, `resume_run_dir` stays `None` and the auto-resume-in-place
      rule inside `run_pyflow` decides
  - run: hand everything to the driver as one
    `workhorse/workhorse/pyflow/run.py::RunInvocation`, and `sys.exit()` with
    `run_pyflow`'s return code. That is where the run actually happens:
    - **reference preflight** — unresolved skill/prompt references in the manifest are
      *warned* about before the first state, because an unresolved one renders as prose
      into a live agent prompt rather than failing; under `--dry-run` the same list becomes
      an exit code
    - **`--dry-run`** — the [static preflight](concepts/pyflow-state-graph.md) first (every
      prompt path resolves, every state name binds, no state is unreachable, the machine
      can terminate), then the machine is driven **for real** with nodes and agent turns
      substituted for stand-ins, so imports, `setup()` and the transitions along one path
      are exercised too. It runs in its own `dry-run` run dir, always cleared, so a smoke
      test can never overwrite the checkpoint of a live week-long run. Reaching the fail
      terminal is reported but *not* an error unless the workflow declared
      `stub_agents({…})` — undeclared, every agent reply is a blank model and any workflow
      with a reachable failure can be walked into one
    - **run identity** — an explicit `--resume-run` wins; otherwise the one stable dir for
      this `(workflow, run-id)` is resumed in place when it holds an unfinished checkpoint,
      else started fresh in that same dir
    - **the flow a checkpoint belongs to** — a resume re-enters the flow that wrote the
      checkpoint. Asking for a different `<flow>` in the same run dir is refused by name:
      the checkpoint's state and params mean nothing to another flow
    - **inputs are a model** — the workflow class's own fields are the parameter contract,
      so a missing or mistyped `--params` key is reported by name by pydantic before the
      first state
    - **interrupt** — `Ctrl-C` terminates the active agent, records the interrupt against
      the state in flight, prints the `--resume-run` command, and exits `130`
- code: `workhorse/workhorse/cli/run.py::run`
- verify: `workhorse/tests/test_run_options.py::test_profile_travels_to_the_run_and_carries_its_default_cli`,
  `workhorse/tests/test_run_options.py::test_cli_flag_still_wins_over_a_profiles_default`,
  `workhorse/tests/test_run_options.py::test_an_unknown_profile_is_refused_before_the_first_state`,
  `workhorse/tests/test_run_options.py::test_a_profile_with_nothing_for_the_chosen_backend_is_refused`,
  `workhorse/tests/test_run_options.py::test_a_flagless_resume_re_applies_the_recorded_profile`,
  `workhorse/tests/test_run_options.py::test_an_explicit_profile_overrides_the_recorded_one`
- verify: `workhorse/tests/test_console_script.py::test_every_flag_reaches_the_engine`,
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
  - run: take the `Registry` off the namespace, exactly as `run` does — *which* workflow to
    render is not a question this command asks, since it is whichever one's console script
    started the process
  - run: derive one graph per distinct flow class from the registry
    (`registry_graphs`) and render them with `to_dot` — one `subgraph cluster_*` per flow,
    **live state names only**, so an `aliases=[…]` rename never shows up as a second state.
    The graph is read off each state's own source; see [state
    graph](concepts/pyflow-state-graph.md)
  - run: if `--output` is given, write the DOT text to that path and print
    `[workhorse] wrote <path>` to stderr; otherwise write the DOT text to stdout
- code: `workhorse/workhorse/cli/dot.py::run`
- verify: `workhorse/tests/test_pyflow_graph.py::test_dot_renders_a_python_workflow_from_its_registry`

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
  - run: return with no explicit `sys.exit` (exit `0`); raises uncaught if
    `workhorse-agent` isn't installed as a package, since no fallback is attempted
- code: `workhorse/workhorse/cli/version.py::run`

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
