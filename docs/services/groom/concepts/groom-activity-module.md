---
type: concept
slug: groom-activity-module
title: Groom activity module
---
# Groom activity module

The activity module builds what the [Activity tab](run-activity-tab.md) shows: the list of a run's agent turns, the same turns grouped under their work item and flow pass with the steps, gates, retries and churn alerts around them, and the head and entries of one turn. It joins three sources that each know part of a turn. The run's stored spans know when a turn started and ended, what it cost and where it sat in its flow. The turn archive knows the session's stored record. The live history knows the transcript of a turn that has not ended.

The module reads and returns plain data. It writes nothing, holds no state between calls and raises two errors the server maps to statuses: `TurnNotFound` for a slug the run has no turn under, and `TurnUnreadable` for a turn that exists whose record is not on this machine.

- code: groom/groom/activity.py@a6f9070f05f6
- tests: groom/tests/test_activity.py
- tests: groom/tests/test_activity_groups.py
- refs: [groom transcript parse module](groom-transcript-parse-module.md), [groom store](groom-store.md), [groom turns module](groom-turns-module.md), [run flow tree](run-flow-tree.md)

## Methods

### timeline

- sig: `timeline(run_id: str, live: LiveRows | None = None) -> dict[str, Any]`
- abstract: false
- does: lists the run's agent turns oldest first, a finished turn from its spans and a turn with live rows and no span from its first live row
- verify: json_path(path="$.rows[0].status", matches="^(done|failed)$")
- returns: `{"run_id", "rows", "items", "as_of"}`
- code: groom/groom/activity.py::timeline@7ae2217373d7
- tests: groom/tests/test_activity.py::test_the_timeline_lists_a_finished_turn_with_its_figures_and_pass
- endpoint: [get-run-activity](../http/get-run-activity.md)

### turn

- sig: `turn(run_id: str, slug: str, live: LiveRows | None = None) -> dict[str, Any]`
- abstract: false
- does: reads a finished turn from its stored record inside the turn's window, falls back to the live rows when the record is absent, and reads a running turn from the live rows
- verify: json_path(path="$.entries[0].kind", matches="^(message|tool)$")
- raises: `TurnNotFound` when neither a span nor a live row carries the slug
- raises: `TurnUnreadable` when the turn exists and nothing can be read for it
- returns: `{"run_id", "head", "entries", "prompt", "thinking", "cut"}`, with `cut` true when the first live update of the turn is gone
- returns: `prompt` and `thinking`, each a string or null
- returns: a `final` flag on the last assistant message of a finished turn
- code: groom/groom/activity.py::turn@5b3443f1a116
- tests: groom/tests/test_activity.py::test_a_finished_turn_reads_only_its_own_window_and_drops_the_rest
- tests: groom/tests/test_activity.py::test_an_unknown_turn_is_not_found_and_a_container_turn_with_no_transcript_is_unreadable
- tests: groom/tests/test_activity.py::test_a_live_turn_whose_start_the_history_dropped_is_marked_cut
- tests: groom/tests/test_activity.py::test_a_turn_carries_its_recorded_prompt_and_its_thinking
- tests: groom/tests/test_activity.py::test_the_last_assistant_message_of_a_finished_turn_is_final_and_a_running_turns_is_not
- endpoint: [get-run-turn](../http/get-run-turn.md)

## Rules

- rule: a result comes from the recorded `summary`, then `notes`, then the span's activity label, then for a running turn its last agent message, each cut to its first non-empty line and 140 characters.
- rule: a span with no `workhorse.visit.slug` takes the slug of the one stored turn row of its node, and of its session when the span names one, whose time falls within 5 seconds of the span's start and end. Any other count of candidates leaves the span under the key `unmatched-<span id>`.
- rule: the spans of one slug that sit under one parent span are one visit, as a retried turn is, and are one row. Its start is the earliest start, its end the latest end, its time the sum of its spans' own seconds, its cost the sum of its priced spans and its status the last span's. A slug that a resumed pass repeats gives one row per parent span. The first keeps the slug as its key, and each later one is keyed `<slug>~<milliseconds of its first start>`, so a read after a refresh gives it the same key. A row reads the record of its own session, or when it names no session the record stamped inside its own window, and it does not read the record of another visit of the slug. A row with no such record is marked not matched, and its turn answers an empty list.
- rule: a pass is numbered within its work item and flow by the start order of the flow's node spans, and one function numbers the rows, the pass headings and the head of one turn. A row whose visit slug is shared by turns of several passes takes the pass of its earliest turn, the one its start time belongs to.
- rule: a work item's figures come from the Overview's work item rows and a flow pass's from the flow tree's leaf rule, so a heading reads the same figures as the Overview. A gate, a retry or a churn alert that names no work item or pass goes to the nearest group of the same work item by time.
- rule: only `assistant` and `plan` messages with text, and tool calls, are kept as entries. The prompt and the thinking travel beside the entries as `prompt` and `thinking`, the prompt from the record's `prompt.md` else the transcript's user messages, and a failed tool call carries its whole output while a passed one carries none.
