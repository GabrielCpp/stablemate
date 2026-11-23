story: SM-01M6CQJF3C824NJ7KWR7X08TF5
date: 2026-11-23
elements: RunDetail
sources: groom/groom/assets/dashboard.js, groom/groom/activity.py, groom/groom/app.py, groom/groom/gates.py

An operator who wants to know why a step failed, or what was asked and answered at a gate, opens the row and reads it in the pane. The row's one line stays as it was, and the pane holds the rest.

A step's logs are those of its node between its span's start and end, because a log row carries no visit. The pane keeps the last 500 of them and says when earlier ones are cut, so a noisy step cannot make the page heavy. An ERROR or FATAL line reads by its level word as well as its colour.

What came next is the row after this one in the run's timeline. It names that row and offers a control that opens it, which unfolds the work item, the pass and the fold that hold it. The last row says nothing came after it. A running step says nothing came yet.

A running step and an open gate have no stored span, so each reads from the run's live state and stands as a row of its own. A gate's key is `gate:<node>#<n>` and holds across open and answered, so the selection does not move when the operator answers.

The gate file is append-only and the span carries no answer. The nth asking therefore reads the nth occurrence of its question, and an asking the file no longer holds reads no answer. It never reads a neighbour's answer.

An open gate holds no answer box of its own. It says it is not answered yet and points to the box above the tabs, which keeps `the-gate-strip-sits-above-the-tabs`. The answer a person sends goes through the same route as before and lands in the gate file, and the pane reads it back from there.

The step's error, its logs, the gate's question and its answer go through the rules a message does, so markup in them shows as text and no script runs. This keeps `a-turn-reads-from-its-own-record`.

The entry endpoint carries these parts as `head`, `error`, `logs`, `cut`, `next`, `question`, `answer` and `taken`. The book's groom holds only pushed runs, which report no spans, so these elements are declared and not played. The browser tests of `test_activity_step_gate_dynamic.py` play them.
