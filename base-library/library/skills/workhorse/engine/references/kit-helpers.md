# `workhorse_workflows.kit` — the shared helpers

The helper branch of [`workhorse-engine`](../SKILL.md): every seam a node uses instead of
a subprocess — git, GitHub, workspace resolution, `find_repo_root`, `find_docs_root`,
`load_json`, `load_jsonc`, `run_tool` — with the patch target each one needs under test.
Reached when a node touches a repo, a branch, a PR or a workspace file. For the doc graph,
[ostler-api.md](ostler-api.md) instead.

Everything a node reuses lives in the **workflow** distribution, not the engine: git,
GitHub and workspace resolution, plus `find_repo_root`, `find_docs_root`, `load_json`,
`load_jsonc` and `run_tool`. `run_tool` is the seam for a genuine external CLI — one that
is not git, GitHub or ostler.

```python
from workhorse_workflows import kit
```

- `kit.git` — `open_repo`, `active_branch`, `current_branch`, `default_branch`,
  `branch_exists`, `local_branch_exists`, `checkout`, `clone`, `fetch_reset`,
  `commit_all`, `commit_paths`, `commits_ahead`, `merge_base`, `diff_text`, `show_file`,
  `list_tracked_files`, `restore_paths`, `rename_branch`, `push_to_origin`, `origin_url`,
  `remote_urls`, `set_identity`, `short_sha`, `allow_all_directories`.
- `kit.github` — `resolve_github_token`, `resolve_repo`, `github_client`, `find_open_pr`,
  `push_branch`, `repo_full_name_from_url`, `sync_to_origin`.
- `kit.workspace` — `resolve_workspace`, `get_repo_config`, `get_affected_repos`,
  `build_dispatch_list`, `checkout_workspace`.

**Never shell out to `git` or `gh`.** The helpers wrap GitPython and PyGithub behind seams,
so a node never touches the CLIs while git still runs for **real** under test (against a
throwaway repo from `make_git_repo`) and GitHub is faked by patching `github_client`. Every
git helper is fail-soft: a bad repo or failed command returns `None`/`False`/`-1` rather
than raising into a run.

```python
# Branch: create or check out, idempotently — a resume re-enters this node.
if kit.git.local_branch_exists(repo_path, branch):
    kit.git.checkout(repo_path, branch)
else:
    kit.git.checkout(repo_path, branch, create=True)

kit.git.commit_all(repo_path, f"{epic}: {slug}" if epic else slug)   # False = nothing to commit
kit.git.commit_paths(repo_path, "prune completed epic from queue", paths.epics_index(root))
```

The pathspec on that last line comes from the workflow's `shared/paths.py`, never from a
`docs/…` literal: a workflow joins a filename it owns onto a directory **ostler** resolved,
so a repo that moved its epics with `docRoots:` still gets the right file staged. The rule
is stated in `workflows/README.md` under "A workflow does not spell a doc path".

`push_branch` handles the transient credential helper (the token rides `GH_TOKEN`, never a
URL / git config / log) **and** verifies the remote head advanced to the local head — an
unverified push is what lets a fix loop spin against a stale ref:

```python
if not kit.github.push_branch(repo_path, token, branch):   # verify=True by default
    ...  # push attempted but did not land / did not verify
```

For GitHub, go through the seams and reach for raw PyGithub objects past them when you need
structured responses (`gh_repo.get_workflow_runs(head_sha=…)`, `pr.merge(merge_method=…)`):

```python
token = kit.github.resolve_github_token(root)     # agents.yml workflow.githubTokenEnv → GH_TOKEN → GITHUB_TOKEN
gh_repo, slug = kit.github.resolve_repo(root, token)
if gh_repo is not None:
    pr = kit.github.find_open_pr(gh_repo, branch) or gh_repo.create_pull(
        title=title, body=body, head=branch, base=base,
    )
```

`kit` re-exports these through a module `__getattr__`, so `kit.git.commit_all` and
`from workhorse_workflows.kit.git import commit_all` are the same function. **Patch the
defining submodule** (`workhorse_workflows.kit.git`), not the `kit` facade, or the
forwarding hands the test the real one.

**Working directory.** A node inherits the driver's cwd, which is not necessarily the
checkout under work. Take the repo root as an **argument** rather than assuming it — never
from the environment, which is prohibited here (see *No environment* below):

```python
def my_node(logger: Logger, repo_dir: str = "") -> Result:
    root = kit.find_repo_root(repo_dir)   # argument first, else walk up from cwd
```

The workflow holds `repo_dir` as a field and `Workflow.injects` fills it into any node that
declares the parameter, so the callsite usually says nothing at all.

