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

A decision is a folder under the docs home: `docs/decisions/<slug>/decision.md`. Its frontmatter holds
`repo`, `status` (`accepted`) and `summary`, and its body holds `## Question`, `## Decided`,
`## Grounded in` and `## Context` in that order. Diagrams and images may sit beside it.
`ostler decisions add <slug> --summary "<line>"` files it empty and prints its path, and the
caller fills the sections. `--repo` defaults to the workspace member name of the repository
holding the working folder, and to that repository's normalised folder name when it is in no
workspace. The command does not commit: in a workspace the artifacts repo tracks `docs/`, and in a
repository outside any workspace the agent commits the file with its own change.

The docs home of a member is the artifacts dir. The docs home of any other repository is the
repository itself, found by walking up from the folder the command starts in. No environment
variable chooses a workspace. `workhorse run --workspace NAME` validates the name, creates the
artifacts repo and passes `workspace` to the workflow, and it changes nothing about where a
document goes.

A run that resolves `repo://<member>/<path>` citations reads the union of every workspace's
members as `{name: folder}`, overridden by any explicit `--checkout`. That union is unambiguous
because the home config refuses a member name bound to two folders.

- code: `core/stablemate_core/config.py::docs_home` @b2fcdfeb41a0
- code: `core/stablemate_core/config.py::repository_identity` @b2fcdfeb41a0
- code: `core/stablemate_core/config.py::RepositoryIdentity` @b2fcdfeb41a0
- code: `core/stablemate_core/config.py::is_workspace_member` @b2fcdfeb41a0
- code: `core/stablemate_core/config.py::repository_name` @b2fcdfeb41a0
- code: `core/stablemate_core/config.py::workspace_members` @b2fcdfeb41a0
- code: `ostler/ostler/decisions.py::add` @85bc946b227c
- code: `ostler/ostler/provenance.py::effective_checkouts` @731cc1e22714
- rule: a repository listed in any workspace uses the artifacts dir as its docs home, and any other repository uses itself
- rule: all workspaces share one artifacts dir, and workspaces may overlap, because any match makes a repository a member and the docs home is the same either way
- rule: one member name maps to one folder across every workspace, and a home config that binds a name to two folders is refused with an error naming both folders
- rule: a worktree and a clone of a member's URL resolve to the member they came from, so every agent on one repository gets the same docs home
- rule: a decision lives at `docs/decisions/<slug>/decision.md` under the docs home, so every agent on one repository files and reads decisions in one folder
- rule: the slug is the folder name and is what `ostler search` matches, so it is short kebab-case: lowercase letters, digits and single hyphens, at most 60 characters
- rule: the decision's own folder holds attachments such as diagrams and images beside `decision.md`
- rule: a decision names its repository in its `repo` frontmatter, never in its path
- rule: a slug whose folder already exists is refused, so two decisions never share a slug
- rule: a repository outside every workspace keeps `docs/decisions` in the repository itself
- tests: `core/tests/test_workspaces.py::test_docs_home_is_the_artifacts_dir_from_a_member_folder`
- tests: `core/tests/test_workspaces.py::test_docs_home_is_the_artifacts_dir_from_a_worktree_of_a_member`
- tests: `core/tests/test_workspaces.py::test_docs_home_is_the_artifacts_dir_from_a_clone_of_a_member_url`
- tests: `core/tests/test_workspaces.py::test_docs_home_is_none_for_a_repository_in_no_workspace`
- tests: `core/tests/test_workspaces.py::test_one_member_name_bound_to_two_folders_raises`
- tests: `ostler/tests/test_decisions.py::test_add_writes_the_shape_and_prints_the_path`
- tests: `ostler/tests/test_decisions.py::test_a_taken_slug_is_refused_and_leaves_the_file_alone`
- tests: `ostler/tests/test_decisions.py::test_a_worktree_of_a_member_files_in_the_same_folder_under_the_member_name`
- tests: `workflows/tests/coder/shared/test_decision_home.py::test_a_run_and_a_session_resolve_the_same_decisions_folder`
- tests: `workflows/tests/coder/shared/test_decision_home.py::test_search_returns_a_decision_filed_by_either_agent`
