---
type: concept
slug: workflow-kit-workspace
title: Workflow kit workspace
---
# Workflow kit workspace

The workspace kit derives a single-repository workspace from the supplied repository directory,
not the workflow process's current directory, and does not let `agents.yml` rename that repository
key. Its checkout operation supports the default disposable clone and a host-backed worktree:
worktrees are detached, preserve committed and uncommitted work across a restart, prune stale
registrations, and refuse remote URLs because both sides must share the host path.

- code: `workflows/src/workhorse_workflows/kit/workspace.py::resolve_workspace`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::_git_network_command`
- code: `workflows/src/workhorse_workflows/kit/workspace.py::checkout_workspace`
- tests: `workflows/tests/test_kit_workspace.py::test_resolve_workspace_uses_the_repo_dir_argument_over_cwd`
- tests: `workflows/tests/test_kit_workspace.py::test_a_repo_is_named_by_its_directory_not_by_its_agents_yml`
- tests: `workflows/tests/test_kit_workspace.py::test_git_network_command_uses_configured_token_env`
- tests: `workflows/tests/test_kit_worktree.py::test_two_concurrent_runs_each_get_their_own_tree_of_one_repo`
- tests: `workflows/tests/test_kit_worktree.py::test_uncommitted_work_survives_a_restart_too`
- tests: `workflows/tests/test_kit_worktree.py::test_a_remote_url_is_refused_with_the_reason`
