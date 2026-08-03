---
type: concept
slug: workflow-kit
title: workhorse_workflows.kit — git, GitHub and workspaces for nodes
---
# workhorse_workflows.kit — git, GitHub and workspaces for nodes

The domain half of what used to be `workhorse.scriptutil`: everything that knows what a repo is.
Three modules — `git`, `github`, `workspace` — behind one flat import surface:

```python
from workhorse_workflows.kit import commit_all, github_client, resolve_workspace
```

It lives in the `workflows` distribution, not in workhorse, because that is where `gitpython` and
`PyGithub` are dependencies. The split is the point: the engine gained nothing from knowing how to
open a PR, and every install of it paid for two libraries it never called. What stayed behind —
JSON parsing, root resolution, the reimport, the external-CLI seam — is documented in
[scriptutil](scriptutil.md).

- code: `workflows/src/workhorse_workflows/kit/__init__.py`

## The flat surface, and how to patch it

`workhorse_workflows.kit` resolves a name through `__getattr__` against a `{name: module}` map
rather than re-exporting it at import time. **Patch the defining submodule** — `kit.git`,
`kit.github`, `kit.workspace` — and the flat surface follows.

That indirection is not incidental. A node re-executes on every call, so its
`from workhorse_workflows.kit import github_client` re-reads the attribute and picks up a fake. A
plain re-export would have frozen those bindings at *package* import — one process-lifetime
earlier — and every existing patch would have silently stopped reaching the node while still
appearing to be installed.

One rule follows from having three modules where there was one: a helper here calls another through
its module object (`git_kit.origin_url(...)`), never a direct `from … import`, so a test that fakes
`kit.git.origin_url` also redirects `kit.github`'s internal use of it — which is what
monkeypatching a single module used to give for free.

## Workspace resolution

Which repos a run spans, where they are, and getting them onto disk. The manifest is the
[`.code-workspace` file](../code-workspace-file.md), parsed with scriptutil's
[`load_jsonc`](scriptutil.md#load_jsonc) by a shared `_read_workspace_file(workspace_file)`
helper: it parses the path it is handed and returns `(folders, ws_dir)`, or `None` when that path is
empty or does not exist. The path is an **argument** — the run's `workspace_file` input, never an
environment read (see [workflows/README.md](../../../../workflows/README.md)). It returns `None`
rather than guessing because `resolve_workspace` (read an existing checkout) and
`checkout_workspace` (create one) fall back differently.

- code: `workflows/src/workhorse_workflows/kit/workspace.py::_read_workspace_file`

### `resolve_workspace`

Builds `{repo_name: {path, template, ...}}` describing every repo a node might operate on, merging
in each repo's own `agents.yml` `workspace:` section. This is the primary lookup
[`build_dispatch_list`](#build_dispatch_list), [`get_repo_config`](#get_repo_config) and
[`get_affected_repos`](#get_affected_repos) all key off.

- **Input:** `workspace_file: str | Path = ""` — the manifest the run was given;
  `repo_dir: str | Path = ""` — the single checkout to fall back to. Both are workflow inputs the
  caller passes down, so this module assumes no convention and reads no environment.
- **Output:** `dict[str, dict]` — one entry per folder, each at least `{"path": <abs path str>}`,
  plus (when the folder's `agents.yml` exists and parses) `"template"` (its `template:` mapping) and
  every key of its `workspace:` mapping spread on top.
- **Algorithm:**
  1. **Locate folders** via `_read_workspace_file`. When it returns `(folders, ws_dir)`, `ws_dir` is
     the workspace file's parent directory and folder `path`s resolve relative to it. When it
     returns `None`, fall back to a **single-folder** workspace: the root is
     `find_repo_root(repo_dir)`, i.e. the argument when given and otherwise the upward walk from
     `Path.cwd()`; its name is the directory basename normalized by `_repo_name_from_dir` (the
     same kebab rule farrier derives an install prefix with, so a checkout at `.../Acme` is keyed
     `acme` here and its skills install as `acme-*`). `agents.yml` is not consulted for it — the
     name is the directory's, so one repo cannot answer to two names; and `ws_dir`
     is the root's **parent**, so the folder's `path` resolves back to the root itself. The
     argument comes first for the same reason it does in
     [`find_repo_root`](scriptutil.md#find_repo_root) — a bare `Path.cwd()` would key a mono-repo
     run off whatever directory the driver was launched from instead of the real repo.
  2. **Merge each folder's `agents.yml`.** Resolve `ws_dir / folder["path"]`; if
     `<abs path>/agents.yml` exists, `yaml.safe_load` it — on a YAML/OS error the entry is just
     `{"path": ...}` with no merge; otherwise take its `template:` mapping (default `{}`) and spread
     its `workspace:` mapping (default `{}`) over `{"path": ..., "template": ...}`, so workspace
     keys win over the two fixed ones on collision. A folder with no `agents.yml` gets just
     `{"path": ...}`.
- **Raises:** nothing on a missing/invalid `agents.yml` (caught and degraded per folder); an invalid
  `.code-workspace` file itself propagates `load_jsonc`'s `JSONDecodeError`.
- code: `workflows/src/workhorse_workflows/kit/workspace.py::resolve_workspace`
- verify: `workflows/tests/test_kit_workspace.py::test_resolve_workspace_uses_the_repo_dir_argument_over_cwd`
- verify: `workflows/tests/test_kit_workspace.py::test_resolve_workspace_falls_back_to_cwd_without_a_repo_dir`

The `agents.yml` `workspace:` section is this module's own reading of the file — a multi-repo
extension distinct from farrier's field list for the same file (see
[`agents.yml`](../../farrier/agents-yml-config.md), whose `repo`/`template` fields farrier itself
renders from). farrier does not read or validate `workspace:`.

### `checkout_workspace`

Materialises every `url`-bearing folder under `workspace_root` — cloning it, or (in `worktree`
mode) cutting a detached `git worktree` of a bind-mounted host repo. Invoked once **in-process** by
the container's `supervisor.py`, before the engine starts, so every folder's working tree already
exists by the time the first state runs. Neither coder nor author has a "setup" state.

- **Input:** `workspace_file: str | Path = ""`; `workspace_root: str | Path = "/workspace"`; and
  keyword-only `repo_url` / `repo_name` / `repo_branch` / `token_env` / `source_mode` /
  `worktree_root`. `supervisor.py` is the process boundary and passes what it read from the
  environment as arguments (this module's `__main__` exposes the same set as flags).
- **`source_mode`:** `clone` (default) is a disposable copy reset to the remote on restart;
  `worktree` gives each concurrent run its own working tree of one host repo, sharing its objects
  and refs. A worktree is created **detached** (no workflow knows its branch yet) and an existing
  one is **never reset** — it sits in the operator's own repo and may hold work in progress.
- **Output:** `None` (side effect: working trees under `workspace_root`); progress goes to stderr at
  `INFO` through a `"workhorse.checkout"` logger.
- **Algorithm:**
  1. **Locate folders** via the same `_read_workspace_file` helper. If it returns `None`, fall back
     to the `repo_url` argument; if empty, log and return having done nothing; else synthesize one
     folder `{"name": repo_name, "url": repo_url, "branch": repo_branch}` — which keeps the 1-repo
     and N-repo cases on one code path.
  2. `workspace_root.mkdir(parents=True, exist_ok=True)`.
  3. **Per folder without a `url`:** skip entirely. It may not be a git repo at all (e.g. a plain
     docs directory that reaches the container only via a bind mount), so nothing is cloned for it.
  4. **Per folder with a `url`:** `name` is its `name` or the path's basename; `branch` its `branch`
     or `"main"`; `dest = workspace_root / name`.
     - **`dest/.git` exists:** point `origin` at `url` (`_set_origin_url`, add-or-set-url, a no-op
       when it already matches — a persistent checkout must follow the configured source), fetch,
       then consult `_has_unsynced_work(dest, branch)`: true when `git status --porcelain` is
       non-empty *or* `git rev-list --count origin/<branch>..HEAD` is non-zero. If unsynced, **log
       and skip** — a bare reset cannot tell "container restarted mid-run, resume where it left off"
       from "clean checkout, fast-forward to the host's latest", so this preserves in-container work
       (a blocked operator-gate state's edits) rather than silently discarding it. If synced,
       `git checkout --quiet <branch>` then `git reset --quiet --hard origin/<branch>`.
     - **Otherwise:** `git clone --quiet --branch <branch> --single-branch <url> <dest>`. Cloning
       from a local bind-mounted path works exactly like cloning from a remote.
- **Credentials:** the network commands (clone, fetch) are built by `_git_network_command`, which
  prepends a transient `credential.helper` emitting `x-access-token` / `$WORKHORSE_GIT_TOKEN` when
  that variable is set, and is a plain `git` otherwise. A workflow-specific checkout hook
  resolves credentials per that workflow's own configuration and exports the variable; the generic
  code knows no token names or provider conventions.
- **Raises:** every `subprocess.run(..., check=True)` propagates `subprocess.CalledProcessError` on
  a non-zero exit; each carries a timeout (10s local, 300s fetch, 600s clone).
- code: `workflows/src/workhorse_workflows/kit/workspace.py::checkout_workspace`
- verify: `workflows/tests/test_kit_workspace.py::test_git_network_command_uses_configured_token_env`
- verify: `workflows/tests/test_kit_workspace.py::test_git_network_command_needs_no_token_for_public_or_local_clone`

### `get_repo_config`

- **Input:** `repo_name: str`, `key: str`, `default=None`, `repos: dict | None = None`
  (keyword-only).
- **Output:** `repo.get(key, default)` where `repo = repos.get(repo_name, {})`. When `repos` is
  omitted it is built by calling [`resolve_workspace()`](#resolve_workspace) with its default env
  var (`"WORKSPACE_FILE"`) — pass `repos` explicitly when the caller already resolved the workspace
  under a different one.
- code: `workflows/src/workhorse_workflows/kit/workspace.py::get_repo_config`

### `build_dispatch_list`

Joins a plan's `services`/`implementation_order` (a workflow-supplied `plan_ctx` dict, whose schema
is owned by whichever workflow builds it) against the [`resolve_workspace`](#resolve_workspace) repo
map, producing one ordered record per service ready to drive a fan-out.

- **Input:** `plan_ctx: dict` — expected shape `{"services": [{"repo", "path", "type"?,
  "plan_file"?, "skills"?}, ...], "implementation_order": [str, ...]}` (both keys optional, default
  `[]`); `repos: dict[str, dict]`; `fallback: bool = False` (keyword-only).
- **Output:** `list[dict]`, each record carrying:
  - `service` — `"<repo>::<path>"`, the same key `implementation_order` entries use.
  - `repo`, `cwd` (the repo's resolved path from `repos`), `service_path`, `type` (default
    `"unknown"`), `plan_file` (default `"plan.md"`), `skills` (default `[]`).
  - `qa_mode` (default `"cli"`), `qa_skills` (default `[]`), `verification` (default `""`) — read
    from `repos[repo_name]`, i.e. that repo's `agents.yml` `workspace:` section.
  - `label` — the repo's `template.backend_layer_name`, else `template.mobile_layer_name`, else the
    service's own `type`.
- **Algorithm:** key every `services` entry by `f"{svc['repo']}::{svc['path']}"`; order by
  `implementation_order` when non-empty, else by the services' declared order; build the record
  above for each ordered key present, silently skipping a key with no matching service. With
  `fallback=True` only: if the result is still empty and `repos` is non-empty, emit **one** record
  from the first repo (`type: "unknown"`, `service_path: "."`, `plan_file: "plan.md"`, no skills,
  `label` = the repo name). Pass `fallback=True` only from callers that already know the plan
  context was absent or listed no services.
- code: `workflows/src/workhorse_workflows/kit/workspace.py::build_dispatch_list`

### `get_affected_repos`

- **Input:** `plan_ctx: dict` (same `services` shape as
  [`build_dispatch_list`](#build_dispatch_list)); `repos: dict[str, dict]`.
- **Output:** `list[str]` — the sorted, deduplicated set of `svc["repo"]` values that are also keys
  of `repos`. A service naming a repo outside the resolved workspace is excluded.
- code: `workflows/src/workhorse_workflows/kit/workspace.py::get_affected_repos`

## git

The git commands a node needs, wrapped so it never shells out. GitPython is a thin wrapper over the
git CLI, so behaviour matches the subprocess calls these replaced while error handling routes
through `GitError`.

Two properties are contractual:

- **Fail-soft.** Each helper opens the repo lazily and returns a plain value — `None`, `False`, `""`
  or `-1` — rather than raising into an unattended run.
- **No seam.** There is nothing to monkeypatch here: under test the real git CLI runs against a
  throwaway repo (`workhorse.testing.make_git_repo`). Only [GitHub](#github) is faked.

GitPython is imported at **module scope**, not inside each function. The old in-function import
existed because importing GitPython runs a `git --version` probe that crashes when `git` is shadowed
by a stub, and the engine was full of git-free scripts that had to import the module anyway — a
constraint that ended with the split, since importing this module is now itself the statement that
you want git.

| | |
|---|---|
| **open the repo** | `open_repo` — the single seam every other helper here opens |
| **inspect** | `origin_url`, `remote_urls`, `current_branch`, `active_branch`, `default_branch`, `local_branch_exists`, `branch_exists`, `short_sha`, `commits_ahead`, `merge_base`, `list_tracked_files`, `show_file`, `diff_text` |
| **change** | `checkout` (`create` cuts with `-b`, `reset` create-or-resets with `-B` and wins over `create`), `rename_branch`, `restore_paths`, `commit_paths`, `commit_all`, `clone`, `fetch_reset`, `push_to_origin` |
| **environment** | `set_identity` (repo-local `user.name`/`user.email`, for unattended committers with no ambient git identity), `allow_all_directories` (global `safe.directory = *`, for a host-owned bind mount inside a container) |

`push_to_origin` uses the checkout's **ambient** credentials (an SSH key, a cached helper).
Token-authenticated pushes are [`kit.github.push_branch`](#github)'s job instead — they are
github.com operations, not generic git.

- code: `workflows/src/workhorse_workflows/kit/git.py::open_repo`
- code: `workflows/src/workhorse_workflows/kit/git.py::checkout`
- code: `workflows/src/workhorse_workflows/kit/git.py::commit_all`

## github

GitHub access through **PyGithub, never the `gh` CLI**. `github_client` is the one seam every node
goes through, and because it is a plain Python call an in-process test monkeypatches it — no PATH
shim, no CLI, no network. Every helper below inherits that seam.

| symbol | does |
|---|---|
| `github_client(token=None)` | an authenticated PyGithub `Github` client — the seam |
| `resolve_github_token(root=None)` | the first non-empty of: the env var named by the repo's `agents.yml` `workflow.githubTokenEnv` (or `github_token_env`), `GH_TOKEN`, `GITHUB_TOKEN` — `""` when none is set, which callers read as "no token, skip". `root` defaults to [`find_repo_root()`](scriptutil.md#find_repo_root) |
| `repo_full_name_from_url(url)` | an `owner/repo` slug from an origin URL (SSH or HTTPS); `None` when the origin is not github.com |
| `resolve_repo(path, token=None)` | the GitHub repository for the `origin` configured at `path` |
| `find_open_pr(gh_repo, branch)` | the first OPEN pull request whose head is `branch`, else `None` |
| `push_branch(...)` | push `branch` over HTTPS with a transient token |
| `sync_to_origin(path, token, base)` | fetch `base` over HTTPS and hard-set the local `base` to it (`git checkout -B <base> FETCH_HEAD`) |

- code: `workflows/src/workhorse_workflows/kit/github.py::github_client`
- code: `workflows/src/workhorse_workflows/kit/github.py::resolve_github_token`

## Consumers

- Workflow **[node functions](../workflow-format.md#node)** across `author`, `coder` and
  `okf_builder`.
- `workhorse/supervisor.py`, which calls [`checkout_workspace`](#checkout_workspace) once, in
  process, before the engine starts.
- Not the engine. Nothing under `workhorse/workhorse/` imports this package — the dependency runs
  one way only, `kit` → [`scriptutil`](scriptutil.md), and only for
  [`load_jsonc`](scriptutil.md#load_jsonc) and [`find_repo_root`](scriptutil.md#find_repo_root).
