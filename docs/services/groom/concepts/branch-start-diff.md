---
type: concept
slug: branch-start-diff
title: Branch start diff
---
# Branch start diff

The branch start diff is the change of one checkout since its branch started: the working tree against the commit where the checkout's branch left the default branch. The run [Diff tab](run-diff-tab.md) offers it beside the uncommitted change. The sidecar computes it with `git`, and the host passes the reply through [GET /diff/{container_id}](../http/groom.md#get-working-tree-diff). This page holds the decisions behind the read, so a later change to the default-branch order, to the reply or to the git calls can check them in one place. The data shape is [workspace diff data](../formats/workspace-diff-data.md).

- code: groom/groom/gitdiff.py::branch_start@a9238fe68b8e
- code: groom/groom/gitdiff.py::read_branch_local@66fa6eddc2a9
- code: groom/groom/gitdiff.py::_default_branch@e9d109fe680b
- code: groom/groom/gitdiff.py::_git@f952fc5bea78
- code: groom/groom/sidecar.py::_git_diff@4a6396f4f32c
- code: groom/groom/app.py::diff@3b4a38e8e9ca
- code: groom/groom/app.py::_branch_start@06e790f82049
- rule: the base is the merge base of `HEAD` and the default branch, so the view shows the whole change the branch made, committed and uncommitted, and none of what the default branch gained since.
- rule: the default branch is found in this order: the ref `origin/HEAD` names, then a local `main`, then a local `master`. The first that resolves to a commit wins, and a ref that names nothing is skipped.
- rule: the default branch is found from local refs only, and the read never fetches, because the sidecar must not touch the network or the remote.
- rule: a checkout whose current branch is the default branch has no branch of its own. The reply says `default-branch` with an empty diff, and the Diff tab says so, because the merge base of a branch with itself is its own tip and would read as no change.
- rule: a checkout with no default branch to find, or none that shares history with `HEAD`, has no base. The reply says `not-found` with an empty diff and the Diff tab says where the branch started could not be found, because guessing a base would show a wrong change.
- rule: a git failure, a missing checkout or a timeout fails the read. `failed` is true, and no consumer shows it as no change.
- rule: the view is `git diff <base>`, the working tree against the base, and the untracked files come from the same listing as the uncommitted view, in the same group, and are not counted in the tab's size.
- rule: reading never writes the checkout's index. The sidecar reads a checkout an agent is writing, so every git call runs with `--no-optional-locks` and `diff.autoRefreshIndex=false`, because the first alone still lets `git diff` refresh the index.
- rule: `getDiff` with no `view` returns exactly the members it returned before this view existed, so an older host and a newer sidecar still agree.
- rule: the reply to the branch view adds `base`, `base_ref`, `base_branch` and `base_reason`. An empty `base_reason` with a `base` means found, and `default-branch` and `not-found` are the two reasons there is none.
- rule: `/diff/{container_id}` marks a branch reply `based` true when the sidecar sent `base_reason`, and false otherwise. A `based` false reply comes from a sidecar too old to know the view, and the tab says so instead of showing the uncommitted diff as the view.
- rule: the view travels as the query and RPC parameter `view`, because `scope` is reserved by the web framework.
- rule: the branch view is never answered from a volume or a native checkout. Without a connected sidecar the reply is unreadable, because the fallback readers run only the uncommitted commands.
- verify: absent(subject="a diff for a checkout on its default branch")
- tests: groom/tests/test_gitdiff.py::test_a_feature_branch_reads_the_whole_change_from_its_merge_base
- tests: groom/tests/test_gitdiff.py::test_the_ref_origin_head_names_comes_before_a_local_main
- tests: groom/tests/test_gitdiff.py::test_a_local_main_comes_before_a_local_master
- tests: groom/tests/test_gitdiff.py::test_reading_either_view_leaves_the_index_and_the_refs_of_the_checkout_unchanged
- tests: groom/tests/test_sidecar_session.py::test_a_get_diff_with_no_view_returns_exactly_the_uncommitted_reply
- tests: groom/tests/test_app.py::test_diff_endpoint_never_answers_the_branch_view_from_a_volume
- tests: groom/tests/test_app.py::test_diff_endpoint_says_a_sidecar_that_reports_no_base_is_too_old_for_the_branch_view
- tests: groom/tests/test_gitdiff.py::test_a_checkout_on_its_default_branch_has_no_branch_of_its_own
- tests: groom/tests/test_gitdiff.py::test_a_checkout_with_no_default_branch_has_no_findable_start
