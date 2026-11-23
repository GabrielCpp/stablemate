story: SM-01M6CQJCW9DQCY420AA9Z8W8M9
date: 2026-11-23
elements: RunDetail
sources: groom/groom/assets/dashboard.js, groom/groom/activity.py, groom/groom/transcript_parse.py

An operator opening a long turn wants one message or one failure, so the reading pane opens on those and keeps the rest one action away. The prompt, the thinking and each run of successful tool calls start closed, and the messages, the failed calls and the final output stay in view.

A run of successful tool calls folds from three calls. One or two stay as lines, because a fold of one line saves nothing. The fold's label counts the calls by tool, most used first, and adds their summed time. A failed call never joins a fold. It shows in red and in words with its whole output, up to the 1,000,000 characters `transcript_parse.MAX_RESULT_CHARS` keeps, in a box that scrolls on its own. A passed call carries no output, so the payload stays small.

The prompt reads from the record's `prompt.md`. A record without that file takes the transcript's user messages. The label sizes it in words, because a turn's prompt is prose. The thinking is the transcript's thinking blocks, joined.

The final output is the last assistant message of a finished turn. A running turn has none, because its last message may not be its last.

A backend that recorded no prompt or thinking says so where they would sit, and names only the missing part. A running turn, a turn that ended with no record and a turn whose start the live history dropped show no such note, because the part may exist and not be shown.

The open state lives in the turn's reading, keyed by the turn's slug, so selecting another turn opens it closed. Prompt, thinking and tool output go through the rules a message does, so a script in them does not run.

The turn endpoint carries these parts as `prompt`, `thinking`, `final` and a failed call's `result`. The book's groom holds only pushed runs, which report no turn records, so these elements are declared and not played. The browser tests of `test_turn_reading_dynamic.py` play them.
