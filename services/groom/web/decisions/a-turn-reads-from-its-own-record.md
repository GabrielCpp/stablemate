story: SM-01M6CQJ7W25QB79R1MSMEVHA3Q
date: 2026-11-23
elements: RunDetail
sources: groom/groom/assets/dashboard.js, groom/groom/activity.py, groom/groom/transcript_parse.py, groom/groom/turns.py

An operator reading what one agent turn said and ran wants to see it without opening the record files. The Activity tab lists the run's turns oldest first and opens one beside the list as messages and one line per tool call.

The tab sits directly after Overview, so the tabs read Overview, Activity, Files and Diff. The story's first criterion names a Details tab between Overview and the rest. `the-details-tab-gave-way-to-activity-files-and-diff` overturns that: the run has no Details tab.

A turn reads its own stored record. A turn of an old run with no visit slug takes the one stored record that starts within 5 seconds of the turn. With none, the row's key is `unmatched-<span id>` and the pane says the turn's messages and tool calls are not shown because its record could not be matched.

A record that holds a `transcript.acp.jsonl` is read from it. A Claude record without one is read from `transcript.jsonl`, and only its `user` and `assistant` lines count, because Claude Code also writes the API requests it sent and its attachments into that file. A captured real record proves both paths give the same turn.

The transcript is untrusted. A message goes through marked with raw HTML escaped and images reduced to their alt text, then through DOMPurify, and shows as plain text when either is missing. A tool line sets its name and its summary as text.

A running turn has no span yet. It shows its elapsed time, reads its cost as landing at the turn's end and leaves out what it cannot know. A live turn whose start fell out of the 200-update history says its earlier output is not shown. A turn outside any flow shows no pass.

A read that failed never reads as an empty run or an empty turn. Each says it could not be read and offers a retry, and the list stays.

The book's groom holds only pushed runs, which report no telemetry, so these elements are declared and not played.
