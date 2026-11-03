---
type: concept
slug: run-history-filters
title: Run history filters
---
# Run history filters

The operator narrows the History list by workflow, repo, ending and range, and by text, to find the runs worth a look. The totals strip describes the rows shown, so a narrowed list answers what those runs cost as well as which they are. The filters live in the browser: the list is already loaded, so a choice narrows the rows at once and asks the server for nothing.

The filters belong to History, not to a run. Selecting a run, closing it, and leaving for another rail tab and coming back all keep them, and the narrowed column beside an open run states them so the operator sees why the column holds fewer runs than the table did. When nothing matches, the pane says so and offers one control that sets the filters back.

The screen is the [groom dashboard](../gui/screens/groom-dashboard.md#history-filters). The rows come from [get-run-history](../http/get-run-history.md), and the strip is the [run history totals](run-history-totals.md).

- code: groom/groom/assets/dashboard.js::historyShown@1f04a4430cf5
- code: groom/groom/assets/dashboard.js::historySums@d98874013e39
- code: groom/groom/assets/dashboard.js::historyScope@334b5763b299
- code: groom/groom/assets/dashboard.js::HistoryFilters@669c36ca8aa4
- code: groom/groom/assets/dashboard.js::HistoryChoice@0db9daffece8
- code: groom/groom/assets/dashboard.js::clearHistoryFilters@6e225267a691
- code: groom/groom/history.py::listing@931989b4c09b
- rule: the filters narrow the rows in the browser from the list already loaded, with no request
- rule: the workflow, repo, ending, range and text filters combine, and a run shows only when it matches every filter that is set
- rule: the workflow and repo selects offer the values in the list, each with an All choice, and keep a chosen value in the options when the list no longer holds it
- rule: the ending select offers the endings the history route names, in the route's order, with an Any choice, so the browser holds no second mapping of endings
- rule: a run whose summary is still being read has no ending, and any ending filter leaves it out
- rule: the range offers the last 7 days and the last 30 days and starts on the last 30 days, which is the retention of the list
- rule: the text filter matches the run id or the repo and branch, ignoring case, as the operator types
- rule: the totals strip is computed from the rows shown with the same sums as the route, so a run still being read counts in the runs and stays out of the sums
- rule: the narrowed column keeps the filters and states them above its rows, and with no filter set it holds every run the table held
- rule: the filters persist while a run is selected or closed and while the operator is in another rail tab
- rule: the selects keep one width whatever they hold, so the bar does not shift between filter states, and a long value cuts off with an ellipsis
- rule: when nothing matches, the pane says no runs match these filters, the totals read zero and a control clears the filters and puts focus in the text box
- rule: `j`, `k` and `e` stay inert while a filter holds focus
- tests: groom/tests/test_history_filters_dynamic.py::test_the_workflow_and_repo_filters_offer_the_values_in_the_list_each_with_an_all_choice
- tests: groom/tests/test_history_filters_dynamic.py::test_the_ending_filter_offers_every_ending_in_words_with_an_any_choice
- tests: groom/tests/test_history_filters_dynamic.py::test_the_range_filter_offers_the_last_7_and_30_days_starts_on_30_and_narrows_to_7
- tests: groom/tests/test_history_filters_dynamic.py::test_the_text_filter_narrows_rows_by_run_or_repo_as_the_operator_types
- tests: groom/tests/test_history_filters_dynamic.py::test_each_filter_narrows_the_rows_at_once_and_filters_combine_without_a_request
- tests: groom/tests/test_history_filters_dynamic.py::test_the_totals_describe_the_rows_shown_with_the_estimate_partly_priced_and_reading_clauses
- tests: groom/tests/test_history_filters_dynamic.py::test_selecting_a_run_keeps_the_filters_and_states_them_above_the_narrowed_list
- tests: groom/tests/test_history_filters_dynamic.py::test_closing_the_run_returns_to_the_table_with_the_filters_still_set
- tests: groom/tests/test_history_filters_dynamic.py::test_leaving_history_for_another_tab_and_coming_back_keeps_the_filters_and_the_open_run
- tests: groom/tests/test_history_filters_dynamic.py::test_when_nothing_matches_the_pane_says_so_the_totals_read_zero_and_a_control_clears_the_filters
- tests: groom/tests/test_history_filters_dynamic.py::test_j_k_and_e_stay_inert_while_a_filter_holds_focus
- tests: groom/tests/test_history.py::test_the_listing_names_every_ending_once_in_the_order_the_ending_filter_offers_them
