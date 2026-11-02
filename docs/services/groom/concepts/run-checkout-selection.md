---
type: concept
slug: run-checkout-selection
title: Run checkout selection
---
# Run checkout selection

A container run can hold more than one git checkout in its workspace. The run's Files and Diff tabs in the [groom dashboard](../gui/screens/groom-dashboard.md) show one checkout at a time, chosen with the [checkout selector](../gui/screens/groom-dashboard.md#detail-checkout-select). This page holds the decisions behind that choice, so a later change to the selector, to the `/diff/` and `/files/` replies or to the sidecar `getDiff` and `getTree` replies can check them in one place. The tabs are the [run Diff tab](run-diff-tab.md) and the [run Files tab](run-files-tab.md).

- code: groom/groom/assets/dashboard.js::CheckoutSelect@1dec79549bbb
- code: groom/groom/assets/dashboard.js::checkoutFor@4efc2c003f44
- code: groom/groom/assets/dashboard.js::selectCheckout@fe08d1478779
- code: groom/groom/sidecar.py::_repo_names@6414bfcac07e
- code: groom/groom/app.py::_checkout_names@534a9939c8cb
- rule: the sidecar adds a `repos` list, the names of the workspace's checkouts, to its `getDiff` and `getTree` replies, and `/diff/` and `/files/` pass it through. `/repos/{id}` stays unchanged for the terminal client.
- rule: `repos` is additive. A reply without it comes from a sidecar too old to name its checkouts, and the run shows no selector and reads the default checkout.
- rule: the dashboard learns the checkouts from the Diff or Files read it already makes, so the selector costs no extra read.
- rule: the selector shows only when the Files or Diff tab is open and the run has more than one checkout. A run with one checkout shows none.
- rule: the selector names the checkout and nothing else, and the workspace root, whose name is empty, reads `(workspace root)`.
- rule: the chosen checkout is held in the page's memory per run, beside the snapshot fields that keep tab state, and lasts as long as the page. A reload starts at the first checkout.
- rule: a run selected for the first time shows its first checkout, and selecting another run and coming back restores that run's earlier choice.
- rule: one choice governs the Files and Diff tabs of a run, so moving between the tabs keeps it and reads nothing more.
- rule: choosing a checkout reads that checkout's diff and, when the Files tab is shown, its tree, once each. The Diff tab's `+N −M` follows the choice, in the view in force.
- rule: choosing a checkout keeps the run's Diff view switch position, and the new checkout is read in that view. See [branch start diff](branch-start-diff.md).
- rule: choosing a checkout clears Files' selected file and its folder collapse state, because both belong to the checkout they were opened in.
- rule: a refresh keeps the chosen checkout, and every read names the checkout it reads, the diff, the tree and each file alike.
- rule: when the chosen checkout is not in the reply's `repos`, the tab falls back to the first checkout and reads it.
- rule: a read that failed keeps the selector, so the operator can leave an unreadable checkout.
- rule: the selector is a native select named `Checkout`, so it has a role, an accessible name and keyboard operation without script.
- rule: `j` and `k` do nothing while a text field, a textarea, a select or an editable region has focus, so choosing a checkout with the keys never moves the run selection.
- rule: the rail carries no Files or Diff control and no repository picker, and a mode with no pane in the page lands on Runs, never on a blank pane.
- rule: a native run has no Files or Diff tab and no other route to them, and its Overview shows its checkout path in the Run list, before its first node finishes as well as after.
- verify: absent(subject="the checkout selector for a run with one checkout")
- tests: groom/tests/test_checkout_selector_dynamic.py::test_a_run_with_several_checkouts_shows_a_selector_on_files_and_diff_only
- tests: groom/tests/test_checkout_selector_dynamic.py::test_a_run_with_one_checkout_shows_no_selector
- tests: groom/tests/test_checkout_selector_dynamic.py::test_a_sidecar_that_names_no_checkouts_shows_no_selector_and_reads_the_default_one
- tests: groom/tests/test_checkout_selector_dynamic.py::test_a_run_selected_for_the_first_time_shows_its_first_checkout
- tests: groom/tests/test_checkout_selector_dynamic.py::test_selecting_a_checkout_shows_its_change_and_its_tree_and_the_size_follows
- tests: groom/tests/test_checkout_selector_dynamic.py::test_one_selection_governs_files_and_diff_and_moving_between_them_reads_nothing_more
- tests: groom/tests/test_checkout_selector_dynamic.py::test_refreshing_the_diff_keeps_the_checkout_and_names_it_in_the_read
- tests: groom/tests/test_checkout_selector_dynamic.py::test_selecting_another_run_and_coming_back_restores_the_checkout_each_run_had
- tests: groom/tests/test_checkout_selector_dynamic.py::test_a_reload_starts_again_at_the_first_checkout
- tests: groom/tests/test_checkout_selector_dynamic.py::test_changing_the_checkout_clears_the_open_file_and_the_collapsed_folders_of_files
- tests: groom/tests/test_checkout_selector_dynamic.py::test_a_remembered_checkout_that_is_gone_falls_back_to_the_first_one_and_never_shows_an_empty_pane
- tests: groom/tests/test_checkout_selector_dynamic.py::test_an_unreadable_checkout_keeps_the_selector_so_the_operator_can_leave_it
- tests: groom/tests/test_checkout_selector_dynamic.py::test_the_selector_has_a_role_and_a_name_works_from_the_keyboard_and_passes_axe
- tests: groom/tests/test_checkout_selector_dynamic.py::test_j_and_k_with_the_selector_focused_do_not_move_the_run_selection
- tests: groom/tests/test_checkout_selector_dynamic.py::test_the_rail_has_no_files_diff_or_repository_picker_and_the_page_never_asks_for_the_repository_list
- tests: groom/tests/test_checkout_selector_dynamic.py::test_a_pane_that_no_longer_exists_lands_on_runs_and_never_on_a_blank_pane
- tests: groom/tests/test_checkout_selector_dynamic.py::test_a_native_run_has_no_route_to_files_or_a_diff_and_the_rail_offers_none
- tests: groom/tests/test_checkout_selector_dynamic.py::test_a_native_run_shows_its_checkout_path_on_overview_before_and_after_its_first_finished_node
- tests: groom/tests/test_diff_since_branch_dynamic.py::test_the_switch_keeps_its_position_when_another_checkout_is_selected
- tests: groom/tests/test_sidecar_session.py::test_rpc_get_tree_names_every_checkout_of_the_workspace_beside_the_one_it_read
- tests: groom/tests/test_sidecar_session.py::test_rpc_get_diff_names_every_checkout_of_the_workspace_even_when_the_read_failed
- tests: groom/tests/test_app.py::test_files_and_diff_pass_the_sidecars_checkout_list_through
