---
type: concept
slug: artifacts-layout
title: Artifacts layout and the docs home
---
# Artifacts layout and the docs home

Every agent working on one repository reads and files its documents in one folder, whatever
shape the repository reaches it in: the member folder, a worktree of it, or a clone of its
URL. That folder is the repository's docs home.

The home config names groups of repositories in its `[workspaces]` table. A workspace entry is a
path or a table with a `path`, an optional `name`, an optional `url` and an optional `branch`.
A repository's identity holds three facts: its folder, the main folder of its worktree (the
parent of `git rev-parse --git-common-dir`), and its `origin` URL, empty when it has none. A
folder outside any git repository is its own identity and matches by path only.

A repository is a member of the workspace table when its folder or its main worktree folder
equals a member's configured path, or its origin URL equals a member's `url`. Both paths are
resolved. Both URLs are compared with any trailing `/` and `.git` removed. A member of any
workspace makes the repository a member, so a worktree cut for a run and a clone made outside any
run both resolve to the member they came from. The match runs once per command, with one
`git rev-parse` call and one `git remote get-url` call.

The docs home of a member is the artifacts dir. The docs home of any other repository is the
repository itself, found by walking up from the folder the command starts in. No environment
variable chooses a workspace. `workhorse run --workspace NAME` validates the name, creates the
artifacts repo and passes `workspace` to the workflow, and it changes nothing about where a
document goes.

A run that resolves `repo://<member>/<path>` citations reads the union of every workspace's
members as `{name: folder}`, overridden by any explicit `--checkout`. That union is unambiguous
because the home config refuses a member name bound to two folders.

- code: `core/stablemate_core/config.py::docs_home` @ff8a02ce3c68
- code: `core/stablemate_core/config.py::repository_identity` @ff8a02ce3c68
- code: `core/stablemate_core/config.py::RepositoryIdentity` @ff8a02ce3c68
- code: `core/stablemate_core/config.py::is_workspace_member` @ff8a02ce3c68
- code: `core/stablemate_core/config.py::workspace_members` @ff8a02ce3c68
- code: `ostler/ostler/provenance.py::effective_checkouts` @731cc1e22714
- rule: a repository listed in any workspace uses the artifacts dir as its docs home, and any other repository uses itself
- rule: all workspaces share one artifacts dir, and workspaces may overlap, because any match makes a repository a member and the docs home is the same either way
- rule: one member name maps to one folder across every workspace, and a home config that binds a name to two folders is refused with an error naming both folders
- rule: a worktree and a clone of a member's URL resolve to the member they came from, so every agent on one repository gets the same docs home
- tests: `core/tests/test_workspaces.py::test_docs_home_is_the_artifacts_dir_from_a_member_folder`
- tests: `core/tests/test_workspaces.py::test_docs_home_is_the_artifacts_dir_from_a_worktree_of_a_member`
- tests: `core/tests/test_workspaces.py::test_docs_home_is_the_artifacts_dir_from_a_clone_of_a_member_url`
- tests: `core/tests/test_workspaces.py::test_docs_home_is_none_for_a_repository_in_no_workspace`
- tests: `core/tests/test_workspaces.py::test_one_member_name_bound_to_two_folders_raises`
