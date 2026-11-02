---
type: milestone
title: Groom run visibility
status: approved
epics:
- 0009-see-what-a-live-run-is-costing
- 0010-inspect-files-and-diff-of-a-container-run
- 0011-read-the-activity-of-a-run
- 0012-review-a-finished-run-in-history
---

# Groom run visibility

## Outcome

An operator can tell from the groom dashboard what any run cost, where its time went, and what it
did, for a run still working and for one that ended months ago. A new History tab lists ended and
archived runs. Selecting a run shows one detail with the same figures in either place, and a reworked
Activity tab replaces the "Recent telemetry history" feed so a turn or a failure can be found and
read without opening a terminal.

Files and Diff stop being top-level tabs. They move inside the selected run and exist only for a
container run with a connected sidecar. The operator keeps the place they were reading when a gate
opens, because the question and the answer box sit above that run's tabs. The design is in
[the design note](../../design/groom-run-visibility.md).

## Release Boundary

This is one milestone. It is complete when every journey below works in the running dashboard against
live runs and archived runs, and when the old rail tabs and the old feed are gone.

Each removal lands in the same story as its replacement. The rail tabs and the repo picker go when Files
and Diff work inside a run, because removing them earlier leaves container runs with no way to reach them.
The old feed goes when Raw works, because every record it could show must stay reachable. Run figures,
History and Activity may land incrementally around those two cutovers.

The first story proves one path end to end: selecting a live run shows an Overview with its real cost
and its time per flow.

## User Journeys

### Inspect files and diff of a container run

- services: groom

The actor is an operator with a run in a container whose sidecar is connected. The entry point is the
Runs tab.

1. The operator selects the run. The list narrows to a column, and the detail opens beside it.
2. The detail offers Overview, Activity, Files and Diff. The Diff tab shows the size of the change.
3. The operator opens Diff and reads the uncommitted change by file. A switch shows the whole change
   since the branch started.
4. The operator opens Files and browses the checkout read-only.
5. A run with more than one checkout shows a selector for them. A run with one shows none.

The operator ends knowing what the run changed, without leaving the run.

Required states:

- A gate opens on this run: the full question and answer box appear above the tabs, the operator
  answers there, and the tab and scroll position stay. Keyboard shortcuts stay inert while typing.
- The sidecar drops: the last diff stays with its time, the tab is marked stale, and a retry is
  offered. It clears on reconnect.
- A native run: no Files or Diff tab, and the Overview shows the checkout path.
- An ended run: no Files or Diff tab.

Preservation: the rail no longer shows Files, Diff or the repo picker. The terminal client keeps its
own file and repo views.

### Review a finished run in history

- services: groom

The actor is an operator looking back at runs. The entry point is the new History tab in the rail.

1. The operator opens History and sees ended runs from the last 30 days, newest first, with totals.
2. Each row shows the workflow, repo, ending, end time, active time, wall time, cost with its coverage,
   items, cost per item against the median, turns, gates and problems.
3. The operator filters by workflow, repo, ending or range, and the totals follow the filters. A range
   can include archived runs.
4. The operator selects a run. The list narrows and keeps its filters, the same detail opens, and a
   close control returns to the full table.
5. The Overview shows time and cost by flow, node and work item, where the wall clock went, models,
   facts, and the sessions with how each stopped.
6. The By node view shows each node against its median, so a high cost per item can be traced to a
   node.

The operator ends knowing what the run cost, where the money went, and why it stopped.

Required states:

- A failed run: a banner says where it ended and why, links to that moment in Activity, and gives a
  copyable command to continue it. It shows no comparison with the median.
- A run with no recorded ending: the label says so in words.
- An archive opened for the first time: a reading state, with no problem count until it has loaded.
- An archive whose files are gone: its stored summary, and a statement that Activity cannot be read.
- Nothing matches the filters: an empty state, with the totals at zero.
- A backend that reports no cost: the estimate labelled as one, with output tokens in the tree.

### See what a live run is costing

- services: groom

The actor is an operator deciding whether to let a run continue. The entry point is a run in the Runs
tab.

1. Every row in the run list shows cost so far, active time and items done.
2. The operator selects a run. The Overview shows the current node, the turn length against that
   node's norm, agent idle and the last beat.
3. The cost tile says the figure is as of the last finished turn and gives a burn rate per active hour.
4. The same breakdowns as History show the running node marked in the tree.
5. Figures refresh as telemetry arrives, with no flicker and no loss of the operator's place.

The operator ends able to decide whether to let the run continue.

Required states:

- Blocked at a gate: the tree marks the node as waiting on the operator, not as running. The answer
  box is pinned above the tabs.
- Just started: a statement that figures appear when the first node finishes, with no problem badge.
- A backend that reports no cost: the estimate labelled as one, with output tokens in the tree.
- The run ends while open: the detail stays, with a strip saying it ended and linking to History.
- Another pane open: the Runs rail badge shows a blocked run, and the History rail badge shows a failed
  run since the operator last looked.

### Read the activity of a run

- services: groom

The actor is an operator finding out what a run did. The entry point is the Activity tab of any
selected run, live or ended.

1. The timeline shows the run grouped by work item, then flow pass, then visit. One row is one visit,
   with its time, duration, cost and a one-line result.
2. Successful deterministic steps fold into one line.
3. The operator moves with `j` and `k`, jumps to the next problem with `e`, searches, and filters by
   work item. The keys are labelled on screen.
4. Problems narrows the timeline. Steps and Info logs add to it.
5. Selecting a turn shows its duration, model and cost, its messages as prose, its tool calls as one
   line each and its failures in full. Prompt and thinking start collapsed.
6. Selecting a step shows its error, logs and what came next. Selecting a gate shows question and
   answer.
7. On a live run the timeline follows. Scrolling pauses it, and a pill counts what arrived and returns
   to live.

The operator ends able to say what happened in a run and why, from the browser.

Required states: a turn still running, a failed step, an answered gate, a Problems view with none, an
empty run, and Raw, which lists every record with metric samples hidden until asked for.

Preservation: the "Recent telemetry history" feed is removed. Every record it could show stays reachable
under Raw. A problem badge on the tab always equals the Problems count.

## Architecture Decisions

- **One run detail, two entrances.** Runs and History render one component, so a figure cannot mean
  different things in the two places.
- **Files and Diff follow a sidecar capability on the run row.** The dashboard reads it and decides the
  tabs. The workspace endpoints stay as they are, because the terminal client uses them. Native runs get
  no browser Files or Diff, by owner decision.
- **Flow identity is derived by walking span parents, and new runs also carry it.** The walk covers old
  runs and archives and stays first. Workhorse also stamps `workhorse.flow` and `workhorse.state` on each
  step when it starts, so a live new run names its open flow and an old run keeps its flows.
- **Each archive carries a stored summary.** The manifest gains cost, ending and active time, and an older
  archive gets its summary lazily, once. Listing must not open a frozen telemetry database per row.
- **Overview endpoints reuse the terminal's profile, node cost and loop queries.** They go through the
  existing run-source redirect on the query pool, so a live run and an archive return one shape.
- **Live figures refresh on a committed telemetry batch.** The clock ticks in the browser. Nothing reads the
  database on a timer.
- **Archived transcripts get a route.** Only live runs serve turn content today.
- **The diff since branch start comes from the sidecar.** It computes the base from the checkout. The last
  diff kept during a sidecar loss lives in the browser.
- **The dashboard stays vendored Preact with htm.** There is no build step and no CDN.

## Constraints

- Cost is never presented as complete when it is not. Every total carries its coverage, and an estimate is
  labelled as one.
- Comparisons use successful runs of the same workflow and show their sample size. A failed or abandoned run
  shows no comparison, and under five comparable runs the comparison stays blank.
- Cost per item divides by finished items.
- "Problems" has one definition and one count across the tab badge, the attention tile and History. An
  answered gate is not a problem.
- Wall time is never shown without active time beside it.
- Listing history stays responsive with hundreds of archives, and opening a live Overview must not scan the
  whole telemetry store.
- Transcript content is untrusted and goes through the existing sanitizer.
- Every new control has a role, an accessible name and keyboard operation, and status is never color alone.
- Retention and archive rules do not change.

## Acceptance

- The rail shows Runs, History, Attendant, Dispatch and Settings, and no Files, Diff or repo picker.
- A container run with a connected sidecar shows Files and Diff tabs. A native run and an ended run show
  neither. Sidecar loss keeps the last diff, marked stale, and reconnecting clears the mark.
- Answering a gate above the diff leaves the Diff tab and its scroll position in place.
- The uncommitted and since-branch-start diffs each match `git diff` for the same base in the checkout.
- History lists a real ended run and a real archived run, and the filters change both the rows and the
  totals.
- For one finished run, the cost, the per-node times and the per-flow times on screen match the terminal's
  cost and profile reports for that run. Flow times appear for a run recorded before this milestone.
- A run with unpriced turns shows its coverage. A backend with no cost shows a labelled estimate.
- A failed run shows its banner, its copyable command, and no median comparison. Running the command continues
  that run.
- A live run's Overview shows its current node and cost as of the last finished turn, and it updates on new
  telemetry without losing scroll position.
- A blocked run raises the Runs rail badge while History is open. A run that fails raises the History rail
  badge. A selected run that ends stays open with its strip.
- Activity shows visits, not records. No metric sample appears outside Raw. A turn from a live run and a turn
  from an archived run both open in the reading pane.
- The problem count is equal on the tab badge, the attention tile and the History column of one run.
- The "Recent telemetry history" feed is gone from the dashboard, and its records remain reachable under Raw.
- With hundreds of archives present, History opens in under two seconds after the first summaries exist.
- The book describes the new rail, run detail, History and Activity as current behaviour, and the pages for the
  removed tabs and feed are updated.

## Non-Goals

- The terminal client does not change or gain these screens.
- There is no side-by-side comparison of two runs. The per-node median covers tracing a cost.
- There are no budgets, cost alerts or projected totals. The burn rate covers the decision to keep spending.
- History has no stop, resume or rewind buttons. A failed run offers the command.
- Files and Diff do not come to native or ended runs, and nothing edits files.
- Retention, archive format beyond the summary, and the telemetry schema's stored spans stay as they are.
