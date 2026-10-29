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
- code: `workhorse/workhorse/cli/__init__.py::main` @433998fdbc03
- detail: [CLI dispatch](concepts/cli-dispatch.md)

## Commands

### run

- usage: workhorse-loop-runner [run] [FLOW] [--cli NAME | --profile NAME] [--config PATH] [--workspace NAME] [--params JSON] [--params-file PATH] [--context-file PATH] [--runs-dir DIR] [--run-id ID] [--dry-run] [--worktree [--worktree-branch NAME] [--worktree-base REF]] [--resume-run PATH_OR_RUN_ID | --resume-latest | --no-cache]
- flags:
  - `--cli NAME` picks the agent CLI backend for the whole run. It overrides `AGENT_CLI`, which overrides the config's `default_cli`. The default is claude.
  - `--profile NAME` resolves models from `[profiles.NAME]` in the config, and the profile names its own CLI. A profile whose key matches its own `cli` is auto-selected on a fresh run — whether or not `--cli` names that same CLI — when neither `--profile` nor a resumed run's recorded profile already picked one.
  - `--config PATH` reads this config file and nothing else. It overrides `$STABLEMATE_CONFIG`, which overrides `$WORKHORSE_CONFIG`.
  - `--workspace NAME` runs across the named `[workspaces]` entry of the home config: it initialises the artifacts repo and adds `workspace` to the params the workflow receives. A bad name refuses before the run opens its run directory. A resume with no `--workspace` restores the workspace the run recorded.
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
- code: `workhorse/workhorse/cli/run.py::add_arguments` @a07c73905748
- code: `workhorse/workhorse/cli/run.py::run` @0c5d4cc9ba6f
- code: `workhorse/workhorse/cli/run.py::invocation` @d4edb02a5483
- code: `workhorse/workhorse/cli/run.py::apply_config_path` @b3a5e8f90bc8
- code: `workhorse/workhorse/cli/run.py::library_dirs` @11f6ab8973fa
- code: `workhorse/workhorse/cli/params.py::load_params` @7d465d71bf99
- code: `workhorse/workhorse/manifest.py::load_context_manifest` @46f9529e2243
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
- code: `workhorse/workhorse/cli/dot.py::add_arguments` @5fa14abc4ae0
- code: `workhorse/workhorse/cli/dot.py::run` @536b69b94304
- code: `workhorse/workhorse/pyflow/dot.py::to_dot` @0efe335f130a
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
  - `ACTION` is one of reload, stop, status, questions, answer, switch-cli, switch-profile, rewind and resume. The first seven talk to a live run over its control socket. `rewind` and `resume` act on a stopped run. `resume` launches the run in its own transient systemd user scope when `systemd-run` and a user manager are available, so the resumed run survives the caller exiting. Without them it launches the run as a plain detached process.
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
- code: `workhorse/workhorse/cli/control.py::add_arguments` @c48985fbd896
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5
- code: `workhorse/workhorse/cli/offline.py::run_rewind` @b874da1d8083
- code: `workhorse/workhorse/cli/offline.py::run_resume` @6f1f9d97109f
- code: `workhorse/workhorse/cli/offline.py::print_params` @73f461e23864
- code: `workhorse/workhorse/cli/target.py::resolve_target` @3cbe501f15ad
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
- code: `workhorse/workhorse/cli/inbox.py::add_arguments` @2ffa4ea9053f
- code: `workhorse/workhorse/cli/inbox.py::run` @df83964543f3
- code: `workhorse/workhorse/inbox.py::reply` @800471b434e8
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
- code: `workhorse/workhorse/cli/replay.py::add_arguments` @88001e926f95
- code: `workhorse/workhorse/cli/replay.py::run` @6cad5c38a342
- code: `workhorse/workhorse/cli/replay.py::replay_turn` @9f271663abd7
- code: `workhorse/workhorse/cli/replay.py::Replay` @c134cc29f129
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
- code: `workhorse/workhorse/cli/version.py::run` @6d05cf7468f6
- code: `workhorse/workhorse/cli/version.py::add_arguments` @0f815d91bfab
- detail: [packaging](concepts/packaging.md)

## Invocations

### show-top-level-help

- on: [run](#run)
- trigger: the first token is `-h` or `--help`
- does:
  - Prints the top-level help, which lists every command.
- run: invoke(argv=["--help"])
- verify: stdout(text="{run,dot,control,inbox,replay,version}")
- code: `workhorse/workhorse/cli/__init__.py::main` @433998fdbc03
- code: `workhorse/workhorse/cli/parser.py::build_parser` @e74ae81a725b
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
- code: `workhorse/workhorse/cli/__init__.py::main` @433998fdbc03

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
- code: `workhorse/workhorse/cli/run.py::run` @0c5d4cc9ba6f

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
- code: `workhorse/workhorse/cli/run.py::apply_config_path` @b3a5e8f90bc8

### refuse-unknown-resume-run

- on: [run](#run)
- trigger: an author resumes a run id no directory matches
- does:
  - Refuses the resume and reports where it looked.
- run: invoke(argv=["run", "--resume-run", "nope", "--runs-dir", "nowhere"])
- verify: stderr(matches="error: resume run dir not found for 'nope' [(]looked under /.*/nowhere[)]")
- code: `workhorse/workhorse/rundir.py::resolve_run_dir` @71a8debb2472

### refuse-no-resumable-run

- on: [run](#run)
- trigger: an author asks for the newest unfinished run
- does:
  - Skips every directory with no checkpoint and every finished run, then names the runs directory when none is left.
- run: invoke(argv=["run", "--resume-latest", "--runs-dir", "/tmp/workhorse-book/seeded"])
- verify: stderr(text="error: no resumable run found under /tmp/workhorse-book/seeded")
- code: `workhorse/workhorse/rundir.py::find_latest_resumable` @170e39ba7432

### refuse-two-resume-flags

- on: [run](#run)
- trigger: an author passes two of the resume flags
- does:
  - The argument parser refuses the second flag and names the first one it clashes with.
- run: invoke(argv=["run", "--resume-latest", "--resume-run", "nope"])
- verify: stderr(text="error: argument --resume-run: not allowed with argument --resume-latest")
- code: `workhorse/workhorse/cli/run.py::add_arguments` @a07c73905748

### refuse-unknown-profile

- on: [run](#run)
- trigger: an author names a profile the config does not declare
- does:
  - Refuses the launch and lists the known profiles in sorted order.
- run: invoke(argv=["run", "--profile", "ghost", "--config", "/tmp/workhorse-book/seeded/config.toml"])
- verify: stderr(text="error: unknown profile 'ghost' in /tmp/workhorse-book/seeded/config.toml (known: bare, cheap, odd)")
- code: `workhorse/workhorse/cli/run.py::run` @0c5d4cc9ba6f
- code: `workhorse/workhorse/profile.py::select_backend` @ec98391fc4ca
- code: `workhorse/workhorse/_vendor/stablemate_core/profiles.py::select_profile` @9852a73097b9
- code: `workhorse/workhorse/_vendor/stablemate_core/config.py::load_config` @d0ff862932b8
- code: `workhorse/workhorse/_vendor/stablemate_core/discovery.py::base_library_dir` @004b46181627
- code: `workhorse/workhorse/packaged.py::PackagedWorkflowError` @1e6b03ad1f32
- code: `workhorse/workhorse/runner/backends/__init__.py::AgentBackend` @a7fd563f47f8
- code: `workhorse/workhorse/runner/backends/registry.py::get_backend` @97728ec5a6f0
- code: `workhorse/workhorse/runner/backends/claude.py::ClaudeBackend` @c74af8345ba8
- code: `workhorse/workhorse/runner/backends/codex.py::CodexBackend` @8c2758a2cf46
- code: `workhorse/workhorse/runner/backends/cline.py::ClineBackend` @833b0556208c
- code: `workhorse/workhorse/runner/backends/copilot.py::CopilotBackend` @3c59f904ca67
- code: `workhorse/workhorse/runner/backends/opencode.py::OpenCodeBackend` @1e27e752740d
- code: `workhorse/workhorse/runner/backends/delegates.py::Delegate` @234ee3903391
- code: `workhorse/workhorse/runner/backends/jsonl.py::JsonlBackend` @5cb576f3f346
- code: `workhorse/workhorse/runner/backends/turn.py::TurnState` @375ce5ec8206
- code: `workhorse/workhorse/runner/backends/codex_guard.py::Policy` @736e50949720
- code: `workhorse/workhorse/runner/backends/codex_shell.py::shell_denial` @3366bb96722b

### refuse-profile-without-cli

- on: [run](#run)
- trigger: an author names a profile with no `cli` field
- does:
  - Refuses the launch and says every profile must declare its CLI.
- run: invoke(argv=["run", "--profile", "bare", "--config", "/tmp/workhorse-book/seeded/config.toml"])
- verify: stderr(text="error: [profiles.bare] has no cli field — every profile must declare the CLI it runs under.")
- code: `workhorse/workhorse/cli/run.py::run` @0c5d4cc9ba6f

### refuse-undrivable-profile

- on: [run](#run)
- trigger: an author names a profile whose CLI this run cannot drive
- does:
  - Refuses the launch and lists the CLIs the run can drive.
- run: invoke(argv=["run", "--profile", "odd", "--config", "/tmp/workhorse-book/seeded/config.toml"])
- verify: stderr(text="error: profile 'odd' declares cli = 'nope' (in /tmp/workhorse-book/seeded/config.toml), and this run can drive only claude, cline, codex, copilot, opencode")
- code: `workhorse/workhorse/cli/run.py::run` @0c5d4cc9ba6f

### refuse-unreadable-params-file

- on: [run](#run)
- trigger: an author names a `--params-file` that cannot be read
- does:
  - Refuses the launch before any JSON is parsed, and names the file as typed.
- run: invoke(argv=["run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--params-file", "nowhere.json"])
- verify: stderr(text="error: cannot read --params-file nowhere.json: ")
- code: `workhorse/workhorse/cli/params.py::load_params` @7d465d71bf99

### refuse-params-not-json

- on: [run](#run)
- trigger: an author passes inline `--params` that is not JSON
- does:
  - Refuses the launch and names the inline flag.
- run: invoke(argv=["run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--params", "{"])
- verify: stderr(text="error: --params is not valid JSON: ")
- code: `workhorse/workhorse/cli/params.py::load_params` @7d465d71bf99

### refuse-params-file-not-object

- on: [run](#run)
- trigger: an author's `--params-file` holds JSON that is not an object
- does:
  - Refuses the launch, names the file flag and asks for a key-to-value map.
- run: invoke(argv=["run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--params-file", "/tmp/workhorse-book/seeded/params-list.json"])
- verify: stderr(text="error: --params-file must be a JSON object (key→value map)")
- code: `workhorse/workhorse/cli/params.py::load_params` @7d465d71bf99

### refuse-params-not-object

- on: [run](#run)
- trigger: an author's inline `--params` holds a JSON list
- does:
  - Refuses the launch, names the inline flag and asks for a key-to-value map.
- run: invoke(argv=["run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--params", "[1]"])
- verify: stderr(text="error: --params must be a JSON object (key→value map)")
- code: `workhorse/workhorse/cli/params.py::load_params` @7d465d71bf99

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
- code: `workhorse/workhorse/manifest.py::load_context_manifest` @46f9529e2243

### refuse-context-not-json

- on: [run](#run)
- trigger: an author's context manifest is not JSON
- does:
  - Refuses the launch and names the manifest it could not read.
- run: invoke(argv=["run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--context-file", "/tmp/workhorse-book/seeded/bad-context.json"])
- verify: stderr(text="error: cannot read context manifest /tmp/workhorse-book/seeded/bad-context.json: ")
- code: `workhorse/workhorse/manifest.py::load_context_manifest` @46f9529e2243

### refuse-context-not-object

- on: [run](#run)
- trigger: an author's context manifest holds a JSON list
- does:
  - Refuses the launch and asks for a JSON object.
- run: invoke(argv=["run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--context-file", "/tmp/workhorse-book/seeded/list-context.json"])
- verify: stderr(text="error: context manifest /tmp/workhorse-book/seeded/list-context.json must be a JSON object")
- code: `workhorse/workhorse/manifest.py::load_context_manifest` @46f9529e2243

### dry-run-workflow

- on: [run](#run)
- trigger: an author checks the workflow binds before an unattended run
- does:
  - Stubs every node and names the run directory it wrote.
- run: invoke(argv=["run", "--dry-run", "--cli", "claude", "--config", "/tmp/workhorse-book/seeded/config.toml", "--run-id", "walk"])
- verify: stdout(matches="artifacts in /.*/[.]agents/runs/")
- code: `workhorse/workhorse/pyflow/run.py::run_pyflow` @c392763d851e
- code: `workhorse/workhorse/artifacts.py::ArtifactWriter` @a21146f24b40
- code: `workhorse/workhorse/logsetup.py::setup` @b4b552e503f9
- code: `workhorse/workhorse/otel.py::install` @0cfd934d680b
- code: `workhorse/workhorse/gitstate.py::bind` @0e2fd532fd87
- code: `workhorse/workhorse/reload.py::boundary_requested` @42374597c910
- code: `workhorse/workhorse/references.py::missing_references` @8e2d760ce437
- code: `workhorse/workhorse/templates.py::turn_catalog` @15a10fdae8c0
- code: `workhorse/workhorse/turnkey.py::VisitKey` @936605424d96
- code: `workhorse/workhorse/pyflow/driver.py::drive` @ccc7b24c9a3a
- code: `workhorse/workhorse/pyflow/transitions.py::Continue` @577c98d0961e
- code: `workhorse/workhorse/pyflow/activity.py::ActivityLog` @a9aa13a69f9c
- code: `workhorse/workhorse/pyflow/engine.py::Engine` @68b5b8ddb148
- code: `workhorse/workhorse/pyflow/registry.py::Registry` @cf2a43882827
- code: `workhorse/workhorse/pyflow/names.py::NameIndex` @23d376d3a1c1
- code: `workhorse/workhorse/pyflow/blueprint.py::Blueprint` @4b62298ba989
- code: `workhorse/workhorse/pyflow/preflight.py::preflight` @32e23e80439c
- code: `workhorse/workhorse/pyflow/graph.py::registry_graphs` @114afbfbbebb
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow` @05b2b95a00a9
- code: `workhorse/workhorse/control.py::NULL_CHANNEL` @52683677757e
- code: `workhorse/workhorse/config_run.py::RunConfig` @49245badf6b8
- code: `workhorse/workhorse/runner/backends/null.py::NullBackend` @fa155316e8c8
- code: `workhorse/workhorse/runner/ladder.py::AgentRunner` @68bb9bc9e89e
- code: `workhorse/workhorse/runner/spec.py::AgentNode` @bf793637deea
- code: `workhorse/workhorse/context.py::WorkflowContext` @b0093881caa5
- code: `workhorse/workhorse/runner/caps.py::cap_delay_seconds` @a95194550dc0
- code: `workhorse/workhorse/runner/extract.py::extract_outputs` @cc7640499a1d
- code: `workhorse/workhorse/runner/reframe.py::retry_prompt` @b002d345d57b
- code: `workhorse/workhorse/runner/turn_record.py::RenderedTurn` @93da4065b3f7
- code: `workhorse/workhorse/runner/waits.py::RecoveryWaitBudget` @08db08fb9e5c
- code: `workhorse/workhorse/runner/redact.py::SecretRedactor` @ac896c782f16
- code: `workhorse/workhorse/runner/transcript.py::bind` @6b33cd59c7dc
- code: `workhorse/workhorse/runner/worktree_guard.py::install` @1e8de6bd099b
- code: `workhorse/workhorse/runner/process.py::ProcessSupervisor` @a7f7baae77d8
- code: `workhorse/workhorse/runner/acp.py::TranscriptMapper` @a4d4e204f664
- code: `workhorse/workhorse/runner/usage.py::TurnUsage` @3a262095df5b
- code: `workhorse/workhorse/runner/failure.py::BackendInvocationError` @be991f27bfcf
- code: `workhorse/workhorse/sessions.py::slug` @c193ee0fdc62
- code: `workhorse/workhorse/_vendor/stablemate_core/clock.py::Clock` @1fcd1289ac40
- code: `workhorse/workhorse/pyflow/errors.py::PyflowError` @ac44590acb4a
- code: `workhorse/workhorse/pyflow/park.py::ask` @285d89c6448c
- code: `workhorse/workhorse/pyflow/prompts.py::PromptResolver` @d567117240fa
- code: `workhorse/workhorse/pyflow/replies.py::declared_reply` @613af8c064d8
- code: `workhorse/workhorse/pyflow/worktree.py::WorktreeError` @5f2d3d677fd8
- code: `workhorse/workhorse/worklist.py::WorkList` @f25a571c8e32
- code: `workhorse/workhorse/_vendor/stablemate_core/skill_refs.py::SkillCatalog` @f39221fd7e1a

### name-the-graph

- on: [dot](#dot)
- trigger: an author gives the graph a name of their own
- does:
  - `--name` replaces every character outside letters, digits and underscore with an underscore.
- run: invoke(argv=["dot", "--name", "my graph-1"])
- verify: stdout(text="digraph my_graph_1 {")
- code: `workhorse/workhorse/pyflow/dot.py::to_dot` @0efe335f130a

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
- code: `workhorse/workhorse/cli/dot.py::run` @536b69b94304

### write-dot-long-flag

- on: [dot](#dot)
- trigger: an author spells the output flag `--output`
- does:
  - The written file holds the DOT text with its legend.
- run: invoke(argv=["dot", "--output", "graph2.dot"])
- verify: contents(subject="graph2.dot", text="subgraph cluster_legend {")
- code: `workhorse/workhorse/cli/dot.py::add_arguments` @5fa14abc4ae0

### print-version

- on: [version](#version)
- trigger: an operator asks which engine release a workflow script runs
- does:
  - Prints the version on one line.
- run: invoke(argv=["version"])
- verify: stdout(matches="^[0-9]+[.][0-9.]+[a-z0-9.+-]*$")
- code: `workhorse/workhorse/cli/version.py::run` @6d05cf7468f6

### print-checkpoint-params

- on: [control](#control)
- trigger: an operator reads where a stopped run would resume
- does:
  - prints the checkpoint as JSON with no gate it waits on
- run: invoke(argv=["control", "status", "--params", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stdout(matches="waiting_on.: null")
- verify: stdout(matches="(?s)^(?!.*worktree).*$")
- code: `workhorse/workhorse/cli/offline.py::print_params` @73f461e23864

### print-worktree-params

- on: [control](#control)
- trigger: an operator reads the checkpoint of a run dispatched into a worktree
- does:
  - adds a `worktree` key (`path`, `branch`, `base`, `outcome`) when the run's `run.json` records a worktree it was dispatched into; omits the key for a run with no worktree
- run: invoke(argv=["control", "status", "--params", "--run", "/tmp/workhorse-book/seeded/worktree-run"])
- verify: stdout(text="\"worktree\": {\n    \"base\": \"main\",\n    \"branch\": \"feature-x\",\n    \"outcome\": null,\n    \"path\": \"/tmp/workhorse-book/seeded/worktree-run/wt\"\n  }")
- code: `workhorse/workhorse/cli/offline.py::print_params` @73f461e23864
- code: `workhorse/workhorse/cli/offline.py::_worktree` @93fd6528bd6d

### refuse-params-without-checkpoint

- on: [control](#control)
- trigger: an operator asks for the checkpoint of a directory that has none
- does:
  - Refuses to print and names the checkpoint path it tried.
- run: invoke(argv=["control", "status", "--params", "--run", "/tmp/workhorse-book/seeded/bare"])
- verify: stderr(text="error: cannot read checkpoint /tmp/workhorse-book/seeded/bare/checkpoint.json")
- code: `workhorse/workhorse/cli/offline.py::print_params` @73f461e23864

### refuse-params-yaml-checkpoint

- on: [control](#control)
- trigger: an operator asks for a checkpoint the retired YAML engine wrote
- does:
  - Refuses to print and names the retired engine.
- run: invoke(argv=["control", "status", "--params", "--run", "/tmp/workhorse-book/seeded/yaml-era"])
- verify: stderr(text="error: /tmp/workhorse-book/seeded/yaml-era/checkpoint.json is a checkpoint from the retired YAML engine")
- code: `workhorse/workhorse/cli/offline.py::print_params` @73f461e23864

### refuse-unserved-socket

- on: [control](#control)
- trigger: an operator sends a live verb to a run no process serves
- does:
  - Refuses the verb and names the socket it tried.
- run: invoke(argv=["control", "status", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: no run is listening on /tmp/workhorse-book/seeded/finished/control.sock")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### report-finished-run

- on: [control](#control)
- trigger: an operator sends a live verb to a run that already finished
- does:
  - Reports the run's terminal under the refusal.
- run: invoke(argv=["control", "reload", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="  run:     already finished (done) — the request will not be read")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### report-missing-run-record

- on: [control](#control)
- trigger: an operator sends a live verb to a directory with no run.json
- does:
  - Says nothing here records a run starting.
- run: invoke(argv=["control", "questions", "--run", "/tmp/workhorse-book/seeded/bare"])
- verify: stderr(text="  run:     no run.json — nothing here says a run ever started")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### report-unrecorded-pid

- on: [control](#control)
- trigger: an operator stops a run whose run.json records no pid
- does:
  - Says the run is in flight with no pid recorded.
- run: invoke(argv=["control", "stop", "--run", "/tmp/workhorse-book/seeded/in-flight"])
- verify: stderr(text="  run:     in flight, pid not recorded")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### report-gone-pid

- on: [control](#control)
- trigger: an operator answers a gate on a run whose recorded pid is gone
- does:
  - Names the gone pid and says a resume reloads the run.
- run: invoke(argv=["control", "answer", "--text", "yes", "--run", "/tmp/workhorse-book/seeded/stale-pid"])
- verify: stderr(text="  run:     pid 999999 is gone — resume the run and it reloads on entry")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### refuse-switch-cli-unserved

- on: [control](#control)
- trigger: an operator switches the CLI of a run no process serves
- does:
  - Reaches for the socket of the run it names, and the refusal names that socket.
- run: invoke(argv=["control", "switch-cli", "codex", "--run", "/tmp/workhorse-book/seeded/contained"])
- verify: stderr(text="error: no run is listening on /tmp/workhorse-book/seeded/contained/control.sock")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### refuse-no-unfinished-run

- on: [control](#control)
- trigger: an operator names no `--run` and no unfinished run is left
- does:
  - Refuses the verb, names the runs directory and asks for `--run`.
- run: invoke(argv=["control", "status", "--runs-dir", "/tmp/workhorse-book/seeded"])
- verify: stderr(text="error: no unfinished run found under /tmp/workhorse-book/seeded — name one with --run")
- code: `workhorse/workhorse/cli/target.py::resolve_target` @3cbe501f15ad

### refuse-unknown-control-run

- on: [control](#control)
- trigger: an operator names a `--run` that matches no directory
- does:
  - Asks groom, then refuses and says where it looked.
- run: invoke(argv=["control", "status", "--run", "nope", "--runs-dir", "nowhere"])
- verify: stderr(matches="error: no run dir for 'nope' [(]looked under /.*/nowhere[)]")
- code: `workhorse/workhorse/cli/target.py::groom_live_run` @9eedeca9ae29

### refuse-switch-cli-without-name

- on: [control](#control)
- trigger: an operator runs `switch-cli` with no name
- does:
  - Refuses the verb and gives an example with a CLI name.
- run: invoke(argv=["control", "switch-cli", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(matches="error: switch-cli needs the name to switch to, e[.]g[.] .control switch-cli claude.")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### refuse-switch-profile-without-name

- on: [control](#control)
- trigger: an operator runs `switch-profile` with no name
- does:
  - Refuses the verb and gives an example with a profile name.
- run: invoke(argv=["control", "switch-profile", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(matches="error: switch-profile needs the name to switch to, e[.]g[.] .control switch-profile cheap.")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### refuse-name-on-status

- on: [control](#control)
- trigger: an operator puts a name after a verb that takes none
- does:
  - Refuses the verb and quotes the stray name.
- run: invoke(argv=["control", "status", "x", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: status takes no name (got 'x')")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### refuse-text-on-status

- on: [control](#control)
- trigger: an operator passes `--text` to a verb other than `answer`
- does:
  - Refuses the verb and names both answer flags.
- run: invoke(argv=["control", "status", "--text", "hi", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: status takes no --gate or --text")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### refuse-rewind-flag-on-status

- on: [control](#control)
- trigger: an operator passes a rewind flag to another verb
- does:
  - Refuses the verb and names all four rewind flags.
- run: invoke(argv=["control", "status", "--to", "write", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: status takes no --to, --param, --param-from-turn or --keep")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### refuse-params-on-stop

- on: [control](#control)
- trigger: an operator passes `--params` to a verb other than `status`
- does:
  - Refuses the verb and points at `status --params`.
- run: invoke(argv=["control", "stop", "--params", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(matches="error: stop takes no --params [(]it is .status --params.[)]")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### refuse-wait-on-status

- on: [control](#control)
- trigger: an operator passes `--wait` to a verb other than `stop`
- does:
  - Refuses the verb and points at `stop --wait`.
- run: invoke(argv=["control", "status", "--wait", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(matches="error: status takes no --wait [(]it is .stop --wait.[)]")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### refuse-core-on-stop

- on: [control](#control)
- trigger: an operator passes `--core` to `stop`
- does:
  - Refuses the stop and names both reload flags.
- run: invoke(argv=["control", "stop", "--core", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: stop takes no --core or --at-boundary")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

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
- code: `workhorse/workhorse/cli/control.py::add_arguments` @c48985fbd896

### refuse-core-on-rewind

- on: [control](#control)
- trigger: an operator passes `--core` to `rewind`
- does:
  - Refuses the rewind and names both reload flags.
- run: invoke(argv=["control", "rewind", "--core", "--to", "write", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: rewind takes no --core or --at-boundary")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### refuse-rewind-with-name

- on: [control](#control)
- trigger: an operator puts the state after `rewind` as a name
- does:
  - Refuses the rewind, quotes the name and points at `--to`.
- run: invoke(argv=["control", "rewind", "write", "--run", "/tmp/workhorse-book/seeded/failed-ghost"])
- verify: stderr(text="error: rewind takes no name (got 'write'); the state is --to")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### refuse-rewind-without-to

- on: [control](#control)
- trigger: an operator runs `rewind` with no `--to`
- does:
  - Refuses the rewind and shows the full form.
- run: invoke(argv=["control", "rewind", "--run", "/tmp/workhorse-book/seeded/failed-ghost"])
- verify: stderr(matches="error: rewind needs the state to move to: .control rewind --to STATE.")
- code: `workhorse/workhorse/cli/control.py::run` @29e07dfdf1d5

### refuse-rewind-finished

- on: [control](#control)
- trigger: an operator rewinds a run that finished with any terminal but fail
- does:
  - Refuses the rewind and names the run and its terminal.
- run: invoke(argv=["control", "rewind", "--to", "write", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: rewind: /tmp/workhorse-book/seeded/finished already finished (done)")
- code: `workhorse/workhorse/cli/offline.py::run_rewind` @b874da1d8083

### refuse-rewind-without-record

- on: [control](#control)
- trigger: an operator rewinds a directory with no readable run.json
- does:
  - Refuses the rewind and says nothing records a run starting there.
- run: invoke(argv=["control", "rewind", "--to", "write", "--run", "/tmp/workhorse-book/seeded/bare"])
- verify: stderr(text="error: rewind: /tmp/workhorse-book/seeded/bare has no readable run.json — nothing says a run started here")
- code: `workhorse/workhorse/cli/offline.py::run_rewind` @b874da1d8083

### refuse-param-without-equals

- on: [control](#control)
- trigger: an operator passes a `--param` with no `=`
- does:
  - Refuses the rewind and quotes the value and the form it wants.
- run: invoke(argv=["control", "rewind", "--to", "draft", "--param", "x", "--run", "/tmp/workhorse-book/seeded/failed-ghost"])
- verify: stderr(text="error: --param wants NAME=VALUE, got 'x'")
- code: `workhorse/workhorse/cli/offline.py::run_rewind` @b874da1d8083

### refuse-rewind-unknown-flow

- on: [control](#control)
- trigger: an operator rewinds a checkpoint whose flow this workflow does not register
- does:
  - Refuses the rewind, leaves the checkpoint unchanged and names its flow.
- run: invoke(argv=["control", "rewind", "--to", "draft", "--run", "/tmp/workhorse-book/seeded/failed-ghost"])
- verify: stderr(text="error: rewind refused, checkpoint unchanged: /tmp/workhorse-book/seeded/failed-ghost/checkpoint.json names flow 'Ghost', which ")
- code: `workhorse/workhorse/cli/offline.py::run_rewind` @b874da1d8083
- code: `workhorse/workhorse/rewind.py::rewind` @71550797f2a2

### refuse-rewind-without-checkpoint

- on: [control](#control)
- trigger: an operator rewinds a failed run with no checkpoint
- does:
  - Refuses the rewind and names the checkpoint path it tried.
- run: invoke(argv=["control", "rewind", "--to", "draft", "--run", "/tmp/workhorse-book/seeded/no-line"])
- verify: stderr(text="error: rewind refused, checkpoint unchanged: cannot read checkpoint /tmp/workhorse-book/seeded/no-line/checkpoint.json")
- code: `workhorse/workhorse/cli/offline.py::run_rewind` @b874da1d8083

### refuse-rewind-yaml-checkpoint

- on: [control](#control)
- trigger: an operator rewinds a checkpoint the retired YAML engine wrote
- does:
  - Refuses the rewind and names the retired engine.
- run: invoke(argv=["control", "rewind", "--to", "draft", "--run", "/tmp/workhorse-book/seeded/yaml-era"])
- verify: stderr(text="error: rewind refused, checkpoint unchanged: /tmp/workhorse-book/seeded/yaml-era/checkpoint.json is a checkpoint from the retired YAML engine")
- code: `workhorse/workhorse/cli/offline.py::run_rewind` @b874da1d8083

### refuse-resume-finished

- on: [control](#control)
- trigger: an operator resumes a run that finished done
- does:
  - Refuses the resume and names the run and its terminal.
- run: invoke(argv=["control", "resume", "--run", "/tmp/workhorse-book/seeded/finished"])
- verify: stderr(text="error: resume: /tmp/workhorse-book/seeded/finished already finished (done)")
- code: `workhorse/workhorse/cli/offline.py::run_resume` @6f1f9d97109f

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
- code: `workhorse/workhorse/cli/offline.py::run_resume` @6f1f9d97109f

### refuse-resume-without-launch

- on: [control](#control)
- trigger: an operator resumes a failed run that has no launch.json
- does:
  - Accepts the failed run, then refuses because it holds no usable launch.json.
- run: invoke(argv=["control", "resume", "--run", "/tmp/workhorse-book/seeded/failed-ghost"])
- verify: stderr(text="error: resume: no usable launch.json in /tmp/workhorse-book/seeded/failed-ghost (")
- code: `workhorse/workhorse/cli/offline.py::run_resume` @6f1f9d97109f

### refuse-resume-gone-pid

- on: [control](#control)
- trigger: an operator resumes a run whose recorded pid is gone
- does:
  - Accepts the run, then refuses and names the command to resume it by hand.
- run: invoke(argv=["control", "resume", "--run", "/tmp/workhorse-book/seeded/stale-pid"])
- verify: stderr(matches="run .<workflow> run --resume-run /tmp/workhorse-book/seeded/stale-pid. by hand")
- code: `workhorse/workhorse/cli/offline.py::run_resume` @6f1f9d97109f

### refuse-resume-contained

- on: [control](#control)
- trigger: an operator resumes a run launched inside a container
- does:
  - Refuses the resume and says to resume it inside its container.
- run: invoke(argv=["control", "resume", "--run", "/tmp/workhorse-book/seeded/contained"])
- verify: stderr(text="error: resume: launch.json holds container coordinates; resume it inside the container it ran in")
- code: `workhorse/workhorse/cli/offline.py::run_resume` @6f1f9d97109f

### refuse-resume-without-line

- on: [control](#control)
- trigger: an operator resumes a run whose launch.json records no resume line
- does:
  - Refuses the resume and names the run's launch.json.
- run: invoke(argv=["control", "resume", "--run", "/tmp/workhorse-book/seeded/no-line"])
- verify: stderr(text="error: resume: launch.json in /tmp/workhorse-book/seeded/no-line records no resume line")
- code: `workhorse/workhorse/cli/offline.py::run_resume` @6f1f9d97109f

### read-empty-inbox

- on: [inbox](#inbox)
- trigger: an operator reads a run that has no inbox file
- does:
  - Says the run has no outstanding messages.
- run: invoke(argv=["inbox", "read", "--run", "/tmp/workhorse-book/inbox"])
- verify: stdout(text="no outstanding messages in /tmp/workhorse-book/inbox")
- code: `workhorse/workhorse/inbox.py::outstanding` @11b9d85fca3c

### read-all-empty-inbox

- on: [inbox](#inbox)
- trigger: an operator reads every message of a run that has no inbox file
- does:
  - Says the run has no messages.
- run: invoke(argv=["inbox", "read", "--all", "--run", "/tmp/workhorse-book/inbox"])
- verify: stdout(text="no messages in /tmp/workhorse-book/inbox")
- code: `workhorse/workhorse/inbox.py::all_messages` @6773e53cedab

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
- code: `workhorse/workhorse/cli/inbox.py::run` @df83964543f3

### refuse-reply-without-text

- on: [inbox](#inbox)
- trigger: an operator replies with an id and no text
- does:
  - Refuses the reply and asks for both an id and text.
- run: invoke(argv=["inbox", "reply", "m1", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stderr(text="error: reply needs an id and text")
- code: `workhorse/workhorse/cli/inbox.py::run` @df83964543f3

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
- code: `workhorse/workhorse/inbox.py::reply` @800471b434e8

### refuse-unknown-inbox-run

- on: [inbox](#inbox)
- trigger: an operator names a `--run` that matches no directory
- does:
  - Refuses the read and says where it looked.
- run: invoke(argv=["inbox", "read", "--run", "nope", "--runs-dir", "nowhere"])
- verify: stderr(matches="no run dir for 'nope' [(]looked under /.*/nowhere[)]")
- code: `workhorse/workhorse/cli/target.py::resolve_target` @3cbe501f15ad

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
- code: `workhorse/workhorse/cli/inbox.py::add_arguments` @2ffa4ea9053f

### read-outstanding

- on: [inbox](#inbox)
- trigger: an operator checks what a run is asking
- does:
  - Prints the one outstanding message and its body.
- run: invoke(argv=["inbox", "read", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stdout(text="  may I push?")
- code: `workhorse/workhorse/inbox.py::outstanding` @11b9d85fca3c

### reply-to-message

- on: [inbox](#inbox)
- trigger: an operator answers the outstanding message
- does:
  - Records the reply and names the run.
- run: invoke(argv=["inbox", "reply", "m1", "go ahead", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stdout(text="replied to [m1] in /tmp/workhorse-book/inbox/answer")
- code: `workhorse/workhorse/inbox.py::reply` @800471b434e8

### read-all-messages

- on: [inbox](#inbox)
- trigger: an operator reviews every message after replying
- does:
  - Prints the new reply under the message it answers.
- run: invoke(argv=["inbox", "read", "--all", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stdout(text="  -> go ahead")
- code: `workhorse/workhorse/inbox.py::all_messages` @6773e53cedab

### replace-reply

- on: [inbox](#inbox)
- trigger: an operator replies again to a message that already has a reply
- does:
  - Replaces the reply and names the run.
- run: invoke(argv=["inbox", "reply", "m2", "later", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stdout(text="replied to [m2] in /tmp/workhorse-book/inbox/answer")
- code: `workhorse/workhorse/inbox.py::reply` @800471b434e8

### read-replaced-reply

- on: [inbox](#inbox)
- trigger: an operator reads every message after replacing a reply
- does:
  - Prints the replaced reply in place of the old one.
- run: invoke(argv=["inbox", "read", "--all", "--run", "/tmp/workhorse-book/inbox/answer"])
- verify: stdout(text="  -> later")
- code: `workhorse/workhorse/inbox.py::all_messages` @6773e53cedab

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
- code: `workhorse/workhorse/cli/replay.py::add_arguments` @88001e926f95

### refuse-replay-unknown-run

- on: [replay](#replay)
- trigger: an author names a `--run` that matches no directory
- does:
  - Refuses the replay without asking groom, and asks for the run's directory path.
- run: invoke(argv=["replay", "000-00001-x", "--run", "nope", "--runs-dir", "nowhere"])
- verify: stderr(matches="error: no run dir for 'nope' under /.*/nowhere; pass the run's directory path")
- code: `workhorse/workhorse/cli/replay.py::run` @6cad5c38a342

### refuse-missing-turn

- on: [replay](#replay)
- trigger: an author names a turn with no turn.json
- does:
  - Refuses the replay and names the missing turn.json.
- run: invoke(argv=["replay", "000-09999-none", "--run", "/tmp/workhorse-book/seeded/replay-run"])
- verify: stderr(text="error: /tmp/workhorse-book/seeded/replay-run/turns/000-09999-none/turn.json does not exist; name a directory under the run's turns/ that holds a turn.json")
- code: `workhorse/workhorse/cli/replay.py::run` @6cad5c38a342

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
- code: `workhorse/workhorse/cli/replay.py::run` @6cad5c38a342

### refuse-missing-prompt

- on: [replay](#replay)
- trigger: an author replays a turn that recorded no prompt.md, with no `--prompt`
- does:
  - Refuses the replay and asks for `--prompt`.
- run: invoke(argv=["replay", "000-00002-noprompt", "--run", "/tmp/workhorse-book/seeded/replay-run"])
- verify: stderr(text="error: /tmp/workhorse-book/seeded/replay-run/turns/000-00002-noprompt/prompt.md does not exist; pass --prompt with the prompt file to send")
- code: `workhorse/workhorse/cli/replay.py::run` @6cad5c38a342

### refuse-missing-variant

- on: [replay](#replay)
- trigger: an author names a `--prompt` that is no file
- does:
  - Refuses the replay and names the path as typed.
- run: invoke(argv=["replay", "000-00001-x", "--run", "/tmp/workhorse-book/seeded/replay-run", "--prompt", "nowhere.md"])
- verify: stderr(text="error: nowhere.md does not exist; pass --prompt with the prompt file to send")
- code: `workhorse/workhorse/cli/replay.py::run` @6cad5c38a342

### refuse-zero-repeat

- on: [replay](#replay)
- trigger: an author passes `--repeat` below 1
- does:
  - Refuses the replay and says a replay runs at least once.
- run: invoke(argv=["replay", "000-00004-moved", "--run", "/tmp/workhorse-book/seeded/replay-run", "--repeat", "0"])
- verify: stderr(text="error: --repeat 0: a replay runs the turn at least once")
- code: `workhorse/workhorse/cli/replay.py::run` @6cad5c38a342

### refuse-unsizable-variant

- on: [replay](#replay)
- trigger: an author sends a variant for a turn that recorded no prompt, with no limit
- does:
  - Refuses the replay because nothing sizes the variant, and asks for `--max-prompt-chars`.
- run: invoke(argv=["replay", "000-00002-noprompt", "--run", "/tmp/workhorse-book/seeded/replay-run", "--prompt", "/tmp/workhorse-book/seeded/v10.txt"])
- verify: stderr(text="error: /tmp/workhorse-book/seeded/replay-run/turns/000-00002-noprompt/prompt.md does not exist to size a variant against; pass --max-prompt-chars")
- code: `workhorse/workhorse/cli/replay.py::run` @6cad5c38a342

### refuse-oversized-variant

- on: [replay](#replay)
- trigger: an author sends a variant one character over twice the recorded prompt
- does:
  - Refuses the replay and states both lengths and the default limit's source.
- run: invoke(argv=["replay", "000-00004-moved", "--run", "/tmp/workhorse-book/seeded/replay-run", "--prompt", "/tmp/workhorse-book/seeded/v11.txt"])
- verify: stderr(text="error: /tmp/workhorse-book/seeded/v11.txt is 11 characters, over the 10 allowed (2 times the recorded 5-character prompt). Trim the variant, or raise the limit with --max-prompt-chars.")
- code: `workhorse/workhorse/cli/replay.py::run` @6cad5c38a342

### refuse-variant-over-limit

- on: [replay](#replay)
- trigger: an author sets `--max-prompt-chars` below the variant's length
- does:
  - Refuses the replay and names `--max-prompt-chars` as the limit's source.
- run: invoke(argv=["replay", "000-00004-moved", "--run", "/tmp/workhorse-book/seeded/replay-run", "--prompt", "/tmp/workhorse-book/seeded/v11.txt", "--max-prompt-chars", "10"])
- verify: stderr(text="is 11 characters, over the 10 allowed (--max-prompt-chars).")
- code: `workhorse/workhorse/cli/replay.py::run` @6cad5c38a342

### accept-variant-at-limit

- on: [replay](#replay)
- trigger: an author sets `--max-prompt-chars` to the variant's length
- does:
  - The variant passes the size check, and the replay then stops at the tree check.
- run: invoke(argv=["replay", "000-00004-moved", "--run", "/tmp/workhorse-book/seeded/replay-run", "--prompt", "/tmp/workhorse-book/seeded/v11.txt", "--max-prompt-chars", "11"])
- verify: stderr(text="seeded/bare is at no commit, not the turn's start")
- code: `workhorse/workhorse/cli/replay.py::run` @6cad5c38a342

### refuse-moved-replay

- on: [replay](#replay)
- trigger: an author replays a turn with a variant at exactly twice the recorded prompt, on a checkout that moved on
- does:
  - The variant passes the size check, and the replay refuses to reset the moved tree and names both heads.
- run: invoke(argv=["replay", "000-00004-moved", "--run", "/tmp/workhorse-book/seeded/replay-run", "--prompt", "/tmp/workhorse-book/seeded/v10.txt"])
- verify: stderr(text="is at no commit, not the turn's start deadbeefdead, and a replay resets its branch")
- code: `workhorse/workhorse/cli/replay.py::replay_turn` @9f271663abd7
