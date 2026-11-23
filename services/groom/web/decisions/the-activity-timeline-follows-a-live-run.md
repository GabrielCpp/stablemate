story: SM-01M6CQJHGAS0C9HKRSKPFKKQJW
date: 2026-11-23
elements: RunDetail, Runs
sources: groom/groom/assets/dashboard.js, groom/groom/app.py

An operator watching a live run wants the newest row in view without losing what they are reading. The Activity timeline follows the run, pauses when the operator scrolls up, and returns on one action.

A committed span batch moves the run's revision, and the open timeline reads the run again. This keeps `the-overview-refreshes-on-a-committed-span-batch`. While a turn is running the timeline also reads the run every three seconds, because a growing turn adds messages before its span commits.

The follow pauses on a scroll that moved up and left the end by more than 4 pixels. It resumes on a scroll that moved down to within 4 pixels of the end. A scroll event that moved nothing changes nothing, so a re-render cannot resume a paused follow.

While paused, the groups open at the pause stay open, so a group that finishes does not fold away under the operator's eyes.

The pill counts the rows that were not in the timeline at the pause, or the problems while Problems is on. Pressing it selects the newest row and opens it in the pane, because the operator asked to go to what arrived. Resuming by the control or by scrolling leaves the selection alone, because the operator did not ask to read something else.

A lost connection disables the control and makes it read 'Not connected'. The reconnect reads the run again, which fills the gap and clears the mark.

The run's end removes the control and the pill. A turn the timeline still holds as running reads as ended with no record when no turn span arrives, and its cost reaches the headings and the run row when its span commits.

The connection chip's offline phase counts from the moment an open socket closed. Before, each failed reconnect reset that clock, so 'not connected' was never reached.

The book's groom holds only pushed runs, which report no spans, so its timeline has no rows and no follow control. These elements are declared and not played. The browser tests of `test_activity_follow_dynamic.py` play them.
