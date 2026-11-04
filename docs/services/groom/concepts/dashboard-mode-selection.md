---
type: concept
slug: dashboard-mode-selection
title: Dashboard mode selection
---
# Dashboard mode selection

The dashboard's activity controls select one of five parallel views rather than competing
implementations of one operation. Runs shows the fleet and, inside a selected run, its files and
diff, History lists the runs that ended, Attend shows the attendant's jobs, Dispatch shows queued work, and Settings exposes dashboard
controls. Selecting History, Attend, Dispatch or Settings invokes only that mode's loader; selecting Runs has
no loader branch. Every selection updates the shared active-mode presentation, and a mode with no
pane in the page lands on Runs.

Files and diff are not modes. They are tabs of a selected run, and a run with several checkouts
chooses among them with the [checkout selector](run-checkout-selection.md).

The `j`/`k` run-row navigation and command-palette result selection first choose Runs because the
run they select must be visible in that pane. That forced choice is contextual, not a preference
over the other modes: an operator chooses the activity mode that matches the information or
control they need.

- code: groom/groom/assets/dashboard.js::setMode@dd272df55c5e
- rule: use Runs for fleet and selected-run activity including its files and diff, History for the runs that ended, Attend for the attendant's jobs, Dispatch for queued work, and Settings for dashboard controls; keyboard or palette run selection switches to Runs only to reveal the selected row, `j` and `k` in History open the next and previous ended run without leaving History, and no mode supersedes another
- detail: [dashboard activity mode selection](dashboard-activity-mode-selection.md)
