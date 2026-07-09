---
type: cli
slug: workhorse
title: workhorse — fail-soft runner for YAML agent workflows
---
# workhorse

Walks a directed graph of nodes defined by a [workflow](concepts/workflow.md) — on disk the
[workflow file format](workflow-format.md) — checkpointing after each node so a run resumes
exactly where it stopped, built to run unattended for days. The agent harness that drives a
run is an [AgentBackend](concepts/agent-backend.md), chosen per run via
[get_backend](concepts/get-backend.md) from the `--cli` flag. A workflow's own `tests/` suite is
run via `workhorse test` and authored against [`workhorse.testing`](concepts/testing.md).

- binary: `workhorse`
- code: `workhorse/workhorse/main.py::main`

**Flows:** end-to-end journeys across these commands — [set up the prompt library and run a
workflow](flows/workhorse-setup-and-run.md), [author, visualize, and run a
workflow](flows/workhorse-author-visualize-run.md), [author and run a workflow's test
suite](flows/workhorse-author-test.md), [choose the agent CLI backend and power
tier](flows/workhorse-choose-backend-and-power.md), [crash and resume in
place](flows/workhorse-crash-resume.md) (see [Flows](#flows) below).

**Exit codes:** a run exits `0` when it reaches a `terminal` node, `1` when it reaches a `fail`
node or dies unrecovered (see [workflow](concepts/workflow.md) execution); with no recognized
subcommand, a bare `workhorse [--workflow …]` is treated as `run`.

## Commands

### run
- usage: `workhorse run <workflow> [<flow>] [--params JSON]` (the default command)
- flags:
  - `--workflow <path>` — run a `workflow.yaml` by path instead of the positional name; equivalent to the positional form.
  - `--context-file <path>` — the per-repo [context manifest](context-manifest.md) (JSON) that
    library prompts render against (template values, instruction/prompt path maps, selected-skills
    set). When omitted, auto-detected as `$AGENT_REPO_DIR/.agents/agents-context.$AGENT_CLI.json`
    then `$AGENT_REPO_DIR/.agents/agents-context.json`; if neither exists the run proceeds with an
    empty manifest. If given explicitly, the path must exist — a typo is a hard error.
  - `--params <json>` / `--params-file <path>` — override the workflow's [vars](workflow-format.md#vars) on a *fresh start*; ignored on resume. Merged when both are given (`--params-file` first, then `--params` — inline wins on key overlap); each source must decode to a JSON object or the run errors out.
  - `--cli <name>` — pick the agent harness for the run: selects an [AgentBackend](concepts/agent-backend.md) implementation via [get_backend](concepts/get-backend.md); `<name>` ∈ `claude` (default) · `codex` · `copilot` · `aider` · `opencode`.
  - `--runs-dir <dir>` — where run artifacts are written (default `<workflow-dir>/runs`).
  - `--run-id <id>` — name the stable run dir (`<workflow>-<id>`, default `default`); distinct ids keep parallel runs side by side.
  - `--resume-run <path-or-id>` / `--resume-latest` / `--no-cache` — mutually exclusive with each
    other. `--resume-run`/`--resume-latest` resume a checkpointed run instead of the default
    auto-resume-in-place. `--no-cache` deletes the stable run dir before starting (forcing a clean
    run from scratch) instead of resuming it.
- args:
  - `<workflow>` — the named [workflow](concepts/workflow.md) to run (resolved from the prompt library), or a path via `--workflow`. Required, from whichever form supplies it: the bare first positional when `--workflow` is omitted, or `--workflow` itself (in which case any positional is instead taken as `<flow>` — at most one is accepted, more is a hard error).
  - `<flow>` — optional: run one named [flow](workflow-format.md#flows) of that workflow standalone, as a re-entry point, instead of the whole graph.
- does:
  - run: resolve `<workflow>`/`--workflow` and the optional `<flow>` from the two input shapes —
    positional-only (`workhorse run <name> [<flow>]`) or `--workflow` explicit (any one remaining
    positional becomes `<flow>`, more than one is a hard error); a missing workflow input under
    either shape prints to stderr and exits `1`
  - run: resolve the workflow spec to a `workflow.yaml` path (`_resolve_workflow_path`): a value
    "looks like a path" when it contains `os.sep` (or `os.altsep` on Windows), ends in `.yaml`/
    `.yml`, or already exists on disk (`Path(spec).exists()`) — such a value is used verbatim,
    resolved to an absolute path (`Path(spec).resolve()`); otherwise `spec` is treated as a bare
    library workflow NAME, resolved against the library dir found by `_resolve_library_dir`
    (`workhorse/workhorse/main.py::_resolve_library_dir`) as
    `<library_dir>/workflows/<name>/workflow.yaml` (also `.resolve()`d). `_resolve_library_dir`
    tries, in order: (1) `$WORKHORSE_LIBRARY_DIR`, used (`Path(env).expanduser()`) only if set to a
    non-empty string — an empty/unset env var falls through; (2) the workhorse [config](concepts/config.md)
    file's `library_dir` key via [`get_config_value`](concepts/config.md#get_config_value), used
    (`Path(lib).expanduser()`) only if it resolves to a non-empty string; (3) otherwise `None`. If
    no library is configured, prints `error: '<spec>' is not a path and no prompt library is
    configured.` plus a hint to set `library_dir` in `~/.config/farrier/config.toml` or export
    `WORKHORSE_LIBRARY_DIR` (or pass `--workflow` as a path) to stderr and exits `1` — the hint
    names *farrier's* config path since the two tools' configs can be pointed at the same file via
    `WORKHORSE_CONFIG` (see [config](concepts/config.md))
  - run: back in `_run_run`, if the resolved `workflow_path` doesn't exist on disk, print
    `error: workflow file not found: <path>` to stderr and exit `1`
  - run: pin `AGENT_REPO_DIR` to the launch directory (`Path.cwd()`) when unset, so subprocess
    scripts (a library-installed workflow runs its scripts with cwd = the library, not the target
    repo) resolve the consuming repo rather than the prompt library
  - run: `--cli` (else `AGENT_CLI`, else `claude`) sets `AGENT_CLI` for the run; select and
    eagerly validate the [AgentBackend](concepts/agent-backend.md) via
    [get_backend](concepts/get-backend.md) — an unknown name prints to stderr and exits `1` before
    any node runs, rather than failing mid-run
  - run: resolve `runs_dir` (`--runs-dir`, else `<cwd>/.agents/runs`)
  - run: load `--params`/`--params-file` into a starting-params dict via
    `_load_params` (`workhorse/workhorse/main.py::_load_params`):
    - starts from `params = {}`. If `--params-file` is given, reads its path as text
      (`Path(file).read_text()`); an `OSError` (missing file, permission error, …) prints
      `error: cannot read --params-file <file>: <error>` to stderr and exits `1`
    - processes the two sources **in file-then-inline order** — the `--params-file` text first,
      then `--params` itself — skipping whichever wasn't given (`None`); each non-`None` source is
      `json.loads`-parsed, and a `json.JSONDecodeError` prints
      `error: <label> is not valid JSON: <error>` to stderr and exits `1`, where `<label>` is
      `--params-file` or `--params` matching the source
    - a source that parses to something other than a JSON object (e.g. a list or scalar) prints
      `error: <label> must be a JSON object (key→value map)` to stderr and exits `1`
    - each valid source's dict is folded into `params` via `dict.update` — so **`--params` wins
      over `--params-file`** on overlapping keys, since inline is merged second; with neither flag
      given, returns `{}`
  - run: load the `--context-file`/auto-detected manifest into a starting-context dict
    (`_load_context_manifest`)
  - run: resolve `resume_run_dir` from the mutually-exclusive resume flags — `--resume-run` (an
    absolute path, an existing relative path, or else a name under `runs_dir`; not-a-directory
    exits `1`) or `--resume-latest` (the newest unfinished run dir under `runs_dir`, found by
    `_find_latest_resumable` (`workhorse/workhorse/main.py::_find_latest_resumable`)):
    - a `runs_dir` that doesn't exist on disk yields no candidates
    - otherwise scans `runs_dir`'s immediate children; a child is a candidate only if it's a
      directory **and** holds a [checkpoint file](run-artifacts.md#checkpointjson)
      (`ArtifactWriter.CHECKPOINT_FILE`, i.e. `checkpoint.json`) — a dir with no checkpoint yet
      (never reached its first node) is never resumable
    - each candidate's [`run.json`](run-artifacts.md#runjson) is read and `json.loads`-parsed; a
      candidate whose `run.json` is missing or not valid JSON (`FileNotFoundError` /
      `json.JSONDecodeError`) is silently dropped rather than failing the whole scan
    - a candidate survives only if its `run.json` `terminal` key is `null`/absent — i.e. the run
      never reached a terminal node; a finished run is never returned by `--resume-latest`
    - among the surviving candidates, the one whose `checkpoint.json` has the newest mtime
      (`Path.stat().st_mtime`) wins (`max` over `(mtime, path)` pairs); with no survivors,
      `_find_latest_resumable` returns `None` and `_run_run` prints
      `error: no resumable run found under <runs_dir>` to stderr and exits `1`
    - with neither `--resume-run` nor `--resume-latest` given, `resume_run_dir` stays `None` and
      the auto-resume-in-place rule inside [workflow](concepts/workflow.md#execution) execution
      decides
  - run: call `run(...)` with `auto=True` always (an explicit resume dir short-circuits the auto
    resolution inside it) — forwarding `run_id`, `params`, `context_manifest`, `flow`, and
    `no_cache` — which walks the [workflow](concepts/workflow.md) graph, checkpointing per node
    and writing [run artifacts](run-artifacts.md), then `sys.exit()`s with its return status code
- code: `workhorse/workhorse/main.py::_run_run`
- verify: `workhorse/tests/test_workflow_resolution.py::test_agent_repo_dir_defaults_to_launch_cwd`,
  `workhorse/tests/test_resume_auto.py::test_find_latest_resumable_picks_newest_of_several_unfinished`,
  `workhorse/tests/test_resume_auto.py::test_resume_latest_still_errors_when_none`

`workhorse run coder qa --params '{"story":"CASE-1234"}'` runs the coder workflow's `qa`
flow standalone.

### test
- usage: `workhorse test <workflow_dir> [-k FILTER] [-v]`
- flags:
  - `-k, --filter <pattern>` — a pytest `-k` expression; only tests whose name matches `<pattern>`
    run. Passed through to pytest unchanged (default: run everything under `tests/`).
  - `-v, --verbose` — pass `-v` through to pytest for verbose per-test output.
- args:
  - `<workflow_dir>` — the workflow directory whose `tests/` subdirectory to run; resolved to an
    absolute path before use.
- does:
  - run: resolve `<workflow_dir>` to an absolute path and check `<workflow_dir>/tests/` exists;
    print `error: no tests/ directory found in <workflow_dir>` to stderr and exit `1` if not
  - run: check that `pytest` is importable; if not, print an install hint (`pip install
    'workhorse-agent[test]'`) to stderr and exit `1` — pytest is an optional dependency (the
    `test` extra), not a hard runtime requirement of `workhorse`
  - run: build the pytest argv as `[<tests_dir>]`, appending `-k <pattern>` when `--filter` is
    given and `-v` when `--verbose` is given
  - run: invoke `pytest.main(argv)` in-process and exit with its return code (`0` all passed, `1`
    some failed, other pytest exit codes propagate unchanged — see pytest's own exit-code table)
- code: `workhorse/workhorse/main.py::_run_test`

A workflow's `tests/*.py` files are ordinary pytest tests that import
[`workhorse.testing`](concepts/testing.md) to drive the real `workhorse` CLI as a subprocess
against an isolated sandbox — `workhorse test <workflow_dir>` is how a workflow author (or CI) runs
that suite without hand-rolling the pytest invocation.

### dot
- usage: `workhorse dot --workflow <path> [--pin K=V] [--leaf NODE] [--name ID] [-o out.dot]`
- flags:
  - `--workflow <path>` — type `str` (path), **required**. The [workflow](concepts/workflow.md)
    `workflow.yaml` to render.
  - `--pin <K=V>` — type `str`, repeatable (`action=append`), default: none. Pins a branch
    variable so any [branch node](concepts/workflow.md) whose `path` equals `K` collapses to its
    single edge for value `V`; the now-unreachable side of the branch is pruned by the renderer's
    reachability walk. Carves one mode's view out of a multi-mode graph (e.g. `--pin mode=epic`).
  - `--leaf <node>` — type `str` (node id), repeatable (`action=append`), default: none. Renders
    `<node>` as a dead-end: its outgoing edges are suppressed, so reachability stops there. Cuts a
    cross-view bridge not gated by a pinned branch.
  - `--name <id>` — type `str`, default: none (falls back to the workflow's own `name`, sanitized
    to a valid DOT identifier). Overrides the rendered `digraph` identifier.
  - `-o, --output <path>` — type `str` (path), default: none (write to stdout). Writes the DOT
    text to `<path>` instead.
- does:
  - run: resolve `--workflow` to an absolute path; if it doesn't exist, print
    `error: workflow file not found: <path>` to stderr and exit `1`
  - run: parse it into a [workflow](concepts/workflow.md) `Graph` via
    [load_workflow](concepts/load-workflow.md); on a `ValueError` (malformed YAML/schema), print
    `error: <message>` to stderr and exit `1`
  - run: parse the repeated `--pin KEY=VALUE` flags into a `dict[str, str]`; an entry missing `=`
    or with an empty key prints `error: --pin must be KEY=VALUE (got '<item>')` to stderr and exits
    `1`
  - run: collect `--leaf` flags into a `set[str]` of node ids
  - run: render the graph to Graphviz DOT — pins/leaves/name applied per the [DOT
    renderer](concepts/dot-renderer.md)
  - run: if `--output` is given, write the DOT text to that path and print
    `[workhorse] wrote <path>` to stderr; otherwise write the DOT text to stdout
- code: `workhorse/workhorse/main.py::_run_dot`
- verify: `workhorse/tests/test_dot.py::test_name_override`

### config
- usage: `workhorse config <show|get|list|set-library|set-stablemate> [args]`
- args:
  - `show [key]` — with no `key`: print every key currently loaded from the config file, one
    `key=value` line per key, in the file's own order. With `key`: print just that key's bare value
    (no `key=` prefix); if the key isn't set, print `error: '<key>' is not set in <config_path>` to
    stderr and exit `1`.
  - `get <name>` — print one config value addressed by a dot-path `<name>` into the loaded TOML
    (e.g. `power.high.claude` reaches the `[power.high.claude]` table). A `dict`/`list` value prints
    as indented (`indent=2`), key-sorted JSON; a scalar prints bare. An unresolved path (any segment
    missing, or a non-dict segment) prints nothing and exits `0` — silent, unlike `show`'s hard error
    on a missing top-level key.
  - `list` — print `# <config_path>` then the whole loaded config as indented, key-sorted JSON — the
    power→model table in full.
  - `set-library <path>` — expand `~` and resolve `<path>` to an absolute path, persist it under the
    `library_dir` top-level key, and print `library_dir=<path>`. This is where [`workhorse
    run`](#run)'s bare-name workflow resolution reads its prompt-library location from.
  - `set-stablemate <path>` — same shape as `set-library`, persisting `stablemate_dir` (consumed
    elsewhere as `CODER_WORKSPACE` for workflow scripts that operate on the stablemate checkout).
- does:
  - run: `argparse` requires exactly one of `show`/`get`/`list`/`set-library`/`set-stablemate` as the
    second positional (a required sub-subparser); a bare `workhorse config` with none given is a
    parse error (exit `2`) before `_run_config` ever runs
  - run: `set-library`/`set-stablemate` resolve `<path>` (`~`-expanded, absolute) and call
    [`write_config_key`](concepts/config.md#write_config_key) directly, without loading or echoing
    the rest of the config
  - run: `show`/`get`/`list` all call [`load_config`](concepts/config.md#load_config) first (`show`
    iterates its items directly; `get` calls [`get_config_value`](concepts/config.md#get_config_value)
    on it; `list` prints [`config_path`](concepts/config.md#location) then the whole dict as
    indented, key-sorted JSON), then format it per subcommand as above
- code: `workhorse/workhorse/main.py::_run_config`

Reads and writes the [workhorse config file](concepts/config.md) (a small TOML file holding
`library_dir`, `stablemate_dir`, and a `[power.<tier>.<backend>]` model/effort table that [`workhorse
run`](#run)'s power resolution consumes). The subcommand names and output shapes mirror farrier's own
`farrier config` (`show`/`get`/`list`/`set-library`/`set-stablemate`), so `agents.mk`/scripts written
against one tool read the same way against the other — but by default the two tools keep **separate**
config files (distinct `platformdirs` app names: `~/.config/workhorse/config.toml` vs
`~/.config/farrier/config.toml` on Linux); pointing `WORKHORSE_CONFIG` at farrier's `config.toml` is
how an operator makes them actually share one file.

### version
- usage: `workhorse version`
- does:
  - run: read the installed version of the `workhorse-agent` distribution via
    `importlib.metadata.version("workhorse-agent")` (the PyPI/installed package name; the import
    package and CLI command are both `workhorse` — see the surface intro) and print it to stdout
  - run: return with no explicit `sys.exit` (exit `0`); raises uncaught if `workhorse-agent` isn't
    installed as a package (e.g. running from a source checkout without an editable install), since
    no fallback is attempted
- code: `workhorse/workhorse/main.py::main`

## Flows

End-to-end journeys across these commands:

- [Set up the prompt library and run a workflow](flows/workhorse-setup-and-run.md) — first-time
  `config set-library` then `run`.
- [Author, visualize, and run a workflow](flows/workhorse-author-visualize-run.md) — hand-write a
  `workflow.yaml`, sanity-check it with `dot`, then `run` it.
- [Author and run a workflow's test suite](flows/workhorse-author-test.md) — write `tests/*.py`
  against `workhorse.testing` and drive them with `test`.
- [Choose the agent CLI backend and power tier](flows/workhorse-choose-backend-and-power.md) —
  point `run --cli` at a different harness and set its power tier in `config`.
- [Crash and resume in place](flows/workhorse-crash-resume.md) — an unattended `run` dies mid-graph
  and is re-launched with the identical command to resume from its last checkpoint.
