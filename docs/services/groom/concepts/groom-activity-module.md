---
type: concept
slug: groom-activity-module
title: Groom activity module
---
# Groom activity module

The activity module builds what the [Activity tab](run-activity-tab.md) shows: the list of a run's agent turns and the head and entries of one turn. It joins three sources that each know part of a turn. The run's stored spans know when a turn started and ended, what it cost and where it sat in its flow. The turn archive knows the session's stored record. The live history knows the transcript of a turn that has not ended.

The module reads and returns plain data. It writes nothing, holds no state between calls and raises two errors the server maps to statuses: `TurnNotFound` for a slug the run has no turn under, and `TurnUnreadable` for a turn that exists whose record is not on this machine.

- code: groom/groom/activity.py@d4907cbdf713
- tests: groom/tests/test_activity.py
- refs: [groom transcript parse module](groom-transcript-parse-module.md), [groom store](groom-store.md), [groom turns module](groom-turns-module.md), [run flow tree](run-flow-tree.md)

## Methods

### timeline

- sig: `timeline(run_id: str, live: LiveRows | None = None) -> dict[str, Any]`
- abstract: false
- does: lists the run's agent turns oldest first, a finished turn from its spans and a turn with live rows and no span from its first live row
- verify: json_path(path="$.rows[0].status", matches="^(done|failed)$")
- returns: `{"run_id", "rows", "as_of"}`
- code: groom/groom/activity.py::timeline@30f4cd17fc42
- tests: groom/tests/test_activity.py::test_the_timeline_lists_a_finished_turn_with_its_figures_and_pass
- endpoint: [get-run-activity](../http/get-run-activity.md)

### turn

- sig: `turn(run_id: str, slug: str, live: LiveRows | None = None) -> dict[str, Any]`
- abstract: false
- does: reads a finished turn from its stored record inside the turn's window, falls back to the live rows when the record is absent, and reads a running turn from the live rows
- verify: json_path(path="$.entries[0].kind", matches="^(message|tool)$")
- raises: `TurnNotFound` when neither a span nor a live row carries the slug
- raises: `TurnUnreadable` when the turn exists and nothing can be read for it
- returns: `{"run_id", "head", "entries", "cut"}`, with `cut` true when the first live update of the turn is gone
- code: groom/groom/activity.py::turn@01b84cdb4aec
- tests: groom/tests/test_activity.py::test_a_finished_turn_reads_only_its_own_window_and_drops_the_rest
- tests: groom/tests/test_activity.py::test_an_unknown_turn_is_not_found_and_an_unarchived_one_is_unreadable
- tests: groom/tests/test_activity.py::test_a_live_turn_whose_start_the_history_dropped_is_marked_cut
- endpoint: [get-run-turn](../http/get-run-turn.md)

## Rules

- rule: a result comes from the recorded `summary`, then `notes`, then the span's activity label, then for a running turn its last agent message, each cut to its first non-empty line and 140 characters.
- rule: a span with no `workhorse.visit.slug` takes the slug of the one stored turn row of its node, and of its session when the span names one, whose time falls within 5 seconds of the span's start and end. Any other count of candidates leaves the span under the key `unmatched-<span id>`.
- rule: a turn that several spans share, as a retried turn does, is one row. Its start is the earliest start, its end the latest end, its cost the sum of its priced spans and its status the last span's.
- rule: only `assistant` and `plan` messages with text, and tool calls, are kept as entries.
