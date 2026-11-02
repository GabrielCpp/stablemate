---
type: concept
slug: run-diff-tab
title: Run Diff tab
---
# Run Diff tab

The run Diff tab shows the uncommitted change of one live container run, or the change since its branch started, beside the Overview and Details tabs in the [groom dashboard](../gui/screens/groom-dashboard.md). The [detail Diff tab](../gui/screens/groom-dashboard.md#detail-diff-tab) holds the screen contract. This page holds the decisions behind it, so a later change to the tab, to the `/diff/` reply or to the sidecar `getDiff` reply can check them in one place. The change since the branch started is computed as [branch start diff](branch-start-diff.md) describes. The data shape is [workspace diff data](../formats/workspace-diff-data.md), and the operator path is [operator inspects working-tree diff](../flows/operator-inspects-working-tree-diff.md).

- code: groom/groom/assets/dashboard.js::DiffTab@8ed2100fd582
- code: groom/groom/assets/dashboard.js::useRunDiff@42e89852f3e2
- code: groom/groom/assets/dashboard.js::loadRunDiff@6b1e2d0423d6
- code: groom/groom/projection.py::run_row@f4041c085d72
- code: groom/groom/gitdiff.py::parse@3a6aaa904d86
- code: groom/groom/gitdiff.py::read_local@f444995ad07c
- code: groom/groom/gitdiff.py::read_branch_local@66fa6eddc2a9
- code: groom/groom/assets/dashboard.js::DiffViewSwitch@6de2b73f3db9
- code: groom/groom/assets/dashboard.js::selectDiffView@977e018d4f66
- code: groom/groom/assets/dashboard.js::BranchStartNotice@95b98f3f8489
- code: groom/groom/app.py::diff@09402337f758
- rule: the Diff tab exists only for a run whose row says `sidecar` is true, and `sidecar` is read from the sidecar hub when the row is projected, because only a connected sidecar can read a live container's checkout.
- rule: a native run, a finished run, and a container run without a connected sidecar have no Diff tab.
- rule: the dashboard reads the diff once when a run with a connected sidecar is selected, and once more when a sidecar connects while its run is selected.
- rule: unselected rows cost no diff read.
- rule: the tab shows the `+N −M` size of the tracked change before it is opened, so the operator sees whether a change exists without opening the tab.
- rule: untracked files are listed in their own group and are not counted in the tab's size, because git has no diff for them.
- rule: a read that did not happen is never shown as no changes. A `failed` reply, a rejected fetch, and non-empty text that diff2html cannot parse all show the unreadable message with a retry control.
- rule: either git command failing fails the whole read, because a diff without its untracked listing would claim a partial truth.
- rule: a sidecar with no checkout to read reports `failed` true, not an empty diff.
- rule: a reply without a `failed` member comes from a sidecar too old to report failure, and an empty diff from it says the tab cannot confirm there are no changes.
- rule: `getDiff` keeps its `diff` field, and `untracked` and `failed` are added beside it, so a consumer that reads only `diff` keeps working.
- rule: a refresh keeps the old content on screen and marks the bar `reading…`, so a slow read does not blank the tree.
- rule: the tab says when the diff was read, as a clock time and an age that ticks each second.
- rule: a chain of single-child folders is one tree row in the run Diff tab.
- rule: the file header above the lines is the tab's own, with the path, the counts, the word `uncommitted` and a words-based `new file`, `deleted file` or rename note, because diff2html's card header carries a badge and no scope.
- rule: the diff sits on the pane's own background with no card border, the hunk header is a plain tinted row, and removed and added lines tint their rows and their text.
- rule: the run header shows a `docker · sidecar` chip while a connected sidecar backs the run.
- rule: the default file is the first changed file in the tree's display order, and a refresh keeps the selected file by path.
- rule: when the run ends while Diff is open, the tab goes and the Overview tab shows.
- rule: when the sidecar drops while the page holds a diff for the run, the Diff tab stays, marked stale in words, as [kept run diff](kept-run-diff.md) describes. When the page holds none, the tab goes and the Overview tab shows if Diff was open, and a later reconnect does not reopen Diff on its own.
- rule: the `/diff/` reply carries `served`, `sidecar` or `volume`, and a `volume` reply never replaces a kept diff.
- rule: the sidecar hub's unregister is followed by a shell broadcast, so open dashboards learn of a disconnect at once.
- rule: the Diff tab opens on Uncommitted, and the run's switch position is held in the page's snapshot per run, so a refresh, a tab change, a checkout change, or selecting another run and coming back keeps each run's own position. A reload starts at Uncommitted.
- rule: the switch is a group named `Diff view` of two pressed buttons, `Uncommitted` and `Since branch start`, with the position in `aria-pressed` and shown by weight and an underline as well as by colour. It sits at the right of the tab bar before the checkout selector and the read time, and only on the Diff tab.
- rule: choosing a view reads that view once, naming the checkout, and a refresh reads the view in force. Moving between tabs reads nothing more.
- rule: the Since branch start view lists its changed files in the same tree as Uncommitted, with the same untracked group, and the tab's `+N −M` follows the view in force.
- rule: the file header in the Since branch start view says `since <7-character base> on <default branch>`, with the full commit and the ref it was found at in the hover title. The Uncommitted view says `uncommitted`.
- rule: a branch with no change since it started says `This branch has no change since it started at <base> on <branch>.` and the tab shows no count. A branch with only untracked files lists them and says no tracked file has changed since it started.
- rule: a checkout on its default branch, one whose branch start cannot be found, and a sidecar too old for the view each say so in the panel with Uncommitted still working, show no count, and never show another view's diff as this one. The not-found state offers `Retry now`.
- rule: an unreadable Since branch start read says `This view could not be read` and `This does not mean there is no change.`, offers `Retry now`, and clears when a read succeeds.
- rule: while the view is read the panel says `Reading the change since the branch started…` and the tab shows no count.
- rule: diff content is rendered by diff2html, which escapes file content, and the client sets no other markup from the diff.
- verify: absent(subject="the Diff tab for a run without a connected sidecar")
- verify: absent(subject="a count on the Diff tab for a branch with no change since it started")
- tests: groom/tests/test_checkout_selector_dynamic.py::test_the_diff_sits_on_the_pane_background_without_a_card_border_and_tints_changed_text
- tests: groom/tests/test_diff_tab_dynamic.py::test_a_container_run_with_a_connected_sidecar_has_a_diff_tab_beside_overview_and_details
- tests: groom/tests/test_diff_tab_dynamic.py::test_rows_that_are_not_selected_cost_no_diff_read
- tests: groom/tests/test_diff_tab_dynamic.py::test_the_tab_stays_marked_stale_when_the_sidecar_drops_while_diff_is_open
- tests: groom/tests/test_diff_tab_dynamic.py::test_a_dropped_sidecar_that_reconnects_clears_the_stale_mark_and_keeps_the_diff_tab
- tests: groom/tests/test_gitdiff.py::test_parse_marks_either_failing_command_as_failed
- tests: groom/tests/test_app.py::test_diff_from_an_old_sidecar_is_marked_as_unable_to_confirm
- tests: groom/tests/test_diff_since_branch_dynamic.py::test_the_diff_tab_opens_on_uncommitted_with_a_switch_that_sends_the_sidecar_no_new_parameter
- tests: groom/tests/test_diff_since_branch_dynamic.py::test_since_branch_start_shows_the_whole_change_names_its_base_and_the_size_and_tree_follow
- tests: groom/tests/test_diff_since_branch_dynamic.py::test_selecting_another_run_and_coming_back_keeps_each_runs_own_position
- tests: groom/tests/test_diff_since_branch_dynamic.py::test_the_switch_has_a_role_a_name_keyboard_operation_and_shows_its_position_by_more_than_color
- detail: [kept run diff](kept-run-diff.md)
