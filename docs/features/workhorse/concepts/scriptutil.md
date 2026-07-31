---
type: concept
slug: scriptutil
title: scriptutil — the engine-side helpers a node imports
---
# scriptutil — the engine-side helpers a node imports

A small library of standalone helpers for workflow **[node functions](../workflow-format.md#node)**:
JSON/JSONC parsing, the hard-fail idiom, repo/docs root resolution, the mid-run reimport, and one
external-CLI seam. What is left here is what a *runner* needs and nothing that knows what a repo
is — git, GitHub and multi-repo workspace resolution live in
[`workhorse_workflows.kit`](workflow-kit.md), a different distribution.

Every function is a **parameterised primitive**: it takes the env-var name, path or dict it needs as
an argument rather than hard-coding a particular workflow's vocabulary. That is how the engine stays
workflow-agnostic while still sharing real code.

- code: `workhorse/workhorse/scriptutil.py`

## `load_jsonc`

Parses the relaxed JSON dialect VSCode accepts for `.code-workspace` files: `//` line comments and
trailing commas before a closing `}`/`]`, neither valid in strict JSON.

- **Input:** `text: str` — raw file contents.
- **Output:** `dict` — the parsed object (`json.loads` after the two rewrites below).
- **Algorithm:** 1) regex-strip a `//` and everything after it, up to the next newline; 2)
  regex-strip a trailing comma immediately before a closing `}`/`]`; 3) `json.loads` the result.
- **Raises:** propagates `json.JSONDecodeError` if the rewritten text still isn't valid JSON.
- code: `workhorse/workhorse/scriptutil.py::load_jsonc`

This is the one engine-side helper the workspace kit still reaches back for:
`workhorse_workflows.kit.workspace` imports it to read a
[`.code-workspace` file](../code-workspace-file.md). Parsing a relaxed-JSON file is runner work;
knowing what the folders in it *mean* is not.

## `load_json`

A caller-facing convenience over `json.loads` that never raises: a missing or unparsable file is
logged and treated as empty, for callers that would rather proceed with `{}` than fail the node
outright.

- **Input:** `path: Path`, `label: str` (used only in the log message), `logger: logging.Logger`.
- **Output:** the parsed `dict`, or `{}` on failure.
- **Algorithm:** read `path` as UTF-8 and `json.loads` it; on `FileNotFoundError` log a warning
  (`"<label> not found at <path>"`) and return `{}`; on `json.JSONDecodeError` or `OSError` log a
  warning with the exception text and return `{}`.
- code: `workhorse/workhorse/scriptutil.py::load_json`

## `die`

The hard-fail idiom, defined once instead of re-implemented per node.

- **Input:** `message: str`; `code: int = 1` (keyword-only).
- **Output:** `NoReturn` — prints `message` to stderr and raises `SystemExit(code)`.

Unlike `sys.exit(message)`, which always exits `1`, this pairs an actionable message with any exit
`code`: nodes use `2` to distinguish a bad or missing invocation target from an ordinary failure, a
distinction the script runner propagates. The `NoReturn` annotation is load-bearing for callers —
statements after `die(...)` narrow as unreachable, and a thin per-workflow wrapper that always ends
in `die` is itself `NoReturn`.

- code: `workhorse/workhorse/scriptutil.py::die`

## `find_repo_root`

- **Input:** `repo_dir: str | Path = ""` — the run's own input (`Workflow.repo_dir`, which the CLI
  defaults to the launch directory), handed to the node as an argument.
- **Output:** `Path` — `repo_dir` resolved when given; else the first of `Path.cwd()` and its
  parents containing an `agents.yml` or a `.git`; else `Path.cwd()` itself if none match.
- code: `workhorse/workhorse/scriptutil.py::find_repo_root`

The argument takes priority over walking `cwd` because a run's cwd is not necessarily the consuming
repo (see [workhorse run](../workhorse.md#run)) — a bare `cwd`-walk would find the wrong
`agents.yml`/`.git` whenever the two diverge. It reads **no environment variable**: a node whose
root depends on the ambient environment is a node whose behavior no caller can see or override,
which is the rule in [workflows/README.md](../../../../workflows/README.md).
`workhorse_workflows.kit`'s [`resolve_workspace`](workflow-kit.md#resolve_workspace) mirrors the
same argument-first order for exactly that reason.

## `find_docs_root`

- **Input:** `docs_path: str = ""` — an explicit path (typically a workflow parameter);
  `repo_dir: str | Path = ""`, the same input `find_repo_root` takes, so the two travel together.
- **Output:** `Path`, resolved in priority order: 1) `docs_path` if given (absolute as-is, else
  joined under [`find_repo_root(repo_dir)`](#find_repo_root)); 2) `find_repo_root(repo_dir)` itself
  when it is empty — i.e. the docs sit beside the code.
- code: `workhorse/workhorse/scriptutil.py::find_docs_root`

## `fresh_import`

Re-imports a module straight from disk instead of returning whatever `sys.modules` already holds.

- **Input:** `name: str`; `also_purge: tuple[str, ...] = ()` (keyword-only).
- **Output:** the imported `ModuleType`.
- **Algorithm:** delete `name` and every `also_purge` root from `sys.modules`, along with each of
  their submodules, then `importlib.import_module(name)`.

The in-process script runner (`workhorse/workhorse/runner/script.py`) reuses one Python interpreter
for a whole run. A node re-executes on every call, but anything it merely `import`s stays cached for
the rest of the run — so a fix landed on disk mid-run (an environment-fix loop editing a QA-tool
package while QA states are still ahead) stays invisible to every later state unless that state
forces a real reimport. Pass any package `name` transitively imports and might change mid-run via
`also_purge` — e.g. `fresh_import("qa_cli", also_purge=("ostler",))` — so its stale submodules don't
leak back in through the reimported caller.

`WORKHORSE_FRESH_IMPORT=0` (also `false`/`no`/`off`) disables the purge and returns the cached
module. That escape hatch exists for tests: reimporting builds a *new module object*, so every
`monkeypatch.setattr` applied to the old one is silently discarded — the mock is still in place, just
no longer on the thing the caller reaches. Nothing edits a package on disk under test, so the
behavior the purge exists for cannot occur there anyway.

- code: `workhorse/workhorse/scriptutil.py::fresh_import`
- verify: `workhorse/tests/test_scriptutil_fresh_import.py::test_fresh_import_picks_up_an_edit_made_after_the_first_import`
- verify: `workhorse/tests/test_scriptutil_fresh_import.py::test_disabled_fresh_import_preserves_a_monkeypatched_attribute`

## `run_tool`

Runs an external CLI (`ostler`, say) as a subprocess and returns the completed process.

- **Input:** `argv: list[str]`; `cwd: str | Path | None = None`; `check: bool = False` and
  `logger: logging.Logger | None = None` (keyword-only).
- **Output:** the `subprocess.CompletedProcess` (`capture_output=True, text=True`).
- **Raises:** with `check=True` and a non-zero exit, logs an error through `logger` (if given) and
  raises `RuntimeError(f"{argv[0]} failed: {stderr}")`. With `check=False` (the default) a failed
  result is returned to the caller as-is.
- code: `workhorse/workhorse/scriptutil.py::run_tool`

This is the single seam nodes route external-CLI calls through, so an in-process test can
monkeypatch `run_tool` on this module and get a canned result with no `PATH` shim. In production it
runs the real binary — the "real passthrough" contract.

## What moved to `workhorse_workflows.kit`

Anything that knows what a repo is now lives in [the workflow kit](workflow-kit.md), which is where
`gitpython` and `PyGithub` are dependencies. They are workflow domain, not engine: the engine gained
nothing from knowing how to open a PR, and every install of it paid for two libraries it never
called. Nodes import the same names from `workhorse_workflows.kit` and patch the **defining**
submodule (`kit.git`, `kit.github`, `kit.workspace`).

| was `workhorse.scriptutil.…` | now |
|---|---|
| `resolve_workspace`, `checkout_workspace`, `get_repo_config`, `build_dispatch_list`, `get_affected_repos`, `_read_workspace_file`, `_has_unsynced_work` | [`workhorse_workflows.kit.workspace`](workflow-kit.md#workspace-resolution) |
| `open_repo` | [`workhorse_workflows.kit.git`](workflow-kit.md#git) — alongside the 23 other git verbs that grew up around it |
| `run_gh` | **gone.** GitHub is reached through PyGithub in [`kit.github`](workflow-kit.md#github); a node that genuinely needs another CLI uses [`run_tool`](#run_tool) |

## Consumers

- Any workflow **[node function](../workflow-format.md#node)** may import from this module —
  workhorse is a `uv` workspace member, so `from workhorse.scriptutil import ...` resolves wherever
  the engine is installed.
- `workhorse_workflows.kit.workspace` imports [`load_jsonc`](#load_jsonc).
- Nothing here reads a `.code-workspace` file itself; that is the kit's job.
