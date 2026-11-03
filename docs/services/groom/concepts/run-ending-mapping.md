---
type: concept
slug: run-ending-mapping
title: Run ending mapping
---
# Run ending mapping

The operator reads how a run ended in words: success, gave up, failed, interrupted, crashed, or no ending recorded. The run records only a terminal on its root span, so groom maps the terminal of the latest root span to the ending, and the latest root decides when a run was resumed.

A run counts as closed by its root when no span of the run ends more than 60 seconds after the root, so a child span that ends seconds after an `interrupted` root does not hide the ending. A span hours after the root means the run went on and died with no ending, and it reads no ending recorded.

A terminal of `terminal` or `ended` reads success, and reads gave up when a span of the run sits at a node named in the give-up setting. A terminal of `fail` reads failed, `interrupted` reads interrupted, and `aborted` reads crashed. A terminal of `reload` is not an ending, because the run continues through exec, so it is never listed. A root span with no terminal, or with a terminal groom does not know, records no ending, and the run is listed after 48 hours of silence as no ending recorded.

- code: groom/groom/history.py::ending_of@6a5b7ffda824
- code: groom/groom/alerts.py::giveup_nodes@95ae797aef07
- rule: terminal and ended read success, and read gave up when the run has a span at a give-up node
- rule: fail reads failed, interrupted reads interrupted, and aborted reads crashed
- rule: reload is not an ending
- rule: a terminal groom does not recognize is not guessed into an ending, so the run reads no ending recorded once it has been silent for 48 hours
- rule: a span ending within 60 seconds after the latest root still counts as the root closing the run, one named tolerance shared by the list and the summary, and a longer gap leaves the run with no ending recorded
- rule: the ending is written in words in every place it is shown, and its colour never carries it alone
- tests: groom/tests/test_history.py::test_each_recorded_terminal_maps_to_one_ending_and_reload_is_not_an_ending
- tests: groom/tests/test_history.py::test_the_ending_is_written_in_words_for_each_recorded_terminal
- tests: groom/tests/test_history.py::test_a_run_that_reached_a_give_up_node_reads_gave_up
- tests: groom/tests/test_history.py::test_a_span_ending_within_sixty_seconds_after_the_root_still_counts_as_the_root_closing_the_run
- tests: groom/tests/test_history.py::test_a_span_ending_past_sixty_seconds_after_the_root_means_the_run_went_on
- tests: groom/tests/test_history.py::test_an_unrecognized_terminal_records_no_ending_until_the_run_has_been_silent
