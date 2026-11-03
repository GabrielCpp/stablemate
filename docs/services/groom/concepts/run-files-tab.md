---
type: concept
slug: run-files-tab
title: Run Files tab
---
# Run Files tab

The run Files tab shows the checkout of one live container run, read-only, beside the Overview, Activity and Diff tabs in the [groom dashboard](../gui/screens/groom-dashboard.md). The [detail Files tab](../gui/screens/groom-dashboard.md#detail-files-tab) holds the screen contract. This page holds the decisions behind it, so a later change to the tab, to the `/files/` and `/file/` replies or to the sidecar `getTree` and `getFile` replies can check them in one place. The data shapes are [workspace file list data](../formats/workspace-file-list-data.md) and [workspace file content data](../formats/workspace-file-content-data.md), and the sibling tab is the [run Diff tab](run-diff-tab.md).

- code: groom/groom/assets/dashboard.js::FilesTab@44ffdf1c1d9a
- code: groom/groom/assets/dashboard.js::RunFileView@91777ea958ea
- code: groom/groom/assets/dashboard.js::useRunFiles@9ef89b78abfa
- code: groom/groom/assets/dashboard.js::loadRunFiles@0928854e5520
- code: groom/groom/assets/dashboard.js::openRunFile@aa3dd1ae20a1
- code: groom/groom/assets/dashboard.js::fileCode@1925f7dd181c
- code: groom/groom/app.py::files@1a8049542599
- code: groom/groom/app.py::file_content@6a4a53a92140
- code: groom/groom/sidecar.py::_list_tree@f932858439aa
- code: groom/groom/sidecar.py::_rpc_get_file@b1b877af732b
- rule: the Files tab exists under the same condition as the Diff tab, a run whose row says `sidecar` is true, and it sits directly before Diff, so the tabs read Overview, Activity, Files, Diff.
- rule: a native run, a finished run, and a container run without a connected sidecar have no Files tab.
- rule: the dashboard reads the tree on the first open of Files for a run selection, never on selecting a run, so a run nobody opens Files on costs no tree read.
- rule: moving between tabs of the same run keeps the tree and the selected file and reads nothing new, and selecting another run resets both.
- rule: a gate that opens or is answered while the Files tab is open leaves the tab, the selected file and the scroll position alone and reads no tree or file, as [run gate strip](run-gate-strip.md) describes.
- rule: the selected file scrolls inside a region the keyboard reaches, with the role `region` and the name `Contents of <path>`, or `File contents` when no path is set.
- rule: the tab asks for a file before one is selected, and an empty file says `This file is empty.`, a different state from a file that could not be read.
- rule: a read that did not happen is never shown as no files or as an empty file. A `failed` reply, a rejected fetch and a missing checkout show the unreadable message with a retry control.
- rule: a tree walk that cannot enter a folder counts as failed, because a partial listing would claim a checkout without files it has.
- rule: the tree and file replies get a `failed` member beside `paths` and `content`, and the sidecar, the Docker volume reader and the local disk reader all report it, so a consumer that reads only `paths` or `content` keeps working.
- rule: a reply without a `failed` member comes from a sidecar too old to report failure, and an empty answer from it says the tab cannot confirm there are no files or that the file is empty.
- rule: a sidecar asked for an empty `repo` reads the first checkout the diff read finds, so the tab and the Diff tab show the same checkout, and it keeps the workspace root only when no checkout exists.
- rule: file text goes through the same highlighting throughout the dashboard, and the tab sets no other markup from a file or a path.
- rule: the tab has no control that edits, saves, deletes or refreshes, and the retry control appears only on a failed read.
- rule: a folder's expanded state is held with the run's files state, so a folder the operator collapsed stays collapsed while they move between the tabs of the same run, and it resets when another run is selected.
- rule: the code sits on a band darker than the pane, as tall as the code and no taller, beside a 44 px line number gutter.
- rule: Close stays at the top right of the run head's first row and the doing line sits below it.
- rule: when the run ends while Files is open, the tab goes and the Overview tab shows.
- rule: when the sidecar drops while the page holds a diff for the run, the Files tab stays and says the sidecar stopped answering, that the run may still be working, and offers `Retry now`, and it reads the tree again when the sidecar returns. It keeps no tree, as [kept run diff](kept-run-diff.md) describes. When the page holds no diff, the tab goes and the Overview tab shows if Files was open.
- rule: the tree and file replies carry `served`, `sidecar` or `volume`, beside the existing members.
- rule: the Files and Diff tabs are the only way to read a run's files and diff in the dashboard, and a run with several checkouts chooses among them as [run checkout selection](run-checkout-selection.md) describes.
- verify: absent(subject="the Files tab for a run without a connected sidecar")
- tests: groom/tests/test_gate_above_diff_dynamic.py::test_files_keeps_its_file_and_scroll_through_a_gate_and_an_answer_without_a_new_read
- tests: groom/tests/test_gate_above_diff_dynamic.py::test_the_answer_box_and_send_control_have_roles_names_and_keyboard_operation_and_pass_axe_on_diff_and_files
- tests: groom/tests/test_files_tab_dynamic.py::test_a_run_that_shows_a_diff_tab_shows_a_files_tab_before_it_and_other_runs_show_neither
- tests: groom/tests/test_files_tab_dynamic.py::test_selecting_a_run_reads_no_tree_and_the_first_open_of_files_reads_it_once
- tests: groom/tests/test_files_tab_dynamic.py::test_files_keeps_its_tree_and_selected_file_across_tabs_of_the_same_run_without_another_read
- tests: groom/tests/test_files_tab_dynamic.py::test_selecting_another_run_resets_files_and_its_first_open_reads_again
- tests: groom/tests/test_files_tab_dynamic.py::test_folders_the_operator_collapsed_stay_collapsed_across_tabs_of_the_same_run_and_reset_on_another_run
- tests: groom/tests/test_files_tab_dynamic.py::test_close_shares_the_first_row_of_the_run_head_with_a_long_doing_line_at_any_width
- tests: groom/tests/test_files_tab_dynamic.py::test_the_code_sits_on_a_darker_band_than_the_pane_with_a_44px_gutter
- tests: groom/tests/test_files_tab_dynamic.py::test_files_says_the_sidecar_stopped_answering_and_clears_on_reconnect
- tests: groom/tests/test_files_tab_dynamic.py::test_the_tab_goes_and_overview_shows_when_the_run_ends_while_files_is_open
- tests: groom/tests/test_files_tab_dynamic.py::test_an_empty_file_reads_as_empty_and_never_as_a_file_that_could_not_be_read
- tests: groom/tests/test_files_tab_dynamic.py::test_a_file_that_cannot_be_read_says_so_offers_a_retry_and_clears_when_a_read_succeeds
- tests: groom/tests/test_sidecar_session.py::test_rpc_get_tree_reports_a_missing_checkout_as_failed
- tests: groom/tests/test_app.py::test_files_from_an_old_sidecar_is_marked_as_unable_to_report_failure
- detail: [operator browses workspace file](../flows/operator-browses-workspace-file.md)
