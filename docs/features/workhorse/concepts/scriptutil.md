---
type: concept
slug: scriptutil
title: scriptutil — shared utilities for workflow scripts
---
# scriptutil — shared utilities for workflow scripts

A library of standalone helper functions for workflow **[script](../workflow-format.md#script)**
nodes: workspace resolution, relaxed-JSON/YAML file loading, and `git`/`gh` plumbing. Workspace
resolution centers on the [.code-workspace file](../code-workspace-file.md) — the on-disk shape
[`resolve_workspace`](#resolve_workspace-build-the-repo-map) and
[`checkout_workspace`](#checkout_workspace-cloneupdate-every-url-bearing-folder) each parse (via the
shared `_read_workspace_file` helper) to learn which repos a workflow run operates on. A script node
runs as its own subprocess (not workhorse's own process), so nothing here is imported by the engine
itself (`main.py`/`graph/`/`runner/`) — it exists purely so a workflow's own scripts (and
`entrypoint.sh`'s pre-graph checkout step, `python -c "from workhorse.scriptutil import
checkout_workspace; checkout_workspace()"`) don't each re-implement the same workspace-resolution
and git plumbing in a local `lib/` directory. Because workhorse is installed editable
(`pip install -e`), `from workhorse.scriptutil import ...` resolves for any script a workflow ships.

Every function here is a **parameterised primitive**: it takes the env-var name / path / dict it
needs as an argument rather than hard-coding a particular workflow's vocabulary (e.g.
`resolve_workspace(workspace_env_key)` — the caller passes its own env var name, such as
`CODER_WORKSPACE` — rather than the module assuming one). This is the model workhorse's own
`CLAUDE.md` points to for keeping the engine workflow-agnostic while still sharing real code.

- code: `workhorse/workhorse/scriptutil.py`

## `load_jsonc` — JSON-with-Comments parser

Parses the relaxed JSON dialect VSCode accepts for `.code-workspace` files: `//` line comments and
trailing commas before a closing `}`/`]`, neither valid in strict JSON.

- **Input:** `text: str` — raw file contents.
- **Output:** `dict` — the parsed object (`json.loads` after the two rewrites below).
- **Algorithm:** 1) regex-strip a `//` and everything after it, up to the next newline; 2)
  regex-strip a trailing comma immediately before a closing `}`/`]`; 3) `json.loads` the result.
- **Raises:** propagates `json.JSONDecodeError` if the rewritten text still isn't valid JSON.
- code: `workhorse/workhorse/scriptutil.py::load_jsonc`

Used by [`_read_workspace_file`](#resolve_workspace) (shared by `resolve_workspace` and
`checkout_workspace`) to read a `.code-workspace` file.

## `load_json` — best-effort JSON file loader

A caller-facing convenience over `json.loads` that never raises: a missing or unparsable file is
logged and treated as empty, for callers that would rather proceed with `{}` than crash a script
node outright.

- **Input:** `path: Path`, `label: str` (used only in the log message), `logger: logging.Logger`.
- **Output:** the parsed `dict`, or `{}` on failure.
- **Algorithm:** read `path` as UTF-8 and `json.loads` it; on `FileNotFoundError` log a warning
  (`"<label> not found at <path>"`) and return `{}`; on `json.JSONDecodeError` or `OSError` log a
  warning with the exception text and return `{}`.
- code: `workhorse/workhorse/scriptutil.py::load_json`

## `resolve_workspace` — build the repo map

Builds `{repo_name: {path, template, ...}}` describing every repo a script node might operate on,
merging in each repo's own `agents.yml` `workspace:` section. This is the primary lookup
[`build_dispatch_list`](#build_dispatch_list), [`get_repo_config`](#get_repo_config), and
[`get_affected_repos`](#get_affected_repos) all key off.

- **Input:** `workspace_env_key: str = "WORKSPACE_FILE"` — the env var name to read; callers pass
  their own convention (e.g. `"CODER_WORKSPACE"`) rather than this module assuming one.
- **Output:** `dict[str, dict]` — one entry per folder, each at least `{"path": <abs path str>}`,
  plus (when the folder's `agents.yml` exists and parses) `"template"` (its `template:` mapping) and
  every key of its `workspace:` mapping spread on top.
- **Algorithm:**
  1. **Locate folders.** Call the shared `_read_workspace_file(workspace_env_key)` helper — reads
     `os.environ[workspace_env_key]`; if unset or the path doesn't exist, returns `None`. When it
     returns `None`, fall back to a **single-folder** workspace: resolve the repo root as
     `AGENT_REPO_DIR` if set, else `Path.cwd()` (script nodes run with cwd = the workflow
     definition's own directory, not the consuming repo — `AGENT_REPO_DIR` is the correct signal,
     mirroring [`find_repo_root`](#find_repo_root)); name it from that root's own `agents.yml`
     `repo.name` if present, else the directory's basename; `ws_dir` is that root's **parent** (so
     the folder's `path` resolves back to the root itself). When `_read_workspace_file` does return
     `(folders, ws_dir)`, it parsed the `.code-workspace` file (via [`load_jsonc`](#load_jsonc)) at
     the env var's path and returned its `folders:` list (each `{"name"?, "path"}`, VSCode's own
     schema) plus `ws_dir` = that file's parent directory, which folder `path`s are resolved
     relative to.
  2. **Merge each folder's `agents.yml`.** For every folder: resolve its absolute path (`ws_dir /
     folder["path"]`); if `<abs path>/agents.yml` exists, `yaml.safe_load` it — on a YAML/OS error,
     the entry is just `{"path": ...}` (no `template`/`workspace` merge); otherwise take its
     `template:` mapping (default `{}`) and spread its `workspace:` mapping (default `{}`) over
     `{"path": ..., "template": ...}` so workspace keys win over the two fixed ones on collision.
     A folder with no `agents.yml` gets just `{"path": ...}`.
- **Raises:** does not raise on a missing/invalid `agents.yml` (caught and degraded per-folder, as
  above); an invalid `.code-workspace` file itself propagates `load_jsonc`'s `JSONDecodeError`.
- code: `workhorse/workhorse/scriptutil.py::resolve_workspace`
- verify: `workhorse/tests/test_scriptutil_workspace.py::test_resolve_workspace_uses_agent_repo_dir_over_cwd`, `test_resolve_workspace_falls_back_to_cwd_without_agent_repo_dir`

The `agents.yml` `workspace:` section is scriptutil's own reading of the file — a mono-repo-workflow
extension distinct from farrier's own field list for the same file (see
[`agents.yml`](../../farrier/agents-yml-config.md)'s `repo`/`template` fields, which farrier itself
renders from); farrier does not read or validate `workspace:`.

## `checkout_workspace` — clone/update every `url`-bearing folder

Clones or fast-forwards every folder in the `.code-workspace` file (or a single `REPO_URL`-derived
folder) into `workspace_root`, run once from `entrypoint.sh` before the workflow graph starts so
every folder's working tree already exists under `workspace_root/<folder name>` by the time any node
runs.

- **Input:** `workspace_env_key: str = "CODER_WORKSPACE"`; `workspace_root: str | Path =
  "/workspace"`.
- **Output:** `None` (side effect: working trees under `workspace_root`); logs progress via a
  `"workhorse.checkout"` logger configured to stderr at `INFO`.
- **Algorithm:**
  1. **Locate folders**, via the shared `_read_workspace_file(workspace_env_key)` helper (see
     [`resolve_workspace`](#resolve_workspace) — same helper, same `.code-workspace` parse). If it
     returns `None` (no workspace file set): read `REPO_URL`; if empty, log and return without doing
     anything; else synthesize one folder `{"name": REPO_NAME or "repo", "url": REPO_URL, "branch":
     REPO_BRANCH or "main"}` — this keeps the 1-repo and N-repo cases on one code path.
  2. `workspace_root.mkdir(parents=True, exist_ok=True)`.
  3. **Per folder** lacking a `url` key: skip entirely — it may not be a git repo at all (e.g. a
     plain docs directory reaching the container only via a bind mount), so nothing is cloned for it.
  4. **Per folder with a `url`:** `name` = its `name` or the path's basename; `branch` = its
     `branch` or `"main"`; `dest = workspace_root / name`.
     - **If `dest/.git` exists:** `git fetch --quiet origin`, then call the
       `_has_unsynced_work(dest, branch)` helper — `true` if `git status --porcelain` is non-empty
       *or* `git rev-list --count origin/<branch>..HEAD` is non-zero (uncommitted changes, or local
       commits not yet on `origin/<branch>`). If unsynced, **log and skip** — a bare reset can't
       distinguish "container restarted mid-run, resume where it left off" from "clean checkout, fast
       -forward to the host's latest," so this preserves in-container work (e.g. a blocked
       operator-gate node's edits) rather than silently discarding it. If synced, `git checkout
       --quiet <branch>` then `git reset --quiet --hard origin/<branch>`.
     - **Else:** `git clone --quiet --branch <branch> --single-branch <url> <dest>`. Cloning from a
       local bind-mounted path (a read-only host-working-tree trick) works exactly like cloning from
       a remote, so nothing about this path changes for that case.
- **Raises:** any `git`/`gh` `subprocess.run(..., check=True)` call propagates
  `subprocess.CalledProcessError` on a non-zero exit.
- code: `workhorse/workhorse/scriptutil.py::checkout_workspace`

The `.code-workspace` file's `url`/`branch` keys per folder are scriptutil's own optional schema
extension — VSCode ignores unknown keys, so a `.code-workspace` file authored for this purpose still
opens fine as a plain VSCode workspace.

## `find_repo_root` — locate the consuming repo

- **Input:** none.
- **Output:** `Path` — `AGENT_REPO_DIR` (resolved) if that env var is set; else the first of `Path.cwd()`
  and its parents containing an `agents.yml` or a `.git`; else `Path.cwd()` itself if none match.
- code: `workhorse/workhorse/scriptutil.py::find_repo_root`

`AGENT_REPO_DIR` takes priority over walking `cwd` because script nodes run with cwd set to the
*workflow definition's* own directory, not the consuming repo (see
[workhorse run](../workhorse.md#run)) — a bare `cwd`-walk would find the wrong `agents.yml`/`.git`
whenever the two diverge.

## `find_docs_root` — locate the docs repo

- **Input:** `docs_path: str = ""` — an explicit path (typically a workflow `var`).
- **Output:** `Path`, resolved in priority order: 1) `docs_path` if given (absolute as-is, else
  joined under [`find_repo_root()`](#find_repo_root)); 2) the `CODER_DOCS_PATH` env var, same
  absolute/relative handling; 3) `find_repo_root()` itself if neither is set.
- code: `workhorse/workhorse/scriptutil.py::find_docs_root`

## `get_repo_config` — read one `agents.yml` workspace value

- **Input:** `repo_name: str`, `key: str`, `default=None`, `repos: dict | None = None` (keyword-only).
- **Output:** `repo.get(key, default)` where `repo = repos.get(repo_name, {})`; when `repos` is
  omitted, it's built by calling [`resolve_workspace()`](#resolve_workspace) with its default env
  var (`"WORKSPACE_FILE"`) — pass `repos` explicitly when the caller already resolved the workspace
  under a different env var.
- code: `workhorse/workhorse/scriptutil.py::get_repo_config`

## `build_dispatch_list` — ordered per-service dispatch records

Joins a plan's `services`/`implementation_order` (a workflow-supplied `plan_ctx` dict — its exact
schema is owned by whichever workflow builds it, not by workhorse) against the
[`resolve_workspace`](#resolve_workspace) repo map, producing one ordered dict per service ready to
drive a dispatch/fan-out step.

- **Input:** `plan_ctx: dict` — expected shape `{"services": [{"repo", "path", "type"?,
  "plan_file"?, "skills"?}, ...], "implementation_order": [str, ...]}` (both keys optional, default
  `[]`); `repos: dict[str, dict]` — a [`resolve_workspace`](#resolve_workspace) result;
  `fallback: bool = False` (keyword-only).
- **Output:** `list[dict]`, each record:
  - `service` — `"<repo>::<path>"`, the same key `implementation_order` entries use.
  - `repo`, `cwd` (the repo's resolved path from `repos`), `service_path`, `type` (default
    `"unknown"`), `plan_file` (default `"plan.md"`), `skills` (default `[]`).
  - `qa_mode` (default `"cli"`), `qa_skills` (default `[]`), `verification` (default `""`) — all
    read from the repo's own `repos[repo_name]` entry, i.e. its `agents.yml` `workspace:` section.
  - `label` — the repo's `template.backend_layer_name`, else `template.mobile_layer_name`, else the
    service's own `type`.
- **Algorithm:**
  1. Key every `services` entry by `f"{svc['repo']}::{svc['path']}"` into `service_map`.
  2. Order by `implementation_order` if non-empty, else by `service_map`'s own keys (services'
     declared order).
  3. For each ordered key present in `service_map`, look up its repo in `repos` and build the record
     above; a key with no matching service is silently skipped.
  4. **Fallback (`fallback=True` only):** if the result is still empty and `repos` is non-empty,
     emit **one** record from the first repo in `repos` (`type: "unknown"`, `service_path: "."`,
     `plan_file: "plan.md"`, empty `skills`) — for callers that already know `plan-context.json` was
     absent or produced no services and want to proceed against the sole workspace repo anyway. Pass
     `fallback=True` only from such callers, not unconditionally.
- code: `workhorse/workhorse/scriptutil.py::build_dispatch_list`

## `get_affected_repos` — repos actually touched by a plan

- **Input:** `plan_ctx: dict` (same `services` shape as
  [`build_dispatch_list`](#build_dispatch_list)); `repos: dict[str, dict]` — a
  [`resolve_workspace`](#resolve_workspace) result.
- **Output:** `list[str]` — the sorted, deduplicated set of `svc["repo"]` values from `plan_ctx`
  that are also keys of `repos` (a service naming a repo outside the resolved workspace is
  excluded).
- code: `workhorse/workhorse/scriptutil.py::get_affected_repos`

## `open_repo` — lazy GitPython handle

- **Input:** `path: str | Path`.
- **Output:** a `git.Repo` opened at `path`.
- **Algorithm:** imports `git.Repo` **inside the function body**, not at module load — importing
  GitPython runs a `git --version` probe at import time, which raises `IndexError` parsing the
  version whenever `git` is shadowed by a stub (e.g. the workflow test harness's mocked `git`). Only
  scripts that actually open a repo pay that import cost; the many git-free scripts (select-next-*,
  resolve-*, detect-*) can import `workhorse.scriptutil` without a real `git` on `PATH`.
- code: `workhorse/workhorse/scriptutil.py::open_repo`

## `run_gh` — run a `gh` CLI command

- **Input:** `args: list[str]` (passed after `"gh"`), `cwd: str | Path`, `logger: logging.Logger`.
- **Output:** the `subprocess.CompletedProcess` (`capture_output=True, text=True`) on exit 0.
- **Raises:** on a non-zero exit, logs an error (`"gh <args> failed (exit <code>): <stderr>"`) and
  raises `RuntimeError(f"gh {args[0]} failed: {stderr}")` — never returns a failed result to the
  caller.
- code: `workhorse/workhorse/scriptutil.py::run_gh`

## Consumers

- Every workflow **[script](../workflow-format.md#script)** node's script may import from this
  module (available because workhorse is installed editable).
- `entrypoint.sh` invokes [`checkout_workspace`](#checkout_workspace) once, before the graph starts.
- `farrier/farrier/install.py` references [`checkout_workspace`](#checkout_workspace) in a comment
  (the pattern a generated workflow launcher's checkout step should follow) but does not import this
  module itself — farrier and workhorse stay independent packages.
