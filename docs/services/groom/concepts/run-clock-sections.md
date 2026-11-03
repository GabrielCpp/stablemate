---
type: concept
slug: run-clock-sections
title: Run clock, models, facts and sessions
---
# Run clock, models, facts and sessions

Below the tiles, a finished run's Overview carries four sections that answer where the wall clock went, which models did the work, which facts identify the run and how each session ended. An operator reads them to decide whether a slow run was slow because of the agent, the machine or the people, what each model cost and which session to look at when a run stopped.

The sections are not a second set of numbers. They come from the same profile that `groom profile` prints and the same cost read that `groom cost` prints, served by the same Overview query and refetched with the same figures revision as the [overview tiles](overview-tiles.md). The wall clock bar, the models table and the sessions table are three views of that one profile, so each figure on the page equals the figure in the terminal reports.

- code: groom/groom/store.py::run_profile@05d8c4f81e30
- code: groom/groom/store.py::_profile_models@5ff7246d5bfe
- code: groom/groom/store.py::_profile_sessions@84ea59be739d
- code: groom/groom/overview.py::run_overview@d4e666f27ee7
- code: groom/groom/projection.py::head@c6501d02c398
- code: groom/groom/cli.py::_format_profile@db621328f245
- code: groom/groom/assets/dashboard.js::WallClock@45bcd1849e1e
- code: groom/groom/assets/dashboard.js::Models@dfdce71eb006
- code: groom/groom/assets/dashboard.js::CopyButton@075340c266d2
- code: groom/groom/assets/dashboard.js::RunFacts@8b71355f91e7
- code: groom/groom/assets/dashboard.js::Sessions@60d00a14245d
- tests: groom/tests/test_run_clock.py::test_the_wall_clock_segments_sum_to_the_wall_time_and_the_active_ones_to_the_active_tile
- tests: groom/tests/test_run_clock.py::test_the_model_totals_equal_the_cost_report_and_an_unpriced_model_has_no_cost
- tests: groom/tests/test_run_clock.py::test_a_model_with_some_priced_turns_says_how_many
- tests: groom/tests/test_run_clock.py::test_the_session_rows_are_the_sessions_the_tile_counts
- tests: groom/tests/test_run_clock.py::test_a_session_with_no_root_span_has_no_recorded_ending_and_each_gap_is_measured
- tests: groom/tests/test_run_clock.py::test_the_overview_and_the_profile_report_read_one_profile
- tests: groom/tests/test_run_clock.py::test_the_profile_report_prints_the_models_and_the_sessions_in_words
- tests: groom/tests/test_run_clock.py::test_the_run_head_carries_a_checkout_path_for_a_native_run_only
- tests: groom/tests/test_run_clock_dynamic.py::test_the_legend_names_six_segments_in_words_and_the_active_ones_equal_the_active_tile
- tests: groom/tests/test_run_clock_dynamic.py::test_the_models_table_says_not_reported_for_a_model_with_no_cost_and_totals_the_cost
- tests: groom/tests/test_run_clock_dynamic.py::test_the_sessions_table_has_the_tiles_count_and_says_when_no_ending_was_recorded
- tests: groom/tests/test_run_clock_dynamic.py::test_a_run_that_is_no_longer_live_does_not_claim_its_last_session_is_running
- tests: groom/tests/test_run_clock_dynamic.py::test_the_checkout_path_shows_for_a_native_run_and_a_long_one_stays_in_the_pane
- tests: groom/tests/test_run_clock_dynamic.py::test_a_copy_button_works_from_the_keyboard_and_confirms_in_text_a_screen_reader_announces
- tests: groom/tests/test_run_clock_dynamic.py::test_a_failed_clipboard_write_says_so
- tests: groom/tests/test_run_clock_dynamic.py::test_a_run_with_no_finished_node_shows_only_its_run_facts_of_the_new_sections
- tests: groom/tests/test_run_clock_dynamic.py::test_a_live_refresh_keeps_the_scroll_position_with_the_new_sections_open
- tests: groom/tests/test_run_clock_dynamic.py::test_the_new_sections_pass_axe
- refs: [overview tiles](overview-tiles.md), [run flow tree](run-flow-tree.md), [get run overview](../http/get-run-overview.md), [the groom dashboard detail pane](../gui/screens/groom-dashboard.md#detail-pane)

## Wall clock

- rule: the wall clock bar splits the run's wall time into six segments: agent turns, deterministic, infrastructure, waits, unclassified and stopped between sessions. They sum to the wall time.
- rule: the legend names every segment with its duration as text, so the split does not depend on colour. The bar itself is one image with a label that names the split.
- rule: agent turns, deterministic and infrastructure together equal the Active time tile's active time. Wall time sits beside active time.
- rule: the segments are the time partition of the run profile, so each equals the figure `groom profile` prints.

## Models

- rule: the Models table has one row per model with its turns, cost, output tokens and cache read share, ordered by cost with unpriced models last.
- rule: a model none of whose turns reported a cost says `not reported` and does not show `$0`. A model with some priced turns shows its cost and how many of its turns were priced.
- rule: the model costs add up to the Cost tile and to the `groom cost` total, because both sum the same per-turn charge.
- rule: a turn that records no model counts under `(no model recorded)`.

## Run facts

- rule: the Run list shows when the run started, its branch, its run id, its pid, its gas, its run directory and its checkout path, in that order. A fact with no value is left out, except the run id. The pid is the head's pid and shows for a run that has one. The gas is the Gas figure of the run's live metrics and shows for a run that reports one.
- rule: the checkout path shows only for a native run, whose checkout is a directory on this machine. A container run has no checkout path.
- rule: a long value wraps inside the pane and does not widen the layout.
- rule: every fact has a copy button named for it, such as `Copy run id`, `Copy pid` or `Copy gas`. The button works from the keyboard.
- rule: a copy answers in visible text that a status region announces, `Copied run id`. A write the browser refuses answers `Could not copy run id`. The note clears after a few seconds.

## Sessions

- rule: the Sessions table has one row per session, and the row count equals the session count on the Active time tile.
- rule: each row shows when the session started, how long it was active, how long the run then stood still before the next session and how the session ended.
- rule: a session whose root span carries no ending says `no recorded ending`. The table does not guess a cause.
- rule: the last session of a run that is still going shows `still running` for its stop and `running` for its ending, unless its root span recorded an ending.
- rule: the sessions come from the run profile, so the terminal report `groom profile` lists the same sessions with the same words, `no recorded ending` included.

## Refresh

- rule: the sections are computed by the same Overview read as the tiles and refetched when a span batch commits. A refetch keeps the operator's scroll position.
- rule: a run with no finished node shows none of the wall clock, Models and Sessions sections, and still shows the Run facts list.
