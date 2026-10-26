---
type: cli
slug: workhorse
title: workhorse
---
# workhorse

`workhorse` is the engine behind every workflow's console script. A workflow package installs one
script named `workhorse-<workflow>`, and that script carries the workflow's own registry, so each
command below acts on that one workflow. The book drives the `workhorse-loop-runner` script, the
shipped quick-start workflow, whose dry run needs no repository and no agent CLI.

The script starts runs ([run launch](concepts/run-launch.md)), draws the workflow's
[state machine](concepts/state-machine-engine.md), steers a run in flight over its
[control channel](concepts/run-control.md), answers its [operator inbox](concepts/operator-inbox.md)
and replays one recorded [agent turn](concepts/agent-turns.md). How the first token picks a command
is in [CLI dispatch](concepts/cli-dispatch.md). What a run writes to disk is in
[run directory](concepts/run-directory.md). Which agent CLI a run drives is in
[agent backends](concepts/agent-backends.md) and [profiles and config](concepts/profiles-and-config.md).
The rest of the engine is in [shared core](concepts/shared-core.md),
[telemetry and logs](concepts/telemetry-and-logs.md), [prompt rendering](concepts/prompt-rendering.md),
[job containment](concepts/job-containment.md), [testing helpers](concepts/testing-helpers.md) and
[packaging](concepts/packaging.md).

Ten journeys walk the commands end to end. An author can [check a workflow](flows/check-workflow.md),
[fix a launch's settings](flows/fix-launch-config.md), [fix a launch's inputs](flows/fix-launch-inputs.md),
[pick a turn to replay](flows/pick-replay-turn.md) and [size a replay variant](flows/size-replay-variant.md).
An operator can [answer the inbox](flows/answer-inbox.md), [inspect a stopped run](flows/inspect-stopped-run.md),
[steer a live run](flows/steer-live-run.md), [rewind a failed run](flows/rewind-failed-run.md) and
[resume a stopped run](flows/resume-stopped-run.md). The scenarios read run directories seeded by
[seeded runs](fixtures/seeded-runs.md) and [inbox run](fixtures/inbox-run.md).

- binary: workhorse-loop-runner
- code: `workhorse/workhorse/cli/__init__.py::main` @408aa8a4f987
- detail: [CLI dispatch](concepts/cli-dispatch.md)

## Commands

### run

- usage: workhorse-loop-runner [run] [FLOW] [--cli NAME | --profile NAME] [--config PATH] [--workspace NAME] [--params JSON] [--params-file PATH] [--context-file PATH] [--runs-dir DIR] [--run-id ID] [--dry-run] [--worktree [--worktree-branch NAME] [--worktree-base REF]] [--resume-run PATH_OR_RUN_ID | --resume-latest | --no-cache]
- flags:
  - `--cli NAME` picks the agent CLI backend for the whole run. It overrides `AGENT_CLI`, which overrides the config's `default_cli`. The default is claude.
  - `--profile NAME` resolves models from `[profiles.NAME]` in the config, and the profile names its own CLI. A profile whose key matches its own `cli` is auto-selected on a fresh run — whether or not `--cli` names that same CLI — when neither `--profile` nor a resumed run's recorded profile already picked one.
  - `--config PATH` reads this config file and nothing else. It overrides `$STABLEMATE_CONFIG`, which overrides `$WORKHORSE_CONFIG`.
  - `--workspace NAME` runs across the named `[workspaces]` entry of the home config: it sets `$STABLEMATE_WORKSPACE` for every agent turn and for ostler, initialises the artifacts repo, and adds `workspace` to the params the workflow receives. A bad name refuses before the run opens its run directory. A resume with no `--workspace` restores the workspace the run recorded.
  - `--params JSON` is an inline JSON object of workflow params. It wins over `--params-file` on a shared key.
  - `--params-file PATH` reads the same JSON object from a file.
  - `--context-file PATH` names the farrier context manifest. The default is `$AGENT_REPO_DIR/.agents/agents-context.<cli>.json`, then `agents-context.json`, and a run with neither renders without one.
  - `--runs-dir DIR` is where run directories go. The default is `./.agents/runs`.
  - `--run-id ID` names the stable run directory `<workflow>-<id>`. The default is a digest of the params, or `default` with no params.
  - `--dry-run` stubs every node and agent turn and checks that the workflow binds.
  - `--worktree` cuts a fresh branch and git worktree for the run. `--worktree-branch` and `--worktree-base` override its branch name and base ref. The run's terminal state decides whether the worktree is removed or kept, as [run launch](concepts/run-launch.md) describes.
  - `--resume-run`, `--resume-latest` and `--no-cache` exclude each other. The first resumes a named run, the second the newest unfinished one, the third deletes the stable run directory first.
- args:
  - `FLOW` runs one flow sub-graph on its own. Omitted, the run starts at the workflow's entry flow.
- fixture: seeded-runs
- does:
  - A dry run stubs every node and agent turn and reports that each one ran its stand-in.
- run: invoke(argv=["run", "--dry-run", "--no-cache", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml"])
- verify: stdout(text="[workhorse] dry-run ok — every node ran its stand-in")
- exits: 0 when a dry run finds nothing wrong.
- run: invoke(argv=["run", "--dry-run", "--no-cache", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml"])
- verify: exit_status(code=0)
- code: `workhorse/workhorse/cli/run.py::add_arguments` @6bb7cf530876
- code: `workhorse/workhorse/cli/run.py::run` @6bb7cf530876
- code: `workhorse/workhorse/cli/run.py::invocation` @6bb7cf530876
- code: `workhorse/workhorse/cli/run.py::apply_config_path` @6bb7cf530876
- code: `workhorse/workhorse/cli/run.py::library_dirs` @6bb7cf530876
- code: `workhorse/workhorse/cli/params.py::load_params` @43dababb9ed6
- code: `workhorse/workhorse/manifest.py::load_context_manifest` @e896594bc36c
- detail: [run launch](concepts/run-launch.md)

### dot

- usage: workhorse-loop-runner dot [--name NAME] [-o PATH | --output PATH]
- flags:
  - `--name NAME` overrides the digraph identifier. The default is the workflow's name. Every character outside `A-Za-z0-9_` becomes `_`.
  - `-o PATH`, `--output PATH` writes the DOT text to PATH instead of stdout.
- fixture: none, because the graph comes from the workflow's own registry and reads no file
- does:
  - The graph carries a legend cluster beside one cluster per flow.
- run: invoke(argv=["dot"])
- verify: stdout(text="subgraph cluster_legend {")
- exits: 0 after the graph is printed.
- run: invoke(argv=["dot"])
- verify: exit_status(code=0)
- code: `workhorse/workhorse/cli/dot.py::add_arguments` @d156b791d036
- code: `workhorse/workhorse/cli/dot.py::run` @d156b791d036
- code: `workhorse/workhorse/pyflow/dot.py::to_dot` @1de4e44f4848
- detail: [state machine engine](concepts/state-machine-engine.md)

### control

- usage: workhorse-loop-runner control ACTION [NAME] [--run ID|DIR] [--runs-dir DIR] [--gate PATH] [--text TXT] [--core] [--at-boundary] [--to STATE] [--param NAME=VALUE] [--param-from-turn NAME=PATH] [--keep NAME] [--params] [--wait] [--timeout S]
- flags:
  - `--run ID|DIR` names the run by its run id, its run-dir name or a path. The default is the newest unfinished run under `--runs-dir`. A name no directory matches is asked of groom's `/api/live` at `$GROOM_URL`, default `http://127.0.0.1:8787`.
  - `--runs-dir DIR` is where run directories live. The default is `./.agents/runs`.
  - `--gate PATH` and `--text TXT` belong to `answer` only. Without `--text`, `answer` reads the text from stdin.
  - `--core` also replaces workhorse itself on `reload`. `--at-boundary` lets the streaming turn finish first. Neither applies to `stop`, `rewind` or `resume`.
  - `--to STATE`, `--param NAME=VALUE`, `--param-from-turn NAME=PATH` and `--keep NAME` belong to `rewind` only. A `--param` value is JSON when it parses, else the text as typed.
  - `--params` belongs to `status` only and prints the checkpoint from disk.
  - `--wait` belongs to `stop` only. `--timeout S` bounds `stop --wait` and `resume`, default 120.
- args:
  - `ACTION` is one of reload, stop, status, questions, answer, switch-cli, switch-profile, rewind and resume. The first seven talk to a live run over its control socket. `rewind` and `resume` act on a stopped run.
  - `NAME` is the CLI for `switch-cli` and `resume`, and the profile for `switch-profile`. Every other action refuses it.
- fixture: seeded-runs
- does:
  - `status --params` prints the checkpoint's state from disk as sorted JSON.
- run: invoke(argv=["control", "status", "--params", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: json_path(path="$.state", equals="write")
- does:
  - `status --params` prints the checkpoint's params.
- run: invoke(argv=["control", "status", "--params", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: json_path(path="$.params.topic", equals="cats")
- does:
  - `status --params` prints the checkpoint's flow.
- run: invoke(argv=["control", "status", "--params", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: json_path(path="$.flow", equals="Main")
- exits: 0 when `status --params` prints the checkpoint.
- run: invoke(argv=["control", "status", "--params", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: exit_status(code=0)
- code: `workhorse/workhorse/cli/control.py::add_arguments` @d578cf93b87e
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e
- code: `workhorse/workhorse/cli/offline.py::run_rewind` @cd7d6c6c8f77
- code: `workhorse/workhorse/cli/offline.py::run_resume` @cd7d6c6c8f77
- code: `workhorse/workhorse/cli/offline.py::print_params` @cd7d6c6c8f77
- code: `workhorse/workhorse/cli/target.py::resolve_target` @8b8132797882
- detail: [run control](concepts/run-control.md)

### inbox

- usage: workhorse-loop-runner inbox (read [--all] | reply ID TEXT) [--run ID|DIR] [--runs-dir DIR]
- flags:
  - `--all` makes `read` print every message. The default is outstanding messages only.
  - `--run ID|DIR` and `--runs-dir DIR` pick the run exactly as `control` does.
- args:
  - `ACTION` is `read` or `reply`.
  - `ID` and `TEXT` are the message id and the reply text, both required by `reply`.
- fixture: inbox-run dir=answer
- does:
  - `read` prints each outstanding message as an id, timestamp and status line.
- run: invoke(argv=["inbox", "read", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stdout(text="[m1] 2026-01-01T00:00:00+00:00 (outstanding)")
- exits: 0 after `read` prints.
- run: invoke(argv=["inbox", "read", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: exit_status(code=0)
- code: `workhorse/workhorse/cli/inbox.py::add_arguments` @7789b147be16
- code: `workhorse/workhorse/cli/inbox.py::run` @7789b147be16
- code: `workhorse/workhorse/inbox.py::reply` @e2ad0fc21f23
- detail: [operator inbox](concepts/operator-inbox.md)

### replay

- usage: workhorse-loop-runner replay TURN --run ID|DIR [--runs-dir DIR] [--prompt FILE] [--max-prompt-chars N] [--repeat N] [--profile NAME] [--config PATH] [--discard]
- flags:
  - `--run ID|DIR` is required and names the run that recorded the turn. It never asks groom.
  - `--prompt FILE` sends this prompt instead of the recorded `prompt.md`.
  - `--max-prompt-chars N` is the largest variant to send. The default is twice the recorded prompt's length.
  - `--repeat N` runs the turn N times, each from the recorded start. The default is 1.
  - `--profile NAME` runs under another profile. The default is the one the turn recorded.
  - `--config PATH` reads profiles from this config file, as `run` does.
  - `--discard` resets the turn's working trees to its start even when they hold changes or later commits.
- args:
  - `TURN` is a directory name under the run's `turns/`, such as `000-00023-write-page`.
- fixture: seeded-runs
- errors: A working tree whose head moved from the turn's start is refused, because a replay resets it.
- run: invoke(argv=["replay", "000-00004-moved", "--run", "/tmp/workhorse-book/seeded/replay-run"])
- verify: stderr(text="and a replay resets its branch to that start, dropping every commit after it. Replay against a copy of the checkout, or pass --discard.")
- exits: 1 on every refusal after the arguments parse.
- run: invoke(argv=["replay", "000-00004-moved", "--run", "/tmp/workhorse-book/seeded/replay-run"])
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/replay.py::add_arguments` @d6c1e9fdd435
- code: `workhorse/workhorse/cli/replay.py::run` @d6c1e9fdd435
- code: `workhorse/workhorse/cli/replay.py::replay_turn` @d6c1e9fdd435
- code: `workhorse/workhorse/cli/replay.py::Replay` @d6c1e9fdd435
- detail: [agent turns](concepts/agent-turns.md)

### version

- usage: workhorse-loop-runner version
- does:
  - Prints the installed workhorse-agent distribution version.
- run: invoke(argv=["version"])
- verify: stdout(matches="^[0-9]+[.][0-9]+")
- exits: 0 after printing.
- run: invoke(argv=["version"])
- verify: exit_status(code=0)
- code: `workhorse/workhorse/cli/version.py::run` @bf3e2cf7e8dc
- code: `workhorse/workhorse/cli/version.py::add_arguments` @bf3e2cf7e8dc
- detail: [packaging](concepts/packaging.md)

## Invocations

### show-top-level-help

- on: [run](#run)
- trigger: the first token is `-h` or `--help`
- does:
  - Prints the top-level help, which lists every command.
- run: invoke(argv=["--help"])
- verify: stdout(text="{run,dot,control,inbox,replay,version}")
- code: `workhorse/workhorse/cli/__init__.py::main` @408aa8a4f987
- code: `workhorse/workhorse/cli/parser.py::build_parser` @6b7ae77922ce
- code: `workhorse/workhorse/__init__.py::__all__` @331cdb028c18

### fall-through-to-run

- on: [run](#run)
- trigger: the first token names no command
- does:
  - The script runs `run` with every token as its arguments.
- run: invoke(argv=["--cli", "BoGuS", "--config", "/tmp/workhorse-book/seeded/config.toml"])
- verify: stderr(text="error: unknown CLI backend")
- does:
  - The CLI name is lower-cased before it is looked up, and the refusal lists every backend.
- run: invoke(argv=["--cli", "BoGuS", "--config", "/tmp/workhorse-book/seeded/config.toml"])
- verify: stderr(text="error: unknown CLI backend 'bogus' (set AGENT_CLI, --cli or the config's default_cli to one of: claude, cline, codex, copilot, opencode)")
- code: `workhorse/workhorse/cli/__init__.py::main` @408aa8a4f987

### refuse-cli-with-profile

- on: [run](#run)
- trigger: an author passes both `--cli` and `--profile`
- does:
  - Refuses the launch before reading any config, and says a profile carries its own CLI.
- run: invoke(argv=["run", "--cli", "claude", "--profile", "cheap"])
- verify: stderr(matches="error: --cli and --profile are mutually exclusive — a profile carries its own .cli. field[.] Drop one of them[.]")
- status: 2 on `--cli` with `--profile`.
- run: invoke(argv=["run", "--cli", "claude", "--profile", "cheap"])
- verify: exit_status(code=2)
- code: `workhorse/workhorse/cli/run.py::run` @6bb7cf530876

### refuse-missing-config

- on: [run](#run)
- trigger: an author names a `--config` path that is no file
- does:
  - Refuses the launch and names the path as typed.
- run: invoke(argv=["run", "--config", "nowhere.toml"])
- verify: stderr(text="error: --config nowhere.toml: no such file")
- status: 1 on a refused config, profile, params file or context manifest.
- run: invoke(argv=["run", "--config", "nowhere.toml"])
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/run.py::apply_config_path` @6bb7cf530876

### refuse-unknown-resume-run

- on: [run](#run)
- trigger: an author resumes a run id no directory matches
- does:
  - Refuses the resume and reports where it looked.
- run: invoke(argv=["run", "--resume-run", "nope", "--runs-dir", "nowhere"])
- verify: stderr(matches="error: resume run dir not found for 'nope' [(]looked under /.*/nowhere[)]")
- code: `workhorse/workhorse/rundir.py::resolve_run_dir` @aa85ef04e897

### refuse-no-resumable-run

- on: [run](#run)
- trigger: an author asks for the newest unfinished run
- does:
  - Skips every directory with no checkpoint and every finished run, then names the runs directory when none is left.
- run: invoke(argv=["run", "--resume-latest", "--runs-dir", "/tmp/workhorse-book/seeded"])
- verify: stderr(text="error: no resumable run found under /tmp/workhorse-book/seeded")
- code: `workhorse/workhorse/rundir.py::find_latest_resumable` @aa85ef04e897

### refuse-two-resume-flags

- on: [run](#run)
- trigger: an author passes two of the resume flags
- does:
  - The argument parser refuses the second flag and names the first one it clashes with.
- run: invoke(argv=["run", "--resume-latest", "--resume-run", "nope"])
- verify: stderr(text="error: argument --resume-run: not allowed with argument --resume-latest")
- code: `workhorse/workhorse/cli/run.py::add_arguments` @6bb7cf530876

### refuse-unknown-profile

- on: [run](#run)
- trigger: an author names a profile the config does not declare
- does:
  - Refuses the launch and lists the known profiles in sorted order.
- run: invoke(argv=["run", "--profile", "ghost", "--config", "/tmp/workhorse-book/seeded/config.toml"])
- verify: stderr(text="error: unknown profile 'ghost' in /tmp/workhorse-book/seeded/config.toml (known: bare, cheap, odd)")
- code: `workhorse/workhorse/cli/run.py::run` @6bb7cf530876
- code: `workhorse/workhorse/profile.py::select_backend` @5940a4ebe776
- code: `workhorse/workhorse/_vendor/stablemate_core/profiles.py::select_profile` @0f757c16382b
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::load_config` @7a84c0cc67a5
- code: `workhorse/workhorse/_vendor/stablemate_core/discovery.py::base_library_dir` @42eebfdfea77
- code: `workhorse/workhorse/packaged.py::PackagedWorkflowError` @7eeb988b4091
- code: `workhorse/workhorse/runner/backends/__init__.py::AgentBackend` @04abd4b8f62b
- code: `workhorse/workhorse/runner/backends/registry.py::get_backend` @da60c2e93d28
- code: `workhorse/workhorse/runner/backends/claude.py::ClaudeBackend` @c8219f44b0ac
- code: `workhorse/workhorse/runner/backends/codex.py::CodexBackend` @2e04457e239e
- code: `workhorse/workhorse/runner/backends/cline.py::ClineBackend` @6e58fb02886c
- code: `workhorse/workhorse/runner/backends/copilot.py::CopilotBackend` @6ee4a19c5aa9
- code: `workhorse/workhorse/runner/backends/opencode.py::OpenCodeBackend` @7bd44f4d3832
- code: `workhorse/workhorse/runner/backends/delegates.py::Delegate` @543f51f3d262
- code: `workhorse/workhorse/runner/backends/jsonl.py::JsonlBackend` @f6c5136add76
- code: `workhorse/workhorse/runner/backends/turn.py::TurnState` @53dc2823fd84
- code: `workhorse/workhorse/runner/backends/codex_guard.py::Policy` @736e50949720
- code: `workhorse/workhorse/runner/backends/codex_shell.py::shell_denial` @3366bb96722b

### refuse-profile-without-cli

- on: [run](#run)
- trigger: an author names a profile with no `cli` field
- does:
  - Refuses the launch and says every profile must declare its CLI.
- run: invoke(argv=["run", "--profile", "bare", "--config", "/tmp/workhorse-book/seeded/config.toml"])
- verify: stderr(text="error: [profiles.bare] has no cli field — every profile must declare the CLI it runs under.")
- code: `workhorse/workhorse/cli/run.py::run` @6bb7cf530876

### refuse-undrivable-profile

- on: [run](#run)
- trigger: an author names a profile whose CLI this run cannot drive
- does:
  - Refuses the launch and lists the CLIs the run can drive.
- run: invoke(argv=["run", "--profile", "odd", "--config", "/tmp/workhorse-book/seeded/config.toml"])
- verify: stderr(text="error: profile 'odd' declares cli = 'nope' (in /tmp/workhorse-book/seeded/config.toml), and this run can drive only claude, cline, codex, copilot, opencode")
- code: `workhorse/workhorse/cli/run.py::run` @6bb7cf530876

### refuse-unreadable-params-file

- on: [run](#run)
- trigger: an author names a `--params-file` that cannot be read
- does:
  - Refuses the launch before any JSON is parsed, and names the file as typed.
- run: invoke(argv=["run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--params-file", "nowhere.json"])
- verify: stderr(text="error: cannot read --params-file nowhere.json: ")
- code: `workhorse/workhorse/cli/params.py::load_params` @43dababb9ed6

### refuse-params-not-json

- on: [run](#run)
- trigger: an author passes inline `--params` that is not JSON
- does:
  - Refuses the launch and names the inline flag.
- run: invoke(argv=["run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--params", "{"])
- verify: stderr(text="error: --params is not valid JSON: ")
- code: `workhorse/workhorse/cli/params.py::load_params` @43dababb9ed6

### refuse-params-file-not-object

- on: [run](#run)
- trigger: an author's `--params-file` holds JSON that is not an object
- does:
  - Refuses the launch, names the file flag and asks for a key-to-value map.
- run: invoke(argv=["run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--params-file", "/tmp/workhorse-book/seeded/params-list.json"])
- verify: stderr(text="error: --params-file must be a JSON object (key→value map)")
- code: `workhorse/workhorse/cli/params.py::load_params` @43dababb9ed6

### refuse-params-not-object

- on: [run](#run)
- trigger: an author's inline `--params` holds a JSON list
- does:
  - Refuses the launch, names the inline flag and asks for a key-to-value map.
- run: invoke(argv=["run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--params", "[1]"])
- verify: stderr(text="error: --params must be a JSON object (key→value map)")
- code: `workhorse/workhorse/cli/params.py::load_params` @43dababb9ed6

### refuse-missing-context-file

- on: [run](#run)
- trigger: an author names a `--context-file` that does not exist
- does:
  - Refuses the launch and names the path as given.
- run: invoke(argv=["run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--context-file", "nowhere.json"])
- verify: stderr(text="error: --context-file not found: nowhere.json")
- does:
  - The refusal names the command that generates a manifest.
- run: invoke(argv=["run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--context-file", "nowhere.json"])
- verify: stderr(matches="Run .make agent-install. to generate .agents/agents-context.json")
- code: `workhorse/workhorse/manifest.py::load_context_manifest` @e896594bc36c

### refuse-context-not-json

- on: [run](#run)
- trigger: an author's context manifest is not JSON
- does:
  - Refuses the launch and names the manifest it could not read.
- run: invoke(argv=["run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--context-file", "/tmp/workhorse-book/seeded/bad-context.json"])
- verify: stderr(text="error: cannot read context manifest /tmp/workhorse-book/seeded/bad-context.json: ")
- code: `workhorse/workhorse/manifest.py::load_context_manifest` @e896594bc36c

### refuse-context-not-object

- on: [run](#run)
- trigger: an author's context manifest holds a JSON list
- does:
  - Refuses the launch and asks for a JSON object.
- run: invoke(argv=["run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--context-file", "/tmp/workhorse-book/seeded/list-context.json"])
- verify: stderr(text="error: context manifest /tmp/workhorse-book/seeded/list-context.json must be a JSON object")
- code: `workhorse/workhorse/manifest.py::load_context_manifest` @e896594bc36c

### dry-run-workflow

- on: [run](#run)
- trigger: an author checks the workflow binds before an unattended run
- does:
  - Stubs every node and names the run directory it wrote.
- run: invoke(argv=["run", "--dry-run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--run-id", "walk"])
- verify: stdout(matches="artifacts in /.*/[.]agents/runs/")
- code: `workhorse/workhorse/pyflow/run.py::run_pyflow` @c14993f8e31a
- code: `workhorse/workhorse/artifacts.py::ArtifactWriter` @41646e08117a
- code: `workhorse/workhorse/logsetup.py::setup` @dbe8304930de
- code: `workhorse/workhorse/otel.py::install` @c3d8848371ee
- code: `workhorse/workhorse/gitstate.py::bind` @88deaba0786e
- code: `workhorse/workhorse/reload.py::boundary_requested` @c7be7ac9ef2a
- code: `workhorse/workhorse/references.py::missing_references` @c6ff9b16296e
- code: `workhorse/workhorse/templates.py::turn_catalog` @921bcf52f398
- code: `workhorse/workhorse/turnkey.py::VisitKey` @0dffcaf7cfde
- code: `workhorse/workhorse/pyflow/driver.py::drive` @6ee79b75b0f1
- code: `workhorse/workhorse/pyflow/transitions.py::Continue` @05edc5a834cc
- code: `workhorse/workhorse/pyflow/activity.py::ActivityLog` @fc149a498518
- code: `workhorse/workhorse/pyflow/engine.py::Engine` @922a7b361e6e
- code: `workhorse/workhorse/pyflow/registry.py::Registry` @a2d3d9fd50b3
- code: `workhorse/workhorse/pyflow/names.py::NameIndex` @ec28548d30de
- code: `workhorse/workhorse/pyflow/blueprint.py::Blueprint` @4911263291b8
- code: `workhorse/workhorse/pyflow/preflight.py::preflight` @3460fa12f550
- code: `workhorse/workhorse/pyflow/graph.py::registry_graphs` @103855581ca1
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow` @9704358a90e7
- code: `workhorse/workhorse/control.py::NULL_CHANNEL` @52683677757e
- code: `workhorse/workhorse/config_run.py::RunConfig` @d96de3e447d1
- code: `workhorse/workhorse/runner/backends/null.py::NullBackend` @4464f8371e1f
- code: `workhorse/workhorse/runner/ladder.py::AgentRunner` @d22216e866b4
- code: `workhorse/workhorse/runner/spec.py::AgentNode` @ea80f1fc2fed
- code: `workhorse/workhorse/context.py::WorkflowContext` @313726f99d8a
- code: `workhorse/workhorse/runner/caps.py::cap_delay_seconds` @57869724201e
- code: `workhorse/workhorse/runner/extract.py::extract_outputs` @92cafcbdca28
- code: `workhorse/workhorse/runner/reframe.py::retry_prompt` @d40203f18c9b
- code: `workhorse/workhorse/runner/turn_record.py::RenderedTurn` @50530978b759
- code: `workhorse/workhorse/runner/waits.py::RecoveryWaitBudget` @d0c5459fe618
- code: `workhorse/workhorse/runner/redact.py::SecretRedactor` @40448a232adc
- code: `workhorse/workhorse/runner/transcript.py::bind` @761e9ee51dc0
- code: `workhorse/workhorse/runner/worktree_guard.py::install` @0762312c18d4
- code: `workhorse/workhorse/runner/process.py::ProcessSupervisor` @82335d356999
- code: `workhorse/workhorse/runner/acp.py::TranscriptMapper` @c239ef982808
- code: `workhorse/workhorse/runner/usage.py::TurnUsage` @ebb8fd7db412
- code: `workhorse/workhorse/runner/failure.py::BackendInvocationError` @67f43d6fb9ef
- code: `workhorse/workhorse/sessions.py::slug` @f6e3de822358
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::Clock` @99322cfda640
- code: `workhorse/workhorse/pyflow/errors.py::PyflowError` @6daae074220e
- code: `workhorse/workhorse/pyflow/park.py::ask` @3bf2ebf15981
- code: `workhorse/workhorse/pyflow/prompts.py::PromptResolver` @7fe9cd1ee20c
- code: `workhorse/workhorse/pyflow/replies.py::declared_reply` @0ccecab8791a
- code: `workhorse/workhorse/pyflow/worktree.py::WorktreeError` @2da3d23c967a
- code: `workhorse/workhorse/worklist.py::WorkList` @5527e3514bc3
- code: `workhorse/workhorse/_vendor/stablemate_core/skill_refs.py::SkillCatalog` @ebf1b69c7565

### name-the-graph

- on: [dot](#dot)
- trigger: an author gives the graph a name of their own
- does:
  - `--name` replaces every character outside letters, digits and underscore with an underscore.
- run: invoke(argv=["dot", "--name", "my graph-1"])
- verify: stdout(text="digraph my_graph_1 {")
- code: `workhorse/workhorse/pyflow/dot.py::to_dot` @1de4e44f4848

### render-dot-file

- on: [dot](#dot)
- trigger: an author renders the workflow's graph to a file
- does:
  - `-o` writes the graph to the named file.
- run: invoke(argv=["dot", "-o", "graph.dot"])
- verify: created(subject="graph.dot")
- does:
  - A write to a file names the file on stderr.
- run: invoke(argv=["dot", "-o", "graph.dot"])
- verify: stderr(text="[workhorse] wrote graph.dot")
- code: `workhorse/workhorse/cli/dot.py::run` @d156b791d036

### write-dot-long-flag

- on: [dot](#dot)
- trigger: an author spells the output flag `--output`
- does:
  - The written file holds the DOT text with its legend.
- run: invoke(argv=["dot", "--output", "graph2.dot"])
- verify: contents(subject="graph2.dot", text="subgraph cluster_legend {")
- code: `workhorse/workhorse/cli/dot.py::add_arguments` @d156b791d036

### print-version

- on: [version](#version)
- trigger: an operator asks which engine release a workflow script runs
- does:
  - Prints the version on one line.
- run: invoke(argv=["version"])
- verify: stdout(matches="^[0-9]+[.][0-9.]+[a-z0-9.+-]*$")
- code: `workhorse/workhorse/cli/version.py::run` @bf3e2cf7e8dc

### print-checkpoint-params

- on: [control](#control)
- trigger: an operator reads where a stopped run would resume
- does:
  - prints the checkpoint as JSON with no gate it waits on
- run: invoke(argv=["control", "status", "--params", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stdout(matches="waiting_on.: null")
- verify: stdout(matches="(?s)^(?!.*worktree).*$")
- code: `workhorse/workhorse/cli/offline.py::print_params` @cd7d6c6c8f77

### print-worktree-params

- on: [control](#control)
- trigger: an operator reads the checkpoint of a run dispatched into a worktree
- does:
  - adds a `worktree` key (`path`, `branch`, `base`, `outcome`) when the run's `run.json` records a worktree it was dispatched into; omits the key for a run with no worktree
- run: invoke(argv=["control", "status", "--params", "--run", "/tmp/workhorse-book/seeded/worktree-run"])
- verify: stdout(text="\"worktree\": {\n    \"base\": \"main\",\n    \"branch\": \"feature-x\",\n    \"outcome\": null,\n    \"path\": \"/tmp/workhorse-book/seeded/worktree-run/wt\"\n  }")
- code: `workhorse/workhorse/cli/offline.py::print_params` @cd7d6c6c8f77
- code: `workhorse/workhorse/cli/offline.py::_worktree` @cd7d6c6c8f77

### refuse-params-without-checkpoint

- on: [control](#control)
- trigger: an operator asks for the checkpoint of a directory that has none
- does:
  - Refuses to print and names the checkpoint path it tried.
- run: invoke(argv=["control", "status", "--params", "--run", "/tmp/workhorse-book/seeded/bare"])
- verify: stderr(text="error: cannot read checkpoint /tmp/workhorse-book/seeded/bare/checkpoint.json")
- code: `workhorse/workhorse/cli/offline.py::print_params` @cd7d6c6c8f77

### refuse-params-yaml-checkpoint

- on: [control](#control)
- trigger: an operator asks for a checkpoint the retired YAML engine wrote
- does:
  - Refuses to print and names the retired engine.
- run: invoke(argv=["control", "status", "--params", "--run", "/tmp/workhorse-book/seeded/yaml-era"])
- verify: stderr(text="error: /tmp/workhorse-book/seeded/yaml-era/checkpoint.json is a checkpoint from the retired YAML engine")
- code: `workhorse/workhorse/cli/offline.py::print_params` @cd7d6c6c8f77

### refuse-unserved-socket

- on: [control](#control)
- trigger: an operator sends a live verb to a run no process serves
- does:
  - Refuses the verb and names the socket it tried.
- run: invoke(argv=["control", "status", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: no run is listening on /tmp/workhorse-book/seeded/finished/control.sock")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### report-finished-run

- on: [control](#control)
- trigger: an operator sends a live verb to a run that already finished
- does:
  - Reports the run's terminal under the refusal.
- run: invoke(argv=["control", "reload", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="  run:     already finished (done) — the request will not be read")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### report-missing-run-record

- on: [control](#control)
- trigger: an operator sends a live verb to a directory with no run.json
- does:
  - Says nothing here records a run starting.
- run: invoke(argv=["control", "questions", "--run", "/tmp/workhorse-book/seeded/bare"])
- verify: stderr(text="  run:     no run.json — nothing here says a run ever started")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### report-unrecorded-pid

- on: [control](#control)
- trigger: an operator stops a run whose run.json records no pid
- does:
  - Says the run is in flight with no pid recorded.
- run: invoke(argv=["control", "stop", "--run", "/tmp/workhorse-book/seeded/in-flight"])
- verify: stderr(text="  run:     in flight, pid not recorded")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### report-gone-pid

- on: [control](#control)
- trigger: an operator answers a gate on a run whose recorded pid is gone
- does:
  - Names the gone pid and says a resume reloads the run.
- run: invoke(argv=["control", "answer", "--text", "yes", "--run", "/tmp/workhorse-book/seeded/stale-pid"])
- verify: stderr(text="  run:     pid 999999 is gone — resume the run and it reloads on entry")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### refuse-switch-cli-unserved

- on: [control](#control)
- trigger: an operator switches the CLI of a run no process serves
- does:
  - Reaches for the socket of the run it names, and the refusal names that socket.
- run: invoke(argv=["control", "switch-cli", "codex", "--run", "/tmp/workhorse-book/seeded/contained"])
- verify: stderr(text="error: no run is listening on /tmp/workhorse-book/seeded/contained/control.sock")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### refuse-no-unfinished-run

- on: [control](#control)
- trigger: an operator names no `--run` and no unfinished run is left
- does:
  - Refuses the verb, names the runs directory and asks for `--run`.
- run: invoke(argv=["control", "status", "--runs-dir", "/tmp/workhorse-book/seeded"])
- verify: stderr(text="error: no unfinished run found under /tmp/workhorse-book/seeded — name one with --run")
- code: `workhorse/workhorse/cli/target.py::resolve_target` @8b8132797882

### refuse-unknown-control-run

- on: [control](#control)
- trigger: an operator names a `--run` that matches no directory
- does:
  - Asks groom, then refuses and says where it looked.
- run: invoke(argv=["control", "status", "--run", "nope", "--runs-dir", "nowhere"])
- verify: stderr(matches="error: no run dir for 'nope' [(]looked under /.*/nowhere[)]")
- code: `workhorse/workhorse/cli/target.py::groom_live_run` @8b8132797882

### refuse-switch-cli-without-name

- on: [control](#control)
- trigger: an operator runs `switch-cli` with no name
- does:
  - Refuses the verb and gives an example with a CLI name.
- run: invoke(argv=["control", "switch-cli", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(matches="error: switch-cli needs the name to switch to, e[.]g[.] .control switch-cli claude.")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### refuse-switch-profile-without-name

- on: [control](#control)
- trigger: an operator runs `switch-profile` with no name
- does:
  - Refuses the verb and gives an example with a profile name.
- run: invoke(argv=["control", "switch-profile", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(matches="error: switch-profile needs the name to switch to, e[.]g[.] .control switch-profile cheap.")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### refuse-name-on-status

- on: [control](#control)
- trigger: an operator puts a name after a verb that takes none
- does:
  - Refuses the verb and quotes the stray name.
- run: invoke(argv=["control", "status", "x", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: status takes no name (got 'x')")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### refuse-text-on-status

- on: [control](#control)
- trigger: an operator passes `--text` to a verb other than `answer`
- does:
  - Refuses the verb and names both answer flags.
- run: invoke(argv=["control", "status", "--text", "hi", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: status takes no --gate or --text")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### refuse-rewind-flag-on-status

- on: [control](#control)
- trigger: an operator passes a rewind flag to another verb
- does:
  - Refuses the verb and names all four rewind flags.
- run: invoke(argv=["control", "status", "--to", "write", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: status takes no --to, --param, --param-from-turn or --keep")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### refuse-params-on-stop

- on: [control](#control)
- trigger: an operator passes `--params` to a verb other than `status`
- does:
  - Refuses the verb and points at `status --params`.
- run: invoke(argv=["control", "stop", "--params", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(matches="error: stop takes no --params [(]it is .status --params.[)]")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### refuse-wait-on-status

- on: [control](#control)
- trigger: an operator passes `--wait` to a verb other than `stop`
- does:
  - Refuses the verb and points at `stop --wait`.
- run: invoke(argv=["control", "status", "--wait", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(matches="error: status takes no --wait [(]it is .stop --wait.[)]")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### refuse-core-on-stop

- on: [control](#control)
- trigger: an operator passes `--core` to `stop`
- does:
  - Refuses the stop and names both reload flags.
- run: invoke(argv=["control", "stop", "--core", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: stop takes no --core or --at-boundary")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### refuse-unknown-action

- on: [control](#control)
- trigger: an operator types an action outside the nine
- does:
  - The argument parser refuses the action and quotes it.
- run: invoke(argv=["control", "pause", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="invalid choice: 'pause'")
- status: 2 on an action outside the nine.
- run: invoke(argv=["control", "pause", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: exit_status(code=2)
- code: `workhorse/workhorse/cli/control.py::add_arguments` @d578cf93b87e

### refuse-core-on-rewind

- on: [control](#control)
- trigger: an operator passes `--core` to `rewind`
- does:
  - Refuses the rewind and names both reload flags.
- run: invoke(argv=["control", "rewind", "--core", "--to", "write", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: rewind takes no --core or --at-boundary")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### refuse-rewind-with-name

- on: [control](#control)
- trigger: an operator puts the state after `rewind` as a name
- does:
  - Refuses the rewind, quotes the name and points at `--to`.
- run: invoke(argv=["control", "rewind", "write", "--run", "/tmp/workhorse-book/seeded/failed-ghost"])
- verify: stderr(text="error: rewind takes no name (got 'write'); the state is --to")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### refuse-rewind-without-to

- on: [control](#control)
- trigger: an operator runs `rewind` with no `--to`
- does:
  - Refuses the rewind and shows the full form.
- run: invoke(argv=["control", "rewind", "--run", "/tmp/workhorse-book/seeded/failed-ghost"])
- verify: stderr(matches="error: rewind needs the state to move to: .control rewind --to STATE.")
- code: `workhorse/workhorse/cli/control.py::run` @d578cf93b87e

### refuse-rewind-finished

- on: [control](#control)
- trigger: an operator rewinds a run that finished with any terminal but fail
- does:
  - Refuses the rewind and names the run and its terminal.
- run: invoke(argv=["control", "rewind", "--to", "write", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: rewind: /tmp/workhorse-book/seeded/finished already finished (done)")
- code: `workhorse/workhorse/cli/offline.py::run_rewind` @cd7d6c6c8f77

### refuse-rewind-without-record

- on: [control](#control)
- trigger: an operator rewinds a directory with no readable run.json
- does:
  - Refuses the rewind and says nothing records a run starting there.
- run: invoke(argv=["control", "rewind", "--to", "write", "--run", "/tmp/workhorse-book/seeded/bare"])
- verify: stderr(text="error: rewind: /tmp/workhorse-book/seeded/bare has no readable run.json — nothing says a run started here")
- code: `workhorse/workhorse/cli/offline.py::run_rewind` @cd7d6c6c8f77

### refuse-param-without-equals

- on: [control](#control)
- trigger: an operator passes a `--param` with no `=`
- does:
  - Refuses the rewind and quotes the value and the form it wants.
- run: invoke(argv=["control", "rewind", "--to", "draft", "--param", "x", "--run", "/tmp/workhorse-book/seeded/failed-ghost"])
- verify: stderr(text="error: --param wants NAME=VALUE, got 'x'")
- code: `workhorse/workhorse/cli/offline.py::run_rewind` @cd7d6c6c8f77

### refuse-rewind-unknown-flow

- on: [control](#control)
- trigger: an operator rewinds a checkpoint whose flow this workflow does not register
- does:
  - Refuses the rewind, leaves the checkpoint unchanged and names its flow.
- run: invoke(argv=["control", "rewind", "--to", "draft", "--run", "/tmp/workhorse-book/seeded/failed-ghost"])
- verify: stderr(text="error: rewind refused, checkpoint unchanged: /tmp/workhorse-book/seeded/failed-ghost/checkpoint.json names flow 'Ghost', which ")
- code: `workhorse/workhorse/cli/offline.py::run_rewind` @cd7d6c6c8f77
- code: `workhorse/workhorse/rewind.py::rewind` @1ed4d1905220

### refuse-rewind-without-checkpoint

- on: [control](#control)
- trigger: an operator rewinds a failed run with no checkpoint
- does:
  - Refuses the rewind and names the checkpoint path it tried.
- run: invoke(argv=["control", "rewind", "--to", "draft", "--run", "/tmp/workhorse-book/seeded/no-line"])
- verify: stderr(text="error: rewind refused, checkpoint unchanged: cannot read checkpoint /tmp/workhorse-book/seeded/no-line/checkpoint.json")
- code: `workhorse/workhorse/cli/offline.py::run_rewind` @cd7d6c6c8f77

### refuse-rewind-yaml-checkpoint

- on: [control](#control)
- trigger: an operator rewinds a checkpoint the retired YAML engine wrote
- does:
  - Refuses the rewind and names the retired engine.
- run: invoke(argv=["control", "rewind", "--to", "draft", "--run", "/tmp/workhorse-book/seeded/yaml-era"])
- verify: stderr(text="error: rewind refused, checkpoint unchanged: /tmp/workhorse-book/seeded/yaml-era/checkpoint.json is a checkpoint from the retired YAML engine")
- code: `workhorse/workhorse/cli/offline.py::run_rewind` @cd7d6c6c8f77

### refuse-resume-finished

- on: [control](#control)
- trigger: an operator resumes a run that finished done
- does:
  - Refuses the resume and names the run and its terminal.
- run: invoke(argv=["control", "resume", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: resume: /tmp/workhorse-book/seeded/finished already finished (done)")
- code: `workhorse/workhorse/cli/offline.py::run_resume` @cd7d6c6c8f77

### refuse-resume-without-record

- on: [control](#control)
- trigger: an operator resumes a directory with no run.json
- does:
  - Refuses the resume and says nothing records a run starting there.
- run: invoke(argv=["control", "resume", "--run", "/tmp/workhorse-book/seeded/bare"])
- verify: stderr(text="error: resume: /tmp/workhorse-book/seeded/bare has no readable run.json — nothing says a run started here")
- status: 1 on every refusal after the arguments parse.
- run: invoke(argv=["control", "resume", "--run", "/tmp/workhorse-book/seeded/bare"])
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/offline.py::run_resume` @cd7d6c6c8f77

### refuse-resume-without-launch

- on: [control](#control)
- trigger: an operator resumes a failed run that has no launch.json
- does:
  - Accepts the failed run, then refuses because it holds no usable launch.json.
- run: invoke(argv=["control", "resume", "--run", "/tmp/workhorse-book/seeded/failed-ghost"])
- verify: stderr(text="error: resume: no usable launch.json in /tmp/workhorse-book/seeded/failed-ghost (")
- code: `workhorse/workhorse/cli/offline.py::run_resume` @cd7d6c6c8f77

### refuse-resume-gone-pid

- on: [control](#control)
- trigger: an operator resumes a run whose recorded pid is gone
- does:
  - Accepts the run, then refuses and names the command to resume it by hand.
- run: invoke(argv=["control", "resume", "--run", "/tmp/workhorse-book/seeded/stale-pid"])
- verify: stderr(matches="run .<workflow> run --resume-run /tmp/workhorse-book/seeded/stale-pid. by hand")
- code: `workhorse/workhorse/cli/offline.py::run_resume` @cd7d6c6c8f77

### refuse-resume-contained

- on: [control](#control)
- trigger: an operator resumes a run launched inside a container
- does:
  - Refuses the resume and says to resume it inside its container.
- run: invoke(argv=["control", "resume", "--run", "/tmp/workhorse-book/seeded/contained"])
- verify: stderr(text="error: resume: launch.json holds container coordinates; resume it inside the container it ran in")
- code: `workhorse/workhorse/cli/offline.py::run_resume` @cd7d6c6c8f77

### refuse-resume-without-line

- on: [control](#control)
- trigger: an operator resumes a run whose launch.json records no resume line
- does:
  - Refuses the resume and names the run's launch.json.
- run: invoke(argv=["control", "resume", "--run", "/tmp/workhorse-book/seeded/no-line"])
- verify: stderr(text="error: resume: launch.json in /tmp/workhorse-book/seeded/no-line records no resume line")
- code: `workhorse/workhorse/cli/offline.py::run_resume` @cd7d6c6c8f77

### read-empty-inbox

- on: [inbox](#inbox)
- trigger: an operator reads a run that has no inbox file
- does:
  - Says the run has no outstanding messages.
- run: invoke(argv=["inbox", "read", "--run", "/tmp/workhorse-book/inbox"])
- verify: stdout(text="no outstanding messages in /tmp/workhorse-book/inbox")
- code: `workhorse/workhorse/inbox.py::outstanding` @e2ad0fc21f23

### read-all-empty-inbox

- on: [inbox](#inbox)
- trigger: an operator reads every message of a run that has no inbox file
- does:
  - Says the run has no messages.
- run: invoke(argv=["inbox", "read", "--all", "--run", "/tmp/workhorse-book/inbox"])
- verify: stdout(text="no messages in /tmp/workhorse-book/inbox")
- code: `workhorse/workhorse/inbox.py::all_messages` @e2ad0fc21f23

### read-all-replied

- on: [inbox](#inbox)
- trigger: an operator reads every message, replied ones included
- does:
  - `read --all` prints a replied message with its reply time.
- run: invoke(argv=["inbox", "read", "--all", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stdout(text="[m2] 2026-01-01T00:00:00+00:00 (replied 2026-01-02T00:00:00+00:00)")
- does:
  - `read` prints the body indented two spaces under its message line.
- run: invoke(argv=["inbox", "read", "--all", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stdout(text="  tests are red")
- does:
  - `read` prints a reply as an arrow line under the body.
- run: invoke(argv=["inbox", "read", "--all", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stdout(text="  -> no")
- code: `workhorse/workhorse/cli/inbox.py::run` @7789b147be16

### refuse-reply-without-text

- on: [inbox](#inbox)
- trigger: an operator replies with an id and no text
- does:
  - Refuses the reply and asks for both an id and text.
- run: invoke(argv=["inbox", "reply", "m1", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stderr(text="error: reply needs an id and text")
- code: `workhorse/workhorse/cli/inbox.py::run` @7789b147be16

### refuse-unknown-message

- on: [inbox](#inbox)
- trigger: an operator replies to an id the inbox lacks
- does:
  - Refuses the reply, leaves the inbox as it was and names the inbox file it read.
- run: invoke(argv=["inbox", "reply", "m9", "hi", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stderr(text="no inbox message with id 'm9' in /tmp/workhorse-book/inbox/answer/inbox.jsonl")
- status: 1 on a refused reply.
- run: invoke(argv=["inbox", "reply", "m9", "hi", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: exit_status(code=1)
- code: `workhorse/workhorse/inbox.py::reply` @e2ad0fc21f23

### refuse-unknown-inbox-run

- on: [inbox](#inbox)
- trigger: an operator names a `--run` that matches no directory
- does:
  - Refuses the read and says where it looked.
- run: invoke(argv=["inbox", "read", "--run", "nope", "--runs-dir", "nowhere"])
- verify: stderr(matches="no run dir for 'nope' [(]looked under /.*/nowhere[)]")
- code: `workhorse/workhorse/cli/target.py::resolve_target` @8b8132797882

### refuse-unknown-inbox-action

- on: [inbox](#inbox)
- trigger: an operator types an action other than read and reply
- does:
  - The argument parser refuses the action and quotes it.
- run: invoke(argv=["inbox", "list", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stderr(text="invalid choice: 'list'")
- status: 2 on an action other than read and reply.
- run: invoke(argv=["inbox", "list", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: exit_status(code=2)
- code: `workhorse/workhorse/cli/inbox.py::add_arguments` @7789b147be16

### read-outstanding

- on: [inbox](#inbox)
- trigger: an operator checks what a run is asking
- does:
  - Prints the one outstanding message and its body.
- run: invoke(argv=["inbox", "read", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stdout(text="  may I push?")
- code: `workhorse/workhorse/inbox.py::outstanding` @e2ad0fc21f23

### reply-to-message

- on: [inbox](#inbox)
- trigger: an operator answers the outstanding message
- does:
  - Records the reply and names the run.
- run: invoke(argv=["inbox", "reply", "m1", "go ahead", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stdout(text="replied to [m1] in /tmp/workhorse-book/inbox/answer")
- code: `workhorse/workhorse/inbox.py::reply` @e2ad0fc21f23

### read-all-messages

- on: [inbox](#inbox)
- trigger: an operator reviews every message after replying
- does:
  - Prints the new reply under the message it answers.
- run: invoke(argv=["inbox", "read", "--all", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stdout(text="  -> go ahead")
- code: `workhorse/workhorse/inbox.py::all_messages` @e2ad0fc21f23

### replace-reply

- on: [inbox](#inbox)
- trigger: an operator replies again to a message that already has a reply
- does:
  - Replaces the reply and names the run.
- run: invoke(argv=["inbox", "reply", "m2", "later", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stdout(text="replied to [m2] in /tmp/workhorse-book/inbox/answer")
- code: `workhorse/workhorse/inbox.py::reply` @e2ad0fc21f23

### read-replaced-reply

- on: [inbox](#inbox)
- trigger: an operator reads every message after replacing a reply
- does:
  - Prints the replaced reply in place of the old one.
- run: invoke(argv=["inbox", "read", "--all", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stdout(text="  -> later")
- code: `workhorse/workhorse/inbox.py::all_messages` @e2ad0fc21f23

### refuse-replay-without-run

- on: [replay](#replay)
- trigger: an author names a turn and no `--run`
- does:
  - The argument parser refuses the replay and names the missing flag.
- run: invoke(argv=["replay", "000-00001-x"])
- verify: stderr(text="the following arguments are required: --run")
- status: 2 without `--run`.
- run: invoke(argv=["replay", "000-00001-x"])
- verify: exit_status(code=2)
- code: `workhorse/workhorse/cli/replay.py::add_arguments` @d6c1e9fdd435

### refuse-replay-unknown-run

- on: [replay](#replay)
- trigger: an author names a `--run` that matches no directory
- does:
  - Refuses the replay without asking groom, and asks for the run's directory path.
- run: invoke(argv=["replay", "000-00001-x", "--run", "nope", "--runs-dir", "nowhere"])
- verify: stderr(matches="error: no run dir for 'nope' under /.*/nowhere; pass the run's directory path")
- code: `workhorse/workhorse/cli/replay.py::run` @d6c1e9fdd435

### refuse-missing-turn

- on: [replay](#replay)
- trigger: an author names a turn with no turn.json
- does:
  - Refuses the replay and names the missing turn.json.
- run: invoke(argv=["replay", "000-09999-none", "--run", "/tmp/workhorse-book/seeded/replay-run"])
- verify: stderr(text="error: /tmp/workhorse-book/seeded/replay-run/turns/000-09999-none/turn.json does not exist; name a directory under the run's turns/ that holds a turn.json")
- code: `workhorse/workhorse/cli/replay.py::run` @d6c1e9fdd435

### refuse-bad-turn-record

- on: [replay](#replay)
- trigger: an author names a turn whose turn.json does not validate
- does:
  - Refuses the replay and says the file is not a turn record.
- run: invoke(argv=["replay", "000-00003-bad", "--run", "/tmp/workhorse-book/seeded/replay-run"])
- verify: stderr(text="error: /tmp/workhorse-book/seeded/replay-run/turns/000-00003-bad/turn.json is not a turn record: ")
- status: 1 on a turn record that does not validate.
- run: invoke(argv=["replay", "000-00003-bad", "--run", "/tmp/workhorse-book/seeded/replay-run"])
- verify: exit_status(code=1)
- code: `workhorse/workhorse/cli/replay.py::run` @d6c1e9fdd435

### refuse-missing-prompt

- on: [replay](#replay)
- trigger: an author replays a turn that recorded no prompt.md, with no `--prompt`
- does:
  - Refuses the replay and asks for `--prompt`.
- run: invoke(argv=["replay", "000-00002-noprompt", "--run", "/tmp/workhorse-book/seeded/replay-run"])
- verify: stderr(text="error: /tmp/workhorse-book/seeded/replay-run/turns/000-00002-noprompt/prompt.md does not exist; pass --prompt with the prompt file to send")
- code: `workhorse/workhorse/cli/replay.py::run` @d6c1e9fdd435

### refuse-missing-variant

- on: [replay](#replay)
- trigger: an author names a `--prompt` that is no file
- does:
  - Refuses the replay and names the path as typed.
- run: invoke(argv=["replay", "000-00001-x", "--run", "/tmp/workhorse-book/seeded/replay-run", "--prompt", "nowhere.md"])
- verify: stderr(text="error: nowhere.md does not exist; pass --prompt with the prompt file to send")
- code: `workhorse/workhorse/cli/replay.py::run` @d6c1e9fdd435

### refuse-zero-repeat

- on: [replay](#replay)
- trigger: an author passes `--repeat` below 1
- does:
  - Refuses the replay and says a replay runs at least once.
- run: invoke(argv=["replay", "000-00004-moved", "--run", "/tmp/workhorse-book/seeded/replay-run", "--repeat", "0"])
- verify: stderr(text="error: --repeat 0: a replay runs the turn at least once")
- code: `workhorse/workhorse/cli/replay.py::run` @d6c1e9fdd435

### refuse-unsizable-variant

- on: [replay](#replay)
- trigger: an author sends a variant for a turn that recorded no prompt, with no limit
- does:
  - Refuses the replay because nothing sizes the variant, and asks for `--max-prompt-chars`.
- run: invoke(argv=["replay", "000-00002-noprompt", "--run", "/tmp/workhorse-book/seeded/replay-run", "--prompt", "/tmp/workhorse-book/seeded/v10.txt"])
- verify: stderr(text="error: /tmp/workhorse-book/seeded/replay-run/turns/000-00002-noprompt/prompt.md does not exist to size a variant against; pass --max-prompt-chars")
- code: `workhorse/workhorse/cli/replay.py::run` @d6c1e9fdd435

### refuse-oversized-variant

- on: [replay](#replay)
- trigger: an author sends a variant one character over twice the recorded prompt
- does:
  - Refuses the replay and states both lengths and the default limit's source.
- run: invoke(argv=["replay", "000-00004-moved", "--run", "/tmp/workhorse-book/seeded/replay-run", "--prompt", "/tmp/workhorse-book/seeded/v11.txt"])
- verify: stderr(text="error: /tmp/workhorse-book/seeded/v11.txt is 11 characters, over the 10 allowed (2 times the recorded 5-character prompt). Trim the variant, or raise the limit with --max-prompt-chars.")
- code: `workhorse/workhorse/cli/replay.py::run` @d6c1e9fdd435

### refuse-variant-over-limit

- on: [replay](#replay)
- trigger: an author sets `--max-prompt-chars` below the variant's length
- does:
  - Refuses the replay and names `--max-prompt-chars` as the limit's source.
- run: invoke(argv=["replay", "000-00004-moved", "--run", "/tmp/workhorse-book/seeded/replay-run", "--prompt", "/tmp/workhorse-book/seeded/v11.txt", "--max-prompt-chars", "10"])
- verify: stderr(text="is 11 characters, over the 10 allowed (--max-prompt-chars).")
- code: `workhorse/workhorse/cli/replay.py::run` @d6c1e9fdd435

### accept-variant-at-limit

- on: [replay](#replay)
- trigger: an author sets `--max-prompt-chars` to the variant's length
- does:
  - The variant passes the size check, and the replay then stops at the tree check.
- run: invoke(argv=["replay", "000-00004-moved", "--run", "/tmp/workhorse-book/seeded/replay-run", "--prompt", "/tmp/workhorse-book/seeded/v11.txt", "--max-prompt-chars", "11"])
- verify: stderr(text="seeded/bare is at no commit, not the turn's start")
- code: `workhorse/workhorse/cli/replay.py::run` @d6c1e9fdd435

### refuse-moved-replay

- on: [replay](#replay)
- trigger: an author replays a turn with a variant at exactly twice the recorded prompt, on a checkout that moved on
- does:
  - The variant passes the size check, and the replay refuses to reset the moved tree and names both heads.
- run: invoke(argv=["replay", "000-00004-moved", "--run", "/tmp/workhorse-book/seeded/replay-run", "--prompt", "/tmp/workhorse-book/seeded/v10.txt"])
- verify: stderr(text="is at no commit, not the turn's start deadbeefdead, and a replay resets its branch")
- code: `workhorse/workhorse/cli/replay.py::replay_turn` @d6c1e9fdd435
