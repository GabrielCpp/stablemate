---
type: concept
slug: workflow-kit-git
title: Workflow kit Git
---
# Workflow kit Git

The Git kit is the workflow-side, fail-soft facade for repository inspection, branch management,
history comparison, working-tree changes, and network synchronization. Inspection and ordinary
branch helpers return an empty, false, or sentinel value when Git cannot answer. The two commit
helpers distinguish an empty tree from a Git refusal: `commit_paths` stages only explicit
pathspecs, while `commit_all` deliberately stages the whole tree and is safe only in an
exclusive checkout. `merge_ref` aborts a conflicted merge before reporting failure.

- code: `workflows/src/workhorse_workflows/kit/git.py`
- tests: `workflows/tests/test_kit_git.py::test_commit_paths_stages_only_the_named_paths`
- tests: `workflows/tests/test_kit_git.py::test_commit_paths_with_no_pathspecs_commits_nothing`
- tests: `workflows/tests/test_kit_git.py::test_commit_all_still_sweeps_the_whole_tree`
- tests: `workflows/tests/test_kit_git.py::test_a_refused_commit_raises_instead_of_reading_as_an_empty_one`

## Fields

### TRUNK_CANDIDATES

- type: `tuple[str, ...]`
- default: `("origin/master", "origin/main", "master", "main")`
- required: true
- semantics: trunk refs are ordered from highest to lowest priority
- verify: json_path(path="$.value", equals="origin/master, origin/main, master, main")
- semantics: remote-tracking refs take precedence over local branches
- verify: json_path(path="$.value", equals="origin/master, origin/main, master, main")
- code: `workflows/src/workhorse_workflows/kit/git.py::TRUNK_CANDIDATES`

## Methods

### open_repo

- sig: `open_repo(path: str | Path) -> Repo`
- does: opens the repository at `path` through GitPython
- verify: json_path(path="$.result.working_tree_dir", matches="/repo$")
- returns: the repository handle for `path`
- verify: json_path(path="$.result.type", equals="Repo")
- code: `workflows/src/workhorse_workflows/kit/git.py::open_repo`

### origin_url

- sig: `origin_url(path: str | Path) -> str | None`
- does: returns the URL of the remote named `origin`
- verify: json_path(path="$.result", equals="https://example.com/repo.git")
- returns: `None` when the repository is invalid, Git fails, or no `origin` remote exists
- verify: json_path(path="$.result", equals=None)
- code: `workflows/src/workhorse_workflows/kit/git.py::origin_url`

### local_branch_exists

- sig: `local_branch_exists(path: str | Path, branch: str) -> bool`
- does: checks whether `branch` matches a local branch name
- verify: json_path(path="$.result", equals=true)
- returns: `true` when the local branch exists, otherwise `false`, including Git failure
- verify: json_path(path="$.result", equals=false)
- code: `workflows/src/workhorse_workflows/kit/git.py::local_branch_exists`

### branch_exists

- sig: `branch_exists(path: str | Path, ref: str) -> bool`
- does: checks whether `ref` resolves in the repository
- verify: json_path(path="$.result", equals=true)
- returns: `true` when Git verifies `ref`, otherwise `false`
- verify: json_path(path="$.result", equals=false)
- code: `workflows/src/workhorse_workflows/kit/git.py::branch_exists`

### current_branch

- sig: `current_branch(path: str | Path) -> str`
- does: reads the active branch name
- verify: json_path(path="$.result", equals="feature")
- returns: the active branch name, or `"main"` for detached HEAD, an empty name, or Git failure
- verify: json_path(path="$.result", matches="^(feature|main)$")
- code: `workflows/src/workhorse_workflows/kit/git.py::current_branch`

### active_branch

- sig: `active_branch(path: str | Path) -> str | None`
- does: reads the active branch without substituting a trunk name
- verify: json_path(path="$.result", equals="feature")
- returns: the active branch name, or `None` for detached HEAD, an empty name, or Git failure
- verify: json_path(path="$.result", matches="^(feature|None)$")
- code: `workflows/src/workhorse_workflows/kit/git.py::active_branch`

### checkout

- sig: `checkout(path: str | Path, branch: str, *, create: bool = False, reset: bool = False) -> bool`
- does: checks out `branch`
- verify: json_path(path="$.result", equals=true)
- does: creates `branch` with `-b` when `create` is true
- verify: created(subject="the requested branch")
- does: creates or resets `branch` to the current HEAD with `-B` when `reset` is true, taking precedence over `create`
- verify: json_path(path="$.result", equals=true)
- returns: `true` after checkout succeeds, otherwise `false`
- code: `workflows/src/workhorse_workflows/kit/git.py::checkout`

### branch_owner

- sig: `branch_owner(path: str | Path, branch: str) -> str | None`
- does: scans Git worktree porcelain output for the worktree currently holding `branch`
- verify: json_path(path="$.result", matches="^/.+")
- returns: the owning worktree path when a worktree holds `branch`
- verify: json_path(path="$.result", matches="^/.+")
- returns: `None` when no matching worktree or Git result exists
- verify: json_path(path="$.result", equals=None)
- code: `workflows/src/workhorse_workflows/kit/git.py::branch_owner`

### branch_merged

- sig: `branch_merged(path: str | Path, branch: str, base: str) -> bool`
- does: treats `branch` as merged when it is an ancestor of `base` or its content is identical to `base`
- verify: json_path(path="$.result", equals=true)
- does: tries `base` and then `origin/base` when `base` is an unqualified branch name
- verify: json_path(path="$.result", equals=true)
- returns: `true` for ancestry or unchanged squash-merged content, otherwise `false`
- verify: json_path(path="$.result", equals=false)
- code: `workflows/src/workhorse_workflows/kit/git.py::branch_merged`

### commits_ahead

- sig: `commits_ahead(path: str | Path, branch: str, base: str) -> int`
- does: counts commits reachable from `branch` but not from `origin/base`
- verify: count(subject="commits reachable from branch but not from origin/base", equals=2)
- returns: the count, or `-1` when the range cannot be resolved
- verify: json_path(path="$.result", equals=-1)
- code: `workflows/src/workhorse_workflows/kit/git.py::commits_ahead`

### commit_paths

- sig: `commit_paths(path: str | Path, message: str, *pathspecs: str) -> bool`
- does: returns `false` without staging when no pathspecs are supplied
- does: returns `false` when the named scope has no working-tree changes
- does: stages and commits only the named pathspecs
- raises: `GitCommandError` when Git refuses staging or the commit
- returns: `true` when a commit is created, otherwise `false` for an empty scope or non-repository path
- verify: count(subject="paths committed by the scoped helper", equals=1)
- code: `workflows/src/workhorse_workflows/kit/git.py::commit_paths`
- tests: `workflows/tests/test_kit_git.py::test_commit_paths_stages_only_the_named_paths`
- tests: `workflows/tests/test_kit_git.py::test_commit_paths_with_no_pathspecs_commits_nothing`
- tests: `workflows/tests/test_kit_git.py::test_a_refused_commit_raises_instead_of_reading_as_an_empty_one`

### commit_all

- sig: `commit_all(path: str | Path, message: str) -> bool`
- does: stages every working-tree change with `git add -A`
- raises: `GitCommandError` when Git refuses staging or the commit
- returns: `true` when a commit is created, otherwise `false` for a clean tree or non-repository path
- verify: count(subject="whole-tree commits created by the sweeping helper", equals=1)
- code: `workflows/src/workhorse_workflows/kit/git.py::commit_all`
- tests: `workflows/tests/test_kit_git.py::test_commit_all_still_sweeps_the_whole_tree`
- tests: `workflows/tests/test_kit_git.py::test_a_refused_commit_raises_instead_of_reading_as_an_empty_one`

### head_sha

- sig: `head_sha(path: str | Path, ref: str = "HEAD") -> str`
- does: resolves the full SHA for `ref`
- verify: json_path(path="$.result", matches="^[0-9a-f]{40}$")
- returns: the full SHA, or an empty string when `ref` is unresolved, including an unborn HEAD
- verify: json_path(path="$.result", equals="")
- code: `workflows/src/workhorse_workflows/kit/git.py::head_sha`

### short_sha

- sig: `short_sha(path: str | Path, ref: str = "HEAD") -> str`
- does: resolves the abbreviated SHA for `ref`
- verify: json_path(path="$.result", matches="^[0-9a-f]{7,40}$")
- returns: the abbreviated SHA, or an empty string when `ref` is unresolved
- verify: json_path(path="$.result", equals="")
- code: `workflows/src/workhorse_workflows/kit/git.py::short_sha`

### rename_branch

- sig: `rename_branch(path: str | Path, old: str, new: str) -> bool`
- does: renames local branch `old` to `new`
- verify: keys_unchanged(subject="local branch refs")
- returns: `true` on success, otherwise `false`
- verify: json_path(path="$.result", equals=true)
- code: `workflows/src/workhorse_workflows/kit/git.py::rename_branch`

### restore_paths

- sig: `restore_paths(path: str | Path, *pathspecs: str) -> bool`
- does: discards working-tree changes for the supplied pathspecs
- verify: removed(subject="working-tree changes for the supplied pathspecs")
- does: performs no operation when no pathspecs are supplied
- verify: json_path(path="$.result", equals=false)
- returns: `true` when Git restores the paths, otherwise `false`
- verify: json_path(path="$.result", equals=true)
- code: `workflows/src/workhorse_workflows/kit/git.py::restore_paths`

### default_branch

- sig: `default_branch(path: str | Path) -> str | None`
- does: resolves `origin/HEAD` and removes its `origin/` prefix
- verify: json_path(path="$.result", equals="main")
- returns: the remote default branch name, or `None` when the symbolic ref is unavailable
- verify: json_path(path="$.result", equals=None)
- code: `workflows/src/workhorse_workflows/kit/git.py::default_branch`

### merge_base

- sig: `merge_base(path: str | Path, *refs: str) -> str | None`
- does: resolves the best common ancestor of all supplied refs
- verify: json_path(path="$.result", matches="^[0-9a-f]{40}$")
- returns: the merge-base SHA, or `None` when Git cannot resolve one
- verify: json_path(path="$.result", equals=None)
- code: `workflows/src/workhorse_workflows/kit/git.py::merge_base`

### trunk_base

- sig: `trunk_base(path: str | Path) -> str`
- does: finds the first candidate in `TRUNK_CANDIDATES` with a merge base against `HEAD`
- verify: json_path(path="$.result", matches="^[0-9a-f]{40}$")
- returns: the merge-base SHA when a trunk candidate resolves
- verify: json_path(path="$.result", matches="^[0-9a-f]{40}$")
- returns: `"HEAD~1"` when no trunk candidate resolves
- verify: json_path(path="$.result", equals="HEAD~1")
- code: `workflows/src/workhorse_workflows/kit/git.py::trunk_base`

### merge_ref

- sig: `merge_ref(path: str | Path, ref: str) -> bool`
- does: merges `ref` into the current branch without opening an editor
- verify: json_path(path="$.result", equals=true)
- does: aborts the merge after any Git failure before returning
- verify: unchanged(subject="repository working tree and index")
- returns: `true` on success, otherwise `false`
- verify: json_path(path="$.result", equals=false)
- code: `workflows/src/workhorse_workflows/kit/git.py::merge_ref`

### is_ancestor

- sig: `is_ancestor(path: str | Path, ancestor: str, descendant: str) -> bool`
- does: checks whether `ancestor` is reachable from `descendant`
- verify: json_path(path="$.result", equals=true)
- returns: `true` when Git confirms reachability, otherwise `false`
- verify: json_path(path="$.result", equals=false)
- code: `workflows/src/workhorse_workflows/kit/git.py::is_ancestor`

### show_file

- sig: `show_file(path: str | Path, ref: str, relpath: str) -> str | None`
- does: reads `relpath` from the tree identified by `ref`
- returns: the file contents, or `None` when the file or ref cannot be read
- verify: json_path(path="$.result", equals=None)
- code: `workflows/src/workhorse_workflows/kit/git.py::show_file`

### diff_text

- sig: `diff_text(path: str | Path, *args: str) -> str`
- does: runs Git diff with the caller-provided arguments
- verify: json_path(path="$.result", matches="^diff --git ")
- returns: raw diff output, or an empty string when Git fails
- verify: json_path(path="$.result", equals="")
- code: `workflows/src/workhorse_workflows/kit/git.py::diff_text`

### list_tracked_files

- sig: `list_tracked_files(path: str | Path, *pathspecs: str) -> list[str]`
- does: lists tracked repository-relative files, optionally constrained by pathspecs
- verify: json_path(path="$.result", equals=["tracked/README.md"])
- returns: non-empty output lines, or an empty list when Git fails
- verify: json_path(path="$.result", equals=[])
- code: `workflows/src/workhorse_workflows/kit/git.py::list_tracked_files`

### remote_urls

- sig: `remote_urls(path: str | Path, name: str = "origin") -> list[str]`
- does: reads the push URL and fetch URL for `name` in that order
- verify: json_path(path="$.result", equals=["https://push.example/repo.git", "https://fetch.example/repo.git"])
- does: de-duplicates non-empty URLs while preserving their first-seen order
- verify: json_path(path="$.result", equals=["https://example.com/repo.git"])
- returns: the ordered URL list, or an empty list when the remote or repository is unavailable
- verify: json_path(path="$.result", equals=[])
- code: `workflows/src/workhorse_workflows/kit/git.py::remote_urls`

### set_identity

- sig: `set_identity(path: str | Path, name: str, email: str) -> bool`
- does: writes repository-local `user.name` and `user.email`
- verify: persists(subject="repository-local Git identity")
- returns: `true` after both values are written, otherwise `false`
- verify: json_path(path="$.result", equals=true)
- code: `workflows/src/workhorse_workflows/kit/git.py::set_identity`

### allow_all_directories

- sig: `allow_all_directories() -> None`
- does: best-effort adds `*` to Git's global `safe.directory` list
- verify: json_path(path="$.safe_directory_wildcard", equals=true)
- returns: `None` whether or not Git accepts the global configuration change
- verify: json_path(path="$.result", equals=None)
- code: `workflows/src/workhorse_workflows/kit/git.py::allow_all_directories`

### clone

- sig: `clone(url: str, dest: str | Path, *, branch: str | None = None, single_branch: bool = True, ssh_command: str = "") -> bool`
- does: clones `url` into `dest`, optionally selecting `branch` and limiting history to one branch
- verify: created(subject="destination clone with selected branch and single-branch history")
- does: applies `ssh_command` only to this clone when it is non-empty
- verify: json_path(path="$.clone.ssh_command_scope", equals="clone-only")
- returns: `true` when cloning succeeds, otherwise `false`
- verify: json_path(path="$.result", equals=true)
- code: `workflows/src/workhorse_workflows/kit/git.py::clone`

### fetch_reset

- sig: `fetch_reset(path: str | Path, branch: str, *, remote: str = "origin") -> bool`
- does: fetches `remote`, checks out `branch`, and hard-resets it to `remote/branch`
- verify: json_path(path="$.result", equals=true)
- returns: `true` when all three operations succeed, otherwise `false`
- verify: json_path(path="$.result", equals=false)
- code: `workflows/src/workhorse_workflows/kit/git.py::fetch_reset`

### push_to_origin

- sig: `push_to_origin(path: str | Path, branch: str, *, remote: str = "origin", force_with_lease: bool = False) -> bool`
- does: pushes `branch` to `remote` using the checkout's ambient credentials
- verify: persists(subject="remote branch tip")
- does: adds `--force-with-lease` only when `force_with_lease` is true
- verify: conflict_on_stale(subject="remote branch", token="expected remote tip")
- returns: `true` on a successful push, otherwise `false`
- verify: json_path(path="$.result", equals=true)
- code: `workflows/src/workhorse_workflows/kit/git.py::push_to_origin`
