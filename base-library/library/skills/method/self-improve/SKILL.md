---
name: self-improve
description: "Running a continuous improvement loop beside a live process that nobody asked a question about: any loop an agent tends from a feed. Each cycle holds the last delivered unit against its own ideal path, one pass per stage with no retry, no hand step and no dead time, ranks the waste in the gap by how many units it recurred in, diagnoses the top one to a construct in the workflow, designs and lands the change at the size the tax sets, a prompt line or a rebuilt stage, while the run goes on, and reads the yardstick that grades it. The method skills are the loop's steps: isolating-causes and root-cause diagnose, decompose designs, whole-first and vet-proposal gate, step-back judges a change that keeps failing. Load when tending a run from a feed and about to acknowledge a notification, when a unit of work was just delivered, when asked whether a process wastes or converges, or when a run looks normal because nothing in the prompt said otherwise. For a question the operator already wrote, load research-study."
tags: [review, process]
---

# Self-improve a live process

An agent tending a process reads silence as approval. No budget in the prompt becomes an
unlimited budget. A lap that repeats the previous one looks like progress because it is
busy. The run looks normal because nothing said what normal is, and three notifications
in four end with "nothing needs action".

This skill is a **continuous improvement loop** that runs beside the process for its whole
life. The process delivers units. The loop takes one waste out of the workflow per cycle,
while the process goes on, and the next reading grades it. The attendant does not examine
and report. It examines, changes, verifies, and examines again. A tax written down and left
for later is paid by every unit until the loop removes it, and the hours between two
notifications are the loop's working time.

The reference is not a person, a budget or the previous run. It is the unit's own **ideal
path**: every stage passed once, no retry, no hand step, no dead time, nothing done and
undone. The delivered artifact fixes what the ideal path had to contain. Everything the run
did beyond it is **waste**, and every waste has a cause in the workflow: a prompt, a node, a
check, a gate or a tool. A waste that appears on two units is a **tax**, paid on every unit
left until the workflow changes.

## The mandate

The operator who started the loop handed the attendant the workflow for the run's life.
Every construct in it is the attendant's to change without asking, at any size: a prompt
line, a node, a gate, a tool, the order of the stages, a stage itself, or the lane the
stages form. Three things stay with the operator, and only these: what the unit is and what
accepts it, money spent beyond the run's own budget, and the output itself, which only the
process changes. A question about anything else is a tax parked with a question mark on it. Permission is not among the things a cycle waits on.

**"Nothing wrong" is a claim.** It stands only on the readings below. **"Improving" is a
claim too.** It stands only on a waste kind counted on one reading and absent on the next.

## The loop

```
read ─▶ measure ─▶ rank ─▶ diagnose ─▶ design ─▶ change ─▶ verify ─┐
 ▲                                                                  │
 └──────────────────────────────────────────────────────────────────┘
```

| Step | What it produces | Method |
| --- | --- | --- |
| Read | one reading line per notification | this skill |
| Measure | the unit's ideal and actual path, its waste by kind | this skill |
| Rank | the kind table with recurrence, judged by a fresh reader | this skill |
| Diagnose | the construct in the workflow behind the top tax | [[isolating-causes]] for the contrast, [[root-cause]] for the chain |
| Design | the change, as a note | [[decompose]] when it crosses modules or adds a concept |
| Change | the change gated, landed and loaded into the run | [[whole-first]] and [[vet-proposal]] as the gate, [[workhorse-operate]] for the reload |
| Verify | the yardstick's count before and after | this skill, [[step-back]] after three failed changes on one kind |

The method skills are steps of this loop, run in place by the attendant, in the cycle they
belong to. A cycle is complete when its change is loaded and its yardstick is named. The
next cycle starts at once on the next tax in the table. Several cycles may be open at a
time, one per kind, each waiting only on its own yardstick.

[[research-study]] answers a question the operator wrote. The loop here produces the
questions, and takes a routed one into research-study only when the operator asks for it.

## The clock

The process sets the loop's pace in two ways:

- **Every notification**, ten to thirty minutes apart, is a **read**. It gets one line in a
  fixed shape, so lines compare across ticks:

  ```
  <stage> · lap <k>, stage median <m> · turn <elapsed> · doing: <phrase from the transcript> · seen before: <lap or none> · working: <tax in hand, or converged>
  ```

  "Doing" names what the current turn is at, read from its transcript, not from the node
  name. "Seen before" names the earlier lap of this unit that did the same thing, or none.
  "Working" names the tax the attendant is removing between this tick and the next. That
  line is the acknowledgement. A line without "doing" and "seen before" is a check not
  made. A line reading "working: none" while the table holds a tax is the attendant's own
  dead time, and it counts like any other. A lap count above the stage's median, or a "seen
  before" that names a lap, starts a measure at once, while a rewind can still save the
  rest of the unit.
- **Every unit delivered**, and the run's end, is a full **measure** and **rank**: the whole
  table rebuilt with the new unit, the fresh judge, and the grade of every open cycle. A
  unit is a story through its gate, a book round closed, a benchmark task scored.

Between ticks, the loop runs the diagnose, design and change steps of the top open tax. A
notification interrupts for its reading line and the work resumes.

Everything appends to one file, `EXAMINED.md`, in the run's directory beside its event log.
The run directory is the run's record. The next cycle and the fresh judge read the previous
ones from there.

## The records

Work from what the process recorded: the telemetry store, the ledger, the turn transcripts,
the checker reports, the git log of what it delivered. The code says what the process was
meant to do. The records say what it did. For a workhorse run the store and the commands
that read it are in [[groom-telemetry]]. The workflow's code is read in the diagnose step,
once a waste kind points at it.

A process that left no record of a stage has a tax before anything else is read: the stage
is unrecorded, and recording it is the first change.

## Measure

Name the **unit of delivery**: the thing the operator gets, such as a story merged, a page
written, a surface documented. For the unit just delivered, draw the ideal path: one box per
stage, in order, each passed once. Beside each box write what the run did: visits, laps,
turns, retries, minutes, and what came out. The gap is the unit's waste, in minutes per
stage, from the records.

Every minute in the gap belongs to one kind. Read the records for each kind at every stage,
and write the reading even when it is zero:

| Kind | What it is in the records | What produces it |
| --- | --- | --- |
| Rework lap | a stage visited again after its verdict, on the same unit | the previous lap's output did not meet the next stage's check |
| Repeat turn | a turn doing what an earlier turn of this unit did | lost state, a stale handoff, a prompt that re-asks |
| Retry | a tool call that fails and is called again, worked around or ignored | a defect in the instrument |
| Hand step | work a stage should have done, done after it by a tail commit or the operator | a stage that stops before its output is finished |
| Dead time | the run stopped, waiting on a gate, a lock, a quota or a person | a stall the workflow does not route around |
| Undone work | an edit, file or commit made and later reverted or deleted | a stage that acts before the check that rejects it |
| Open loop | an output no later stage and no person reads, a defect filed nowhere | a stage with no receiver |

A kind named without the lap, turn or commit it rests on is a guess. Each row carries its
evidence and its minutes. Done when every stage has an ideal count, an actual count, the
minutes between, and a reading for every kind.

## Rank

Set this unit's table beside the previous units'. For each kind, count the units it appeared
in, out of the units delivered. That count is the rank.

- **Two units make a tax.** A kind seen on two units will be seen on every unit left. Its
  price is its minutes per unit times the units remaining. A tax of three minutes on thirty
  remaining units outranks a one-off of an hour.
- **A one-off is a note.** It joins the table and waits for a second occurrence. It becomes a
  tax on its own only when it alone exceeds the unit's ideal path.
- **The previous unit is a reading, never a reference.** A unit that cost what the last one
  cost, with the same waste, shows the tax is stable. Stable is the problem.

Spend in dollars, and what a person would need, belong to a different question: whether to
run the process at all. That answer goes on one line at run end, once. It never ranks a
tax, and it never clears one.

**The fresh judge.** The one who drew the paths does not grade them. Their frame produced
the table, and it holds the blind spots the workflow's author held. Hand the table to a
reader with fresh context on every measure: a new agent started from a written brief, never
a fork of the attendant, on the cheapest model that reasons well. Skipping it when the table
is short is skipping it when the blind spot is in play. The brief carries the two paths with
minutes per stage, the kind table with its recurrence counts over every unit, and one
question: **which waste here will the next unit pay again, and what in the workflow produces
it?** The judge argues for the next unit, not for the run. It returns the kinds it expects
to recur, ranked by minutes per unit, each with the lap, turn or commit it rests on and the
construct it suspects. The attendant adds them to the table and does not overrule them.

The ranked table is the loop's queue. The top tax with no cycle open is the next cycle.

## Diagnose

Read the transcript of each occurrence of the tax, oldest first, and name the construct in
the workflow that produced it: the prompt section that stops a stage short, the node that
runs before its check, the gate that accepts unfinished output, the tool that fails. Read the
workflow's code now, at that construct only.

Two tests before the name stands:

- **Contrast.** If the kind appears on some units and not others, run [[isolating-causes]]:
  what differs between the units that paid and the units that did not.
- **Origin.** Ask why the construct behaves so, and why that, until the answer is a property
  of the workflow and not of the unit. [[root-cause]] holds the chain. A tail commit that
  restamps citations is produced by a documentation stage that does not restamp, not by the
  story that needed restamping. A change that adds a cleanup stage handles the symptom. A
  change that makes the stage finish its output reaches the origin.

Done when the construct is named with the file and the lines, and the why-chain ends on the
workflow.

## Design

Write the change before making it: the construct, what it becomes, the kind it removes, and
the yardstick. The yardstick is the first reading that can show the kind gone, not the next
unit by default: a prompt change is read at the stage's next visit, a tool fix at the tool's
next call, a gate change at the next gate. One change per kind in flight. Two changes aimed
at one kind would share a yardstick and answer for neither. Changes on different kinds each
have their own, so several cycles run at once.

The tax sets the size of the change, not the gap between two ticks. Price the change in
minutes to design, build and land, against the tax's minutes per unit times the units left.
When the tax is the larger number the change is made at whatever size it needs, and a stage
rebuilt or removed is one cycle like a prompt line is. Lean has the two words: **kaizen**,
the small step every cycle takes, and **kaikaku**, the rebuild when the small steps have
stopped moving the count or the tax dwarfs them. A stage whose single first pass costs
more than the unit's whole ideal path is a kaikaku candidate on its first reading.

A change that crosses two modules, adds a concept, or gives the workflow a second way to do
something runs [[decompose]] here, and its design note is the change written. A rebuild
then runs [[vertical-slicing]] on the note, and its first slice is this cycle's change,
with the stage's next visit as its yardstick. The size of the design is not a reason to
wait for the run to end, and the build follows the note in the same cycle.

Three entries that look like a place to leave the tax are not:

- **"Route: operator"** is a question about one of the three things the mandate leaves with
  the operator, asked now with a recommendation through the run's gate or the operator's
  inbox, with the work that does not depend on the answer done. Any other question the
  attendant answers itself.
- **An open loop** has the attendant as its receiver. A defect with no owner is filed now,
  as a story, an issue or a fix, and the filing is the evidence the row closes on.
- **"After the run"** names a boundary and the reason the run must end first. Without the
  reason it is waiting, and the row stays open at the top of the queue.

## Change

Gate the design. [[vet-proposal]] decides whether the change deserves to exist as written,
and [[whole-first]] joins it when the change adds a construct the workflow did not have. A
change that fails the gate goes back to diagnose with the reason. The gate judges fit, never
size: a rebuild that fits is landed, slice by slice.

A study the loop started under [[research-study]] ends with a verdict, and a verdict that
names what has to replace the current shape is a design written. It re-enters the cycle
here, and the build is the next step, not a question to the operator.

Then land it and make the run pick it up at its next boundary. For a workhorse run that is
a commit on the workflow and a `reload` from [[workhorse-operate]]. The run's state is not
edited. The change lives in the workflow, where every later unit and every later run
inherits it.

A fix that needs something the run holds, such as the device, the backend or the checkout,
is priced, not parked: the tax per unit times the units left, against the minutes the run
loses while the resource is borrowed. When the tax wins, borrow it at the next turn
boundary, take the measurement or land the fix, and resume. When the run wins, do every part
that does not need the resource now, and write the boundary at which the rest lands.

Done when the change is committed, the run reports the new code, and `EXAMINED.md` names
the change, its yardstick and the boundary it is read at.

## Verify

Read the yardstick at the first boundary it names, and write the count before and after. At
the next measure set every other kind beside its previous reading too, not only the one the
change aimed at. A change that moved its own kind to zero and raised another is the siloed
fix [[whole-first]] warns about, and the rise is the next tax.

- Count at zero: the cycle closes. Say so in one line.
- Count unchanged or higher: the cycle reopens with the new occurrence as evidence, back at
  diagnose. Three kaizen changes aimed at one kind with the count still standing is the
  stream [[step-back]] judges, in place, before a fourth, and its usual answer is kaikaku:
  the stage rebuilt, through design.

## Convergence

The queue empties when no kind appears on two units and the one-offs are each below the
unit's ideal path. The process has **converged**. Say so once. The read step keeps running,
and the first kind seen twice opens a new cycle.

## The report

Written at every measure, one screen. Lead with the top tax, as one sentence: the kind, the
units it appeared in, its minutes per unit, and the cycle open on it. Then at most five
kinds, ranked by recurrence, each with its evidence, its construct and its cycle's state.

Then the **grades**: every change whose boundary has passed, its kind's count before and
after, and every other kind before and after.

Then the **null report**: one line per kind, saying which stages were read and what each
read. A line the attendant cannot fill is a check not made. A report that says the process
is fine and carries no table has examined nothing.

Close with one verdict: **improving** when the last change removed its kind, **taxed** when
a kind recurs and no cycle is open on it, **converged** when no kind recurs, **unrecorded**
when a stage left no record. At run end add the one adoption line: wall time and bill
against what a person would need.

## Completion criterion

Each line checkable from `EXAMINED.md` alone:

- Every notification got a reading line in the fixed shape, with "doing", "seen before"
  and "working" filled, and none says "working: none" while the table holds a tax.
- Every delivered unit has its ideal path and actual path side by side, with minutes per
  stage and a reading for every kind, zero readings included, each with its evidence.
- Every kind carries its recurrence count over the units delivered, and a fresh judge's
  expected recurrences are in the table.
- Every tax has a cycle open: a construct with a why-chain ending on the workflow, a change
  committed and loaded with its yardstick and boundary, or the gate's reason it has none.
- Every change is priced against its tax, and no row waits on a permission the mandate
  already grants.
- Every change whose boundary has passed carries its count before and after, and every
  measure sets every kind beside its previous reading.
