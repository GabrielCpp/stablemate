---
type: concept
slug: groom-transcript-parse-module
title: Groom transcript parse module
---
# Groom transcript parse module

The transcript parse module reads one stored turn record into a list of entries, whichever backend wrote it. An entry is either a message with a role and text, or a tool call with a name, a one-line summary, a failed flag, a time in seconds and, for a failed call, its whole output. The [groom activity module](groom-activity-module.md) filters the list to what the Activity tab shows.

A record is a directory of files that [capture](groom-turns-module.md) copied from the run. The module recognises the Claude session log, the Codex rollout, the OpenCode tee and export, and the ACP update stream, and reads each into the same entry shape. It skips a line that is not valid JSON, because a record being written can end mid-line, and it returns nothing for a record with no transcript file. It never raises on a malformed record.

- code: groom/groom/transcript_parse.py@2cc902d9daa1
- rule: a window of two timestamps cuts the entries of a resumed session to the turn's own, and an entry with no timestamp stays.
- rule: a tool call and its result are one entry, joined by the call id, and the entry is failed when the result reports an error.
- rule: a tool call's time is the seconds from its call to its result. A Claude record gives it from the two lines' timestamps, an ACP record from the first and last update of the call id, and an OpenCode record from the call's recorded start and end. A Codex record gives none, and a call with no time carries null.
- rule: an ACP call's name is the first word of its title and the rest of the title is its summary, so a call titled `Bash pytest` is the tool `Bash`.
- rule: a tool result is returned whole up to 1,000,000 characters, and the summary stays one line.
- rule: transcript text is returned as recorded. The module strips no markup and adds none.
- rule: ACP message chunks that follow one another join into one message, and the updates of one call merge into one tool entry.
- verify: json_path(path="$[0].kind", matches="^(message|tool)$")
- tests: groom/tests/test_activity.py::test_a_claude_record_keeps_the_messages_and_pairs_each_tool_with_its_result
- tests: groom/tests/test_activity.py::test_a_resumed_session_record_is_cut_to_the_turns_own_window
- tests: groom/tests/test_activity.py::test_a_malformed_line_is_skipped_and_html_stays_raw_text
- tests: groom/tests/test_activity.py::test_a_codex_rollout_gives_messages_commands_and_file_changes
- tests: groom/tests/test_activity.py::test_an_opencode_tee_and_an_opencode_export_both_read
- tests: groom/tests/test_activity.py::test_acp_chunks_join_and_a_calls_updates_merge
- tests: groom/tests/test_activity.py::test_a_record_with_no_transcript_file_reads_as_none
- tests: groom/tests/test_activity.py::test_a_tool_call_carries_its_time_from_its_call_to_its_result
- tests: groom/tests/test_activity.py::test_an_acp_call_is_named_by_its_tool_and_timed_from_its_first_update_to_its_last
- tests: groom/tests/test_activity.py::test_a_failed_tool_call_carries_its_whole_output_and_a_passed_one_carries_none
- refs: [groom activity module](groom-activity-module.md), [groom turns module](groom-turns-module.md)
