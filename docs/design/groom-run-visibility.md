# Groom run visibility

An operator attending workflow runs can answer a gate in groom. That operator cannot see what a
run cost, where its time went, or what a finished run did, without leaving the browser for a
terminal. The feed that should explain a run mixes metric samples with events, so one turn is
hard to find and harder to read.

This note designs the screens and the data behind them. The contract is the milestone:
[groom run visibility](../milestones/groom-run-visibility/milestone.md). The mockups sit in that
folder under `mockups/`.

## The problem in the operator's terms

Three moments decide whether groom earns its place:

1. A gate opens while the operator is reading something else. They need the question and the
   answer box where they already are.
2. A run ends unwatched, often with a failure. They need to notice, and to learn where it ended
   and how to continue it.
3. A run keeps spending. They need to decide whether to let it continue, from its cost, its
   burn rate and whether its time is normal for that node.

Today's rail makes these harder. Files and Diff are top-level tabs with their own repo picker,
detached from the run they describe. Finished runs have no screen. Cost and per-node time exist
only behind terminal commands.

## Top-level parts

| Part | Owns | Never knows |
| --- | --- | --- |
| Rail | Which pane is showing, and the badges that pull the operator back | Anything about one run |
| Run detail | The tabs of one run, and the open gate pinned above them | Whether it was entered from Runs or History, beyond what the run's state implies |
| History list | Which ended runs match the filters, and their totals | How a run's detail is drawn |
| Run summary | Cost, active time, ending and counts for one run, cheap enough to list hundreds | Spans and transcripts |
| Run profile | Time and cost by flow, node and work item, sessions, models | Which screen asks |
| Activity reader | A run's records grouped into visits, and one visit's content | Where the records are stored |

## Navigation

The rail becomes Runs, History, Attendant, Dispatch, Settings. Files, Diff and the repo picker
leave it.

One run detail has two entrances. Selecting a run in Runs or in History opens the same tabs:
Overview, Activity, Files, Diff. The list narrows to a column beside it, and it keeps its filters
in History.

| Run | Overview | Activity | Files, Diff | Gate |
| --- | --- | --- | --- | --- |
| Container with a connected sidecar | yes | yes, following | yes | pinned, answerable |
| Container whose sidecar dropped | yes | yes | last diff, marked stale | pinned, answerable |
| Native | yes, with the checkout path | yes, following | no | pinned, answerable |
| Ended or archived | yes | yes, not following | no | answered gates in Activity only |

Native runs lose browser Files and Diff. The owner asked for this. The checkout path is on the
Overview, because the operator already has that checkout open. Workspace endpoints stay, because
the terminal client reads them.

## Overview

Live and historical runs share one Overview, so a figure means the same thing in both.

- A failure banner, on a failed run only. It says where the run ended, links to that moment in
  Activity, and offers the command that continues it.
- A now strip, on a live run only. It holds the current node, the turn length against that node's
  norm, agent idle and the last beat.
- Five tiles: cost, active time, work items, agent turns, attention. A live cost says it is as of
  the last finished turn, and it gives the burn rate per active hour.
- Where the wall clock went: agent turns, deterministic steps, infrastructure, waits, unclassified
  and stopped between sessions. A real run's wall clock can be more than double its active time,
  so this bar is what stops wall clock from misleading.
- Where the time and money went, with three views. By flow is the tree of flow, state and node. By
  node adds the comparison with the median, which is what explains a high cost per item. By work
  item says what each item took and how it ended.
- Models, and the run's facts with copy buttons.
- Sessions: when each started, how long it worked, and how it stopped.

### Rules for figures

- Cost always carries coverage: "153/163 turns priced". A backend that reports no cost shows the
  estimate labelled as an estimate, and the tree shows output tokens in place of dollars.
- Cost per item divides by finished items.
- A median comparison uses successful runs of the same workflow, and it shows its sample size.
- A failed or abandoned run shows no comparison. Spending less by failing must not read as thrift.
- "Problems" means failed steps, backend retries, failed gate checks and churn alerts. The tab
  badge, the attention tile and the History column show the same number. An answered gate is not a
  problem.

## History

History lists ended and archived runs, newest first. Filters are workflow, repo, ending and range,
with last 30 days as the default and archives available on request. A totals strip follows the
filters. Each row shows ending, ended, active, wall, cost with coverage, items, cost per item
against the median, turns, gates and problems.

A run with no recorded ending is a real outcome of a killed process. The label says so in words.

Opening an archive for the first time takes a moment, so its tabs say so and its problem badge
waits for the count. An archive whose files are gone still shows its stored summary, and it says
that Activity cannot be read.

## Noticing a change

- The Runs rail badge shows when a run is blocked and another pane is open.
- The History rail badge shows when a run failed since the operator last looked.
- A run that ends while selected stays open with a strip saying it ended and linking to History.

## Activity

Activity replaces the "Recent telemetry history" feed. It is a master and detail pair.

The timeline groups by work item, then flow pass, then visit. One row is one visit, not one record.
Runs of successful deterministic steps fold into one line. Metric samples appear only under Raw,
and Raw hides them until asked.

Filters are search, a work-item selector, a Problems view that narrows, and Steps and Info logs
that add. Keys are `j` and `k` to move and `e` for the next problem, labelled on screen, and inert
while the operator types an answer. Following pauses when the operator scrolls, and a pill counts
what arrived, naming problems when the Problems view is on.

The reading pane depends on the kind of row:

- A turn shows a header with duration, model and cost. Prompt and thinking start collapsed.
  Messages read as prose. A tool call is one line, a failed one is red with its output, and runs of
  tools fold.
- A step shows the error, its logs, and what came next.
- A gate shows the question and the answer.

## Forces and the choices they produce

**Old runs must work on day one, so flow identity is derived.** Spans already link through their
parents, and a flow is the handoff under a state. Walking the parents gives time per flow for old
runs and archives. Stamping a new attribute would leave every existing run without flows.

**Hundreds of archives must list instantly, so each carries a stored summary.** Opening a frozen
archive for its totals would make History slow in proportion to its age. The archive manifest
gains cost, ending and active time. An archive that predates this gets its summary lazily, once.

**One Overview needs one query path.** The profile, node cost and loop queries already exist for
the terminal. The endpoints call them through the existing run-source redirect, on the query pool,
so an archive and a live run give the same shape.

**A live screen must not read the database on a clock.** The groom database reaches several
gigabytes. The live Overview refreshes when a telemetry batch commits, and the clock ticks in the
browser between commits.

**The sidecar owns the workspace, so its loss is not an error page.** The browser keeps the last
diff and its time. The tab says stale. A diff since the branch start needs the sidecar to know the
base, which it can compute from the checkout.

## Assumptions

- A run is one workflow on one branch, and a work item is what the workflow calls one. An item that
  a workflow does not report leaves that tab absent.
- The operator is one person on one machine. No screen handles concurrent answers beyond what gates
  already do.
- The node norm and median need enough history. Under five comparable runs, the comparison stays
  blank rather than showing a noisy number.

## What the review changed

A reader who had not seen the design judged the rendered mockups. Its findings reshaped the first
version:

- Answering moved inline above the diff, because a gate reachable only by leaving the diff defeated
  the point of moving the diff.
- Sidecar loss kept the last diff in place of an empty page.
- Failed runs gained a rail badge, an "ended while open" strip, a banner and a command.
- The cost comparison stopped praising failed runs, and live and History now divide the same way.
- The counts of problems, errors and alerts became one number.
- The Raw view stopped being a metric dump.
- Diff gained a "since branch start" view, because uncommitted work alone misses what the run has
  already committed.

The reader also asked for three things this design leaves out: side-by-side run comparison,
projected cost and budget warnings, and stop or rewind buttons on History. The per-node median and
the burn rate cover the decision to keep spending, and the command on a failed run covers
continuing it.

## Mapping to the existing system

- The dashboard stays vendored Preact with htm, with no build step and no CDN.
- The mockups link the dashboard's real stylesheet rules, and their additions are limited to new
  layouts on existing tokens.
- A run row gains a sidecar capability and its cost fields. The dashboard decides the tabs from
  those fields, and gating stays in the dashboard.
- Archived transcripts gain a route, because the current routes only serve live runs.
- The book pages for the dashboard, the changes view and the workspace flows change with the
  stories that change those screens.
