---
type: concept
slug: workflow-kit-export-surface
title: Workflow kit export surface
---
# Workflow kit export surface

`workhorse_workflows.kit` is the workflow-side helper facade. It exposes the Git, GitHub,
workspace, path, JSON, inbox, and external-tool operations implemented by its sibling modules
without making workflow nodes import a particular implementation module. Attribute access resolves
the defining module at access time, so a test that patches that module continues to affect a node
that imports a helper from this facade. The facade itself owns no Git, network, filesystem, or
subprocess behavior.

- code: `workflows/src/workhorse_workflows/kit/__init__.py::__getattr__`

## Methods

### __getattr__

- sig: `__getattr__(name: str) -> object`
- does: resolves a declared facade name from its defining kit submodule on every attribute access
- raises: raises `AttributeError` when the requested name is not in the facade's declared export map
- returns: the current attribute value declared by the selected submodule
- verify: absent(subject="unknown workflow kit facade attribute")
- code: `workflows/src/workhorse_workflows/kit/__init__.py::__getattr__`

### __dir__

- sig: `__dir__() -> list[str]`
- does: exposes exactly the facade's declared export names for introspection
- returns: the sorted facade export names
- verify: count(subject="workflow kit facade export names", equals=49)
- code: `workflows/src/workhorse_workflows/kit/__init__.py::__dir__`

## Git operations

Imported from `kit.git`:

- `active_branch` — current branch name
- `allow_all_directories` — git config to allow all directories
- `branch_exists` — check if a branch exists locally or remotely
- `branch_merged` — check if a branch has been merged to the base
- `branch_owner` — extract branch owner from branch name
- `checkout` — check out a branch or commit
- `clone` — clone a repository
- `commit_all` — stage and commit all changes
- `commit_paths` — stage and commit specified paths
- `commits_ahead` — count commits ahead of base
- `current_branch` — get the currently checked-out branch
- `default_branch` — get the repository's default branch
- `diff_text` — get diff as plain text
- `fetch_reset` — fetch and reset to origin
- `GitError` — exception raised when git operations fail
- `head_sha` — get the current HEAD commit SHA
- `is_ancestor` — check if one commit is an ancestor of another
- `list_tracked_files` — list all tracked files in the repository
- `local_branch_exists` — check if a branch exists locally
- `merge_base` — find the merge base between two commits
- `merge_ref` — merge a reference into the current branch
- `open_repo` — open a git repository
- `origin_url` — get the origin remote URL
- `push_to_origin` — push the current branch to origin
- `remote_urls` — get all configured remote URLs
- `rename_branch` — rename a branch
- `restore_paths` — discard changes to specified paths
- `set_identity` — configure git user identity
- `short_sha` — get a short form of a commit SHA
- `show_file` — display a file at a specific commit
- `trunk_base` — get the trunk/main branch reference

## GitHub operations

Imported from `kit.github`:

- `find_open_pr` — find an open pull request by criteria
- `github_client` — authenticated GitHub API client
- `push_branch` — push a branch and create or update a pull request
- `repo_full_name_from_url` — extract repo owner and name from a URL
- `resolve_github_token` — get the GitHub API token
- `resolve_repo` — get a GitHub repository object
- `sync_to_origin` — synchronize local branch with origin

## Workspace operations

Imported from `kit.workspace`:

- `build_dispatch_list` — build a list of repositories to process
- `checkout_workspace` — check out the workspace at a specific commit
- `get_affected_repos` — get repositories affected by a change
- `get_repo_config` — get repository configuration
- `resolve_workspace` — resolve the workspace path

## Path operations

Imported from `kit.paths`:

- `find_docs_root` — locate the documentation directory
- `find_repo_root` — locate the repository root

## JSON operations

Imported from `kit.jsonio`:

- `load_json` — load a JSON file
- `load_jsonc` — load a JSON file with comments

## Inbox operations

Imported from `kit.inbox`:

- `poll_run_inbox` — poll for incoming run messages

## External tool operations

Imported from `kit.tools`:

- `run_tool` — run an external tool with arguments

## Implementation contracts

- detail: [Workflow kit GitHub](workflow-kit-github.md)
- detail: [Workflow kit inbox](workflow-kit-inbox.md)
- detail: [Workflow kit JSON I/O](workflow-kit-jsonio.md)
- detail: [Workflow kit telemetry](workflow-kit-telemetry.md)
