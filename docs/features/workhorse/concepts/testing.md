---
type: concept
slug: testing
title: workhorse.testing — workflow test harness
---
# workhorse.testing — workflow test harness

A library workflow authors import from their workflow's `tests/*.py` pytest files — the suite
[`workhorse test`](../workhorse.md#test) runs. It invokes the **real** `workhorse` CLI as a
subprocess against an isolated sandbox directory rather than mocking any workhorse internals; agent
and shell-command calls are intercepted instead by writing PATH shim executables ahead of the run,
so the workflow graph, checkpointing, and [artifact](../run-artifacts.md) writing all execute for real while the agent CLI
and named commands (`git`, `gh`, …) return scripted responses. Every consumer lives outside this
repo (in a prompt library's own `<workflow>/tests/`), so no `verify:`/consumer link resolves inside
`stablemate` itself.

- code: `workhorse/workhorse/testing.py`

## Shim scripts

Two Python source templates are written as executable files under the sandbox's shim `bin/`
(prepended to `PATH` for the subprocess run) so the real `workhorse` process invokes a shim instead
of the real binary.

### the claude shim (`_CLAUDE_SHIM`)
Installed under the name `claude`, and also under whatever `--cli` name the test selects (see
[`WorkflowRun.run`](#workflowrun)'s `cli` argument), so workhorse finds an executable by either
name.
- **Per invocation:** reads `WORKHORSE_SHIM_DIR` and `WORKHORSE_NODE_ID` from its environment
  (workhorse sets `WORKHORSE_NODE_ID` when it starts the agent-CLI subprocess) and all of stdin.
- **Records the call** as `<shim_dir>/calls/claude/<seq>.json` — `{seq, node_id, args, stdin, cwd}`,
  `seq` a zero-padded counter of prior recorded calls for `claude`.
- **Tracks a per-node call index** in `<shim_dir>/call_counts/<node_id>.txt`, incremented each
  call — drives [`mock_agent_sequence`](#workflowrun)'s "successive responses" behavior.
- **Looks up its mock** at `<shim_dir>/agent_mocks/<node_id>.json`. If the file is a JSON list
    (a sequence mock), selects `list[min(call_idx, len(list)-1)]` (the last entry repeats once
    exhausted); otherwise uses the single dict as-is. Each selected entry has `response` (str,
    default `"{}"`), `exit_code` (int, default `0`), `side_effects` (list, default `[]`). If no mock
    file exists at all, prints a `[test-shim] ⚠ no agent mock for node '<node_id>'` warning to
    stderr and falls back to `response="{}"`, `exit_code=0`, `side_effects=[]`.
- **Applies `side_effects` before emitting** — each is `{"path": str, "content": str}`; the shim
  creates parent directories and writes `content` to `path`, simulating a file the real agent would
  have written, with a failure logged (not raised).
- **Emits** one stream-json `result` event to stdout — `{"type": "result", "subtype": "success",
  "result": <response text>, "is_error": false, "session_id": "test-session", "cost_usd": 0,
  "duration_ms": 1, "usage": {...all zero}}` — the shape workhorse's `_stream_events()`
  (`runner/agent.py`) parses to extract the agent's response text — then exits with `exit_code`.

### the generic command shim (`_COMMAND_SHIM_TEMPLATE`)
Written per name registered via [`mock_command`](#workflowrun) (e.g. `git`, `gh`), with `CMD_NAME`
substituted into the template at write time.
- **Records the call** the same way as the claude shim, under `<shim_dir>/calls/<CMD_NAME>/`.
- **Looks up its mock** at `<shim_dir>/command_mocks/<CMD_NAME>.json`. Missing file → prints a
  `[test-shim] ⚠ no mock for command '<CMD_NAME>'` warning and exits `0`. A dict with an
  `exit_code`/`stdout` key is a single fixed response for every invocation. Otherwise the dict is a
  per-first-argv dispatch map: looked up by `sys.argv[1]`, falling back to the `"*"` key, else
  exits `0` with no output.
- **Emits** the resolved `stdout` (if any) then exits with the resolved `exit_code`.

## `WorkflowRun` — drive one workflow run against a sandbox
Constructed per test with `WorkflowRun(workflow: str | Path, sandbox: Path)` — `workflow` is the
`workflow.yaml` path (resolved immediately); `sandbox` is the isolated directory the run executes
in (typically pytest's `tmp_path`). All harness state lives under `<sandbox>/.workhorse-test/`:
`bin/` (shims), `agent_mocks/`, `command_mocks/`, `calls/`, `runs/` (the `--runs-dir` passed to the
real CLI).

- code: `workhorse/workhorse/testing.py::WorkflowRun`

### `mock_agent(node_id, response, exit_code=0, side_effects=None)`
Writes `<sandbox>/.workhorse-test/agent_mocks/<node_id>.json` — a fixed response for every call to
agent node `node_id`. `response: str | dict` (a dict is JSON-serialized); `exit_code: int = 0`;
`side_effects: list[dict] | None = None`, each `{"path": str, "content": str}` written by the shim
after emitting the response.
- code: `workhorse/workhorse/testing.py::WorkflowRun.mock_agent`

### `mock_agent_sequence(node_id, responses, exit_code=0)`
Writes a JSON **list** to the same mock file so repeated calls to `node_id` return successive
entries (the last repeats once the list is exhausted) — the tool for testing a rework/retry cycle.
`responses: list[str | dict]`, each item either a bare response (str/dict, using the `exit_code`
keyword for all of them) or a fully-specified `{"response", "exit_code"?, "side_effects"?}` dict
(its own `exit_code` wins over the keyword for that entry).
- code: `workhorse/workhorse/testing.py::WorkflowRun.mock_agent_sequence`

### `mock_command(name, response)`
Writes `<sandbox>/.workhorse-test/command_mocks/<name>.json` for a PATH command (`git`, `gh`, …).
`response` is either `tuple[int, str]` (`(exit_code, stdout)`, identical reply to every call) or
`dict[str, tuple[int, str]]` (dispatched by first argv, `"*"` as the fallback key).
- code: `workhorse/workhorse/testing.py::WorkflowRun.mock_command`

### `run(*, params=None, flow=None, cli="claude", timeout=120, extra_env=None) -> RunResult`
Executes `workhorse --workflow <workflow> [<flow>] --runs-dir <sandbox>/.workhorse-test/runs
[--params <json>]` as a real subprocess with `cwd=sandbox`, and returns a [`RunResult`](#runresult).
- **Input:** `params: dict | None` — merged into `--params` JSON; `flow: str | None` — runs one
  named `flows:` sub-graph standalone instead of the whole graph (its params must supply every var
  the flow requires); `cli: str = "claude"` — which agent-CLI name the mocked shim answers to
  ([`--cli`](../workhorse.md#run)'s counterpart); `timeout: float = 120` — seconds before the
  subprocess is killed; `extra_env: dict[str, str] | None` — additional env vars layered over the
  inherited environment, e.g. `GH_TOKEN` to enable CI-gate code paths.
- **Algorithm:**
  1. `_setup_shims(cli)` — write the claude shim under `claude` and (if different) `cli`; write a
     generic command shim for every file under `command_mocks/`.
  2. Build `cmd = ["workhorse", "--workflow", <workflow>, [<flow>], "--runs-dir", <runs_dir>,
     ["--params", <json>]]`.
  3. Build `env` = `os.environ` overlaid with `extra_env`, then the fixed harness variables (highest
     precedence): `PATH` prepended with the shim `bin/`; `AGENT_CLI=<cli>`;
     `WORKHORSE_SHIM_DIR=<test_dir>`; `WORKHORSE_DEFAULT_SCRIPT_CWD=<sandbox>`;
     `WORKHORSE_GAS=1500` (small gas-tank default so a stuck loop fails fast under test rather than
     riding the `timeout` wall — see the engine's gas-tank guard);
     `AGENT_MAX_REPHRASE_ATTEMPTS=0` and `AGENT_INVOKE_BACKOFF_BASE_S=0` (kill the [recovery
     ladder's](../../../../workhorse/docs/GUARDRAILS.md) reframe/backoff sleeps so a parse-miss resolves
     to defaults instantly instead of burning real wall-clock time); `AGENT_REPO_DIR=<sandbox>`
     (pins scripts that resolve the consuming repo, e.g. every git-touching workflow script, onto
     the sandbox instead of walking up from cwd into the real prompt-library checkout). Each of
     `WORKHORSE_GAS`/`AGENT_MAX_REPHRASE_ATTEMPTS`/`AGENT_INVOKE_BACKOFF_BASE_S` is overridable by
     the caller's own `extra_env`.
  4. Run the subprocess (`capture_output=True, text=True, cwd=sandbox, env=env, timeout=timeout`).
  5. On `subprocess.TimeoutExpired`: return a `RunResult` with `exit_code=-1` and `stderr` prefixed
     `[workhorse.testing] timed out after <timeout>s`. Otherwise return a `RunResult` built from the
     completed process's `returncode`/`stdout`/`stderr`.
- code: `workhorse/workhorse/testing.py::WorkflowRun.run`

## `RunResult` — the outcome of one `WorkflowRun.run()` call
A dataclass: `exit_code: int`, `stdout: str`, `stderr: str`, `runs_dir: Path` (the `--runs-dir`
passed to the CLI), `test_dir: Path` (the sandbox's `.workhorse-test/`, parent of `runs_dir`, where
shim calls are recorded).

- code: `workhorse/workhorse/testing.py::RunResult`

- `run_dir: Path | None` (property) — the single run directory under `runs_dir`
  (most-recently-modified, if `runs_dir` holds more than one — a fresh run creates exactly one).
- `passed() -> bool` — `exit_code == 0`.
- `context() -> dict` — the run's final context: reads `context.json` if present, else
  `checkpoint.json`'s `"context"` key (or the raw dict if it has no such key); `{}` if neither file
  exists or parses.
- `step_outputs(node_id) -> dict` — parses `<node_id>/output.json`'s contents; `{}` if absent or
  invalid. Resolves `node_id` whether it ran at the workflow's top level or nested inside a
  `flows:` sub-graph — a flow's child nodes are written under `.../_flow/<node_id>/…` (flows may
  nest, giving `.../_flow/.../_flow/<node_id>/…`); the top-level path is preferred, else the first
  match found via `rglob("_flow")`.
- `prompt(node_id) -> str` — the rendered `<node_id>/prompt.md` sent to the agent (same top-level
  vs `_flow`-nested resolution as `step_outputs`); `""` if not found.
- `calls(command) -> list[dict]` — every shim invocation recorded for `command`
  (`<test_dir>/calls/<command>/*.json`), sorted by filename (i.e. by `seq`); `[]` if none.
- `has_warning(text) -> bool` — `text in stdout or text in stderr`.
- `output_lines() -> list[str]` — `stdout.splitlines()`.

## Assertion helpers
Module-level `assert`-based helpers, each raising `AssertionError` with a diagnostic message on
failure (standard pytest-collected assertions, not custom exceptions):

- `assert_file(sandbox, rel)` — `sandbox / rel` exists.
- `assert_file_contains(sandbox, rel, text)` — `sandbox / rel` exists and its text contains `text`.
- `assert_json_file(sandbox, rel, subset)` — `sandbox / rel` exists and parses as JSON; if `subset`
  is a `dict`, every key/value pair in it must be present and equal in the parsed file (extra keys
  in the file are ignored); if `subset` is a `list`, the parsed JSON must equal it exactly.
- `assert_step_output(result, node_id, key, expected)` — `result.step_outputs(node_id)[key] ==
  expected` (via [`RunResult.step_outputs`](#runresult)).
- `assert_prompt_contains(result, node_id, text)` — `result.prompt(node_id)` is non-empty and
  contains `text` (via [`RunResult.prompt`](#runresult)).
- `assert_command_called(result, command, args_contain)` — at least one of `result.calls(command)`
  (via [`RunResult.calls`](#runresult)) has an arg containing `args_contain`.

- code: `workhorse/workhorse/testing.py::assert_file`, `workhorse/workhorse/testing.py::assert_file_contains`, `workhorse/workhorse/testing.py::assert_json_file`, `workhorse/workhorse/testing.py::assert_step_output`, `workhorse/workhorse/testing.py::assert_prompt_contains`, `workhorse/workhorse/testing.py::assert_command_called`

## Consumers

- Every workflow's `tests/*.py`, run via [`workhorse test <workflow_dir>`](../workhorse.md#test) —
  the only in-repo entry point that exercises this module's contract, though the test files
  themselves live in each prompt library, outside `stablemate`.

