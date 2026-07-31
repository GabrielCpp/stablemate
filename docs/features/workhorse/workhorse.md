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

A workflow is **resolved by name, never by path**: an installed distribution registers it
in the `workhorse.workflows` entry-point group, and that group is the only resolution
mechanism there is. The retired YAML front-end that read a `workflow.yaml` off disk is
gone, along with its loader — so a path handed to `--workflow` is refused by name rather
than misread.

- binary: `workhorse`
- code: `workhorse/workhorse/cli/__init__.py::main`

**Flows:** end-to-end journeys across these commands — [install a workflow and run
it](flows/workhorse-setup-and-run.md), [author, visualize, and run a
workflow](flows/workhorse-author-visualize-run.md), [author and run a workflow's test
suite](flows/workhorse-author-test.md), [choose the agent CLI backend and power
tier](flows/workhorse-choose-backend-and-power.md), [crash and resume in
place](flows/workhorse-crash-resume.md) (see [Flows](#flows) below).

**Two front doors, one parser.** `workhorse run <name>` and the per-workflow console
script a distribution publishes (`workhorse-<name> run [<flow>]`) reach the same `main`;
the script only binds the workflow name up front. There is deliberately no second parser —
a per-workflow script with its own argument definitions would drift from `workhorse run`
silently.

**Exit codes:** `0` when the machine reaches `Done` (and when `--dry-run` finds nothing
wrong), `1` when it fails, `130` on a `KeyboardInterrupt` — which pauses the run rather
than ending it, printing the command that resumes it. With no recognized subcommand, a
bare `workhorse [--workflow …]` is treated as `run`; a bare `--help`/`-h` is not, so it
still shows the subcommand listing.

## Commands

### run
- usage: `workhorse run <workflow> [<flow>] [--params JSON]` (the default command)
- flags:
  - `--workflow <name>` — the workflow NAME (e.g. `coder`). **Not a path**: a workflow is
    a Python package, not a file. Equivalent to the positional form.
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
    `copilot` · `aider` · `opencode`. Per run, not per state.
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
  - `<workflow>` — the workflow name to run. Required, from whichever form supplies it:
    the bare first positional when `--workflow` is omitted, or `--workflow` itself (in
    which case any positional is instead taken as `<flow>` — at most one is accepted, more
    is a hard error).
  - `<flow>` — optional: run one of the registry's named flows standalone, as a re-entry
    point, instead of the entry class.
- does:
  - run: resolve the workflow name and the optional flow from the two input shapes —
    positional-only (`workhorse run <name> [<flow>]`) or `--workflow` explicit (any one
    remaining positional becomes `<flow>`, more than one is a hard error); a missing
    workflow input under either shape prints to stderr and exits `1`
  - run: resolve the name to the installed `Registry` it names (`workhorse/workhorse/cli/resolve.py::packaged_registry` →
    `workhorse/workhorse/packaged.py::find_packaged_workflow`), which walks the
    `workhorse.workflows` entry-point group. There is no second mechanism and no fallback:
    - an unresolvable name prints `error: no workflow named '<spec>' is installed.` plus
      the sorted list of installed names (or `(none installed)`), and exits `1`
    - a name that *looks like a path* — contains `os.sep`/`os.altsep`, ends in
      `.yaml`/`.yml`, or exists on disk (`cli/resolve.py::looks_like_path`) — adds the line `Workflows are
      Python packages now, not workflow.yaml files — a path is not a workflow.` This is the
      one place the retired front-end is still named, and it is named to stop a stale
      invocation reading as a merely-unknown workflow
    - an entry point that loads to something other than a `Registry` prints what it
      actually resolved to and exits `1`
    - `Registry.directory()` is then called **eagerly**, while the operator is still being
      told about resolution, because it is what refuses a zip-imported package — deferring
      it to the first prompt render turns "this wheel is packed wrong" into a
      `TemplateNotFound` several states into a run
  - run: pin `AGENT_REPO_DIR` to the launch directory (`Path.cwd()`) when unset, so a
    node resolves the consuming repo rather than the directory the installed workflow
    package happens to sit in
  - run: `--cli` (else `AGENT_CLI`, else `claude`) sets `AGENT_CLI` for the run; select and
    eagerly validate the [AgentBackend](concepts/agent-backend.md) via
    [get_backend](concepts/get-backend.md) — an unknown name prints to stderr and exits `1`
    before any state runs, rather than failing mid-run
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
- verify: `workhorse/tests/test_workflow_resolution.py`,
  `workhorse/tests/test_resume_auto.py::test_find_latest_resumable_picks_newest_of_several_unfinished`,
  `workhorse/tests/test_resume_auto.py::test_resume_latest_still_errors_when_none`

`workhorse run coder qa --params '{"story":"ACME-1234"}'` runs the coder workflow's `qa`
flow standalone. `workhorse run coder docs --params '{"story":"ACME-1234"}'` independently
runs the same hard [documentation gate](flows/coder-documentation-gate.md) that the full
coder pipeline executes before QA and again before commit.

### test
- usage: `workhorse test <workflow_dir> [-k FILTER] [-v]`
- flags:
  - `-k, --filter <pattern>` — a pytest `-k` expression; only tests whose name matches
    `<pattern>` run. Passed through to pytest unchanged (default: run everything under
    `tests/`).
  - `-v, --verbose` — pass `-v` through to pytest for verbose per-test output.
- args:
  - `<workflow_dir>` — the directory whose `tests/` subdirectory to run; resolved to an
    absolute path before use.
- does:
  - run: resolve `<workflow_dir>` to an absolute path and check `<workflow_dir>/tests/`
    exists; print `error: no tests/ directory found in <workflow_dir>` to stderr and exit
    `1` if not
  - run: check that `pytest` is importable; if not, print an install hint (`pip install
    'workhorse-agent[test]'`) to stderr and exit `1` — pytest is an optional dependency
    (the `test` extra), not a hard runtime requirement of `workhorse`
  - run: build the pytest argv as `[<tests_dir>]`, appending `-k <pattern>` when
    `--filter` is given and `-v` when `--verbose` is given
  - run: invoke `pytest.main(argv)` in-process and exit with its return code (`0` all
    passed, `1` some failed, other pytest exit codes propagate unchanged)
- code: `workhorse/workhorse/cli/test.py::run`

A workflow's `tests/*.py` files are ordinary pytest tests. What they substitute is the
run's **node index** rather than module attributes — see [the node index is the
substitution seam](../../../workhorse/docs/AUTHORING.md#the-node-index-is-the-substitution-seam).
`workhorse test <workflow_dir>` is how an author (or CI) runs that suite without
hand-rolling the pytest invocation.

### dot
- usage: `workhorse dot <workflow> [--name ID] [-o out.dot]`
- flags:
  - `--workflow <name>` — type `str`, default: none. The workflow to render, resolved
    exactly the way `run` resolves one. Equivalent to the positional form (`workhorse dot
    <name>`); supplying both a `--workflow` and a positional is a hard error, as is
    supplying neither.
  - `--name <id>` — type `str`, default: none (falls back to the registry's own name).
    Overrides the rendered `digraph` identifier.
  - `-o, --output <path>` — type `str` (path), default: none (write to stdout). Writes the
    DOT text to `<path>` instead.
- does:
  - run: resolve the workflow spec from `--workflow` or the single positional
    (`_dot_spec`); a second positional prints `error: unexpected argument '<arg>'` and
    neither form given prints `error: dot needs a workflow name`, both to stderr, exit `1`
  - run: resolve that name to a `Registry` exactly as `run` does (`packaged_registry`)
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

### config
- usage: `workhorse config <show|get|list|set-library|set-stablemate|set-base> [args]`
- args:
  - `show [key]` — with no `key`: print every key currently loaded from the config file,
    one `key=value` line per key, in the file's own order. With `key`: print just that
    key's bare value (no `key=` prefix); if the key isn't set, print `error: '<key>' is not
    set in <config_path>` to stderr and exit `1`.
  - `get <name>` — print one config value addressed by a dot-path `<name>` into the loaded
    TOML (e.g. `power.high.claude` reaches the `[power.high.claude]` table). A `dict`/`list`
    value prints as indented (`indent=2`), key-sorted JSON; a scalar prints bare. An
    unresolved path (any segment missing, or a non-dict segment) prints nothing and exits
    `0` — silent, unlike `show`'s hard error on a missing top-level key.
  - `list` — print `# <config_path>` then the whole loaded config as indented, key-sorted
    JSON — the power→model table in full.
  - `set-library <path>` — expand `~` and resolve `<path>` to an absolute path, persist it
    under the `library_dir` top-level key, and print `library_dir=<path>`.
  - `set-stablemate <path>` — same shape, persisting `stablemate_dir`.
  - `set-base <path>` — same shape, persisting `base_dir`, for isolated/pipx installs where
    the `stablemate-library` wheel isn't importable. The path must contain `library/` or the
    command refuses it by name.
- does:
  - run: `argparse` requires exactly one subcommand as the second positional (a required
    sub-subparser); a bare `workhorse config` is a parse error (exit `2`) before
    `config.run` ever runs
  - run: the three `set-*` subcommands resolve `<path>` (`~`-expanded, absolute) and call
    [`write_config_key`](concepts/config.md#write_config_key) directly, without loading or
    echoing the rest of the config
  - run: `show`/`get`/`list` all call [`load_config`](concepts/config.md#load_config)
    first, then format it per subcommand as above
  - run: a config written by a *newer* `stablemate-core` raises `ConfigVersionError`, which
    is caught and re-raised as a clean `SystemExit` message rather than a traceback — the
    failure is deterministic and actionable, so it exits like every other config error here
- code: `workhorse/workhorse/cli/config.py::run`

Reads and writes the [shared stablemate config file](concepts/config.md) — **one** TOML
file at `~/.config/stablemate/config.toml` (platform-appropriate), holding `library_dir`,
`stablemate_dir`, `base_dir`, and a `[power.<tier>.<backend>]` model/effort table that
`self.agent(…, power=…)` resolves through. Every stablemate tool reads that same file, so
`workhorse config` and `farrier config` are two doors onto one config rather than two
configs that can disagree. The pre-unification `WORKHORSE_CONFIG` override is still
honored so an existing export keeps working.

### version
- usage: `workhorse version`
- does:
  - run: read the installed version of the `workhorse-agent` distribution via
    `importlib.metadata.version("workhorse-agent")` (the PyPI/installed package name; the
    import package and CLI command are both `workhorse`) and print it to stdout
  - run: return with no explicit `sys.exit` (exit `0`); raises uncaught if
    `workhorse-agent` isn't installed as a package, since no fallback is attempted
- code: `workhorse/workhorse/cli/version.py::run`

## Flows

End-to-end journeys across these commands:

- [Install a workflow and run it](flows/workhorse-setup-and-run.md) — get a workflow's
  distribution installed so its name resolves, then `run` it.
- [Author, visualize, and run a workflow](flows/workhorse-author-visualize-run.md) — write
  the package, sanity-check it with `--dry-run` and `dot`, then `run` it.
- [Author and run a workflow's test suite](flows/workhorse-author-test.md) — write
  `tests/*.py` that substitute the node index and drive them with `test`.
- [Choose the agent CLI backend and power tier](flows/workhorse-choose-backend-and-power.md)
  — point `run --cli` at a different harness and set its power tier in `config`.
- [Crash and resume in place](flows/workhorse-crash-resume.md) — an unattended `run` dies
  mid-machine and is re-launched with the identical command to resume from its last
  checkpoint.
