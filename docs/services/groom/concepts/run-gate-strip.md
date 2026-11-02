---
type: concept
slug: run-gate-strip
title: Run gate strip
---
# Run gate strip

A run waiting on the operator shows its open gates in a strip above the Overview and Details tabs. The operator reads the question and answers it from whichever tab they are on, and the text they were reading stays where it was. A badge on the Runs button counts the blocked runs while another pane is open, so a gate on a run the operator is not looking at is not missed.

- code: groom/groom/assets/dashboard.js::GateStrip@5921a2b7243b
- code: groom/groom/assets/dashboard.js::GateBlock@0b60fdd379ab
- code: groom/groom/assets/dashboard.js::useHoldPlace@5e6b749cb8ef
- code: groom/groom/assets/dashboard.js::paintRunsBadge@bd8cea76ff7e
- tests: groom/tests/test_gate_strip_dynamic.py::test_the_strip_stays_above_the_tabs_while_a_tab_scrolls
- tests: groom/tests/test_gate_strip_dynamic.py::test_a_gate_that_opens_while_the_operator_reads_leaves_the_text_where_it_was
- tests: groom/tests/test_gate_strip_dynamic.py::test_two_open_gates_both_show_with_their_own_question_and_box
- tests: groom/tests/test_gate_strip_dynamic.py::test_the_strip_collapses_to_one_line_with_the_start_of_the_question_and_expands_again
- tests: groom/tests/test_gate_strip_dynamic.py::test_a_live_push_keeps_the_draft_the_collapsed_state_and_the_focused_gate
- tests: groom/tests/test_gate_strip_dynamic.py::test_the_runs_button_carries_a_counted_badge_while_another_pane_is_open_and_clears_with_the_last_block
- refs: [run now strip](run-now-strip.md), [run breakdown views](run-breakdown-views.md), [the gate strip](../gui/screens/groom-dashboard.md#detail-gate-strip), [send detail answer](../gui/screens/groom-dashboard.md#send-detail-answer)

## Placement

- rule: the strip belongs to the selected run's detail pane. It sits above the tabs and outside the scrolling region of the tab, so it stays in view while either tab scrolls.
- rule: the strip lists that run's open gates and nothing else. A gate renders in the strip only, so a tab does not repeat it and one gate shows once.
- rule: a run with no open gate has no strip, and the Details tab says there is nothing to answer.
- rule: each gate is one block with its question, its answer box and its send button. Two open gates show two blocks, in the order of their gate file paths. The strip has one `Collapse` button, in the first block's header row, because collapse belongs to the whole strip.
- rule: a gate's question is markdown that travels as data. The client renders it and sanitizes the result before it reaches the page, so a script, a frame or an event handler in a question does not run.

## Keeping the operator's place

- rule: when the strip appears, grows, collapses or clears, the content of the open tab does not move on screen. If the strip takes height from the scrolling region, the region's scroll position is moved by the same amount.
- rule: the place is held by the top edge of the scrolling region, so it also covers the header above the strip changing height.
- rule: the scroll position cannot go below the top of the tab. A tab scrolled less than the strip's height cannot keep its text in place when the strip clears, and it ends at the top.

## Drafts, focus and collapse

- rule: each gate's draft is keyed to that gate's file path. A live update, a new gate for the same run or another gate's removal leaves every other gate's typed text, caret, selection and focus where they were.
- rule: the strip collapses to one line and expands again with one button, named `Collapse` when open and `Answer` when collapsed. The button carries `aria-expanded`.
- rule: a collapsed strip keeps its boxes out of the page but not out of the draft. Expanding shows the same text, and focus moves to the first answer box. Collapsing moves focus to the button that expands it.
- rule: the collapsed line names the start of the question, the time waited when the run reports it and, with more than one open gate, how many are open. A gate that opens while the strip is collapsed raises that count, so the operator sees it.
- rule: the collapsed state belongs to the selected run. It stays while the same run stays selected, and it resets when another run opens or the detail closes.

## Sending

- rule: sending an answer uses the same command, endpoint and failure message as before the strip. The strip changes where the form sits, not how it sends.
- rule: a sent answer takes its own gate out of the strip. When the last gate goes, the strip goes with it, and the open tab and its scroll position stay.
- rule: a refused send keeps the typed text in its gate's box and says it was not taken, with the reason.
- rule: a shortcut key typed inside an answer box does nothing else. The list shortcuts ignore a focused text field.

## Runs badge

- rule: the Runs button on the activity rail carries a badge with the number of blocked runs across the fleet. It reads the same fleet count as the status bar.
- rule: the badge shows only while a pane other than Runs is open, and only while at least one run is blocked. It is hidden on the Runs pane, where the list shows the same runs.
- rule: the badge shows the number as text. The button's accessible name says the count in words, such as `Runs, 2 blocked runs`, and plain `Runs` when none is blocked.
- rule: the status bar and the run rows keep their own blocked indicators.
