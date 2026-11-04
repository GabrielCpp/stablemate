---
type: concept
slug: worktree-sweep
title: Worktree sweep
---
# Worktree sweep

An agent session that cuts a linked worktree can end without removing it, and the folder then
sits on disk with nobody to judge it. `farrier worktrees` judges those folders by one test: would
removing this lose anything? A [workhorse run](../../workhorse/concepts/run-launch.md) applies the
same test to its own worktree when it ends, so a worktree goes under the same terms either way.

Each line of the listing names the action, the path, the branch and the reason:

| action | meaning |
| --- | --- |
| `remove` | a listing's mark: the work landed and the command would remove it |
| `removed` | `--apply` removed it |
| `keep` | it stays, for the reason shown |
| `prune` | a listing's mark: its folder is gone and only git's entry remains |
| `pruned` | `--apply` cleared that entry |

- code: `core/stablemate_core/worktree.py::assess` @da667fb53279
- code: `core/stablemate_core/worktree.py::retire` @a0944a20afec
- code: `farrier/farrier/worktree_sweep.py::discover_repos` @a3cce4902b88
- code: `farrier/farrier/worktree_sweep.py::process_cwds` @5e48c214140a
- rule: a worktree goes only when its tree is clean and every commit on it is merged into the branch the main checkout has out, or pushed to a remote
- rule: ignored files do not count as changes, so they go with the worktree, because a worktree's ignored files are build output in the common case
- rule: a branch goes only when it is merged, so a pushed but unmerged branch stays after its worktree goes
- rule: the main checkout is never a candidate
- rule: a locked worktree stays, and `git worktree lock` is how an agent or an operator says a kept worktree is deliberate
- rule: a worktree a running process is using stays, whatever else is true of it
- rule: where the platform has no `/proc`, every worktree stays, because the command cannot see which processes use it
- rule: a worktree whose git state changed within the idle window stays, because a clean tree a session has just checked out looks exactly like one it abandoned
- rule: the idle clock reads the worktree's own `HEAD`, `index` and reflog, so looking at a worktree with the command never restarts it
- rule: the command lists by default and removes only under `--apply`, because the removal is not reversible
- tests: `farrier/tests/test_worktree_sweep.py::test_listing_marks_a_landed_worktree_and_changes_nothing`
- tests: `farrier/tests/test_worktree_sweep.py::test_listing_does_not_reset_the_idle_clock`
- tests: `farrier/tests/test_worktree_sweep.py::test_platform_that_cannot_see_processes_removes_nothing`
