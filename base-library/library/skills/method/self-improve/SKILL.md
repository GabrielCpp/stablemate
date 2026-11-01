---
name: self-improve
description: "Running a continuous improvement loop beside a process that delivers units, as a loop an agent tends from a feed or as the way a goal's track is worked. Each cycle holds the last unit against its ideal path, one pass per stage with no retry, no hand step and no dead time, profiles the gap by stage and waste kind with each item's reach and roof, ranks the waste by its cost on every unit left, takes one problem under a cap, finds its cause as a construct of the workflow or its producer, sorts it as execution or design, lands the smallest fix at the cause, reads it through the cheapest instrument, and grades it held, missed or released. Load when tending a run from a feed and about to acknowledge a notification, when a unit was just delivered, when asked whether a process wastes or converges, or when a run looks normal because nothing said otherwise. For a question with no mechanism yet, load explore-then-improve."
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
for later is paid by every unit until the loop removes it.

The reference is not a person, a budget or the previous run. It is the unit's own **ideal
path**: every stage passed once, no retry, no hand step, no dead time, nothing done and
undone. The delivered artifact fixes what the ideal path had to contain. Everything the run
did beyond it is **waste**, and every waste has a cause in the workflow: a prompt, a node, a
check, a gate or a tool. A waste that appears on two units is a **tax**, paid on every unit
left until the workflow changes.

When a caller hands this loop a goal with its dimensions in order, the purpose is that goal:
the unit is the goal's unit, the dimensions decide which waste counts first, and the loop
runs until the caller reads the goal again. Beside a live process with no caller, the purpose
is the process's own, and the loop runs for the process's life.

## The mandate

The operator who started the loop handed the attendant the workflow for the run's life.
Every construct in it is the attendant's to change without asking, at any size: a prompt
line, a node, a gate, a tool, the order of the stages, a stage itself, or the lane the
stages form. Three things stay with the operator, and only these: what the unit is and what
accepts it, money spent beyond the run's own ceiling, and the output itself,
which only the process changes. A question about anything else is a tax parked with a
question mark on it. Permission is not among the things a cycle waits on.

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
| Read | one reading line per unit source | this skill |
| Measure | the unit's ideal and actual path, its waste by kind, each item's reach and roof | this skill |
| Rank | the kind table priced per unit left, judged by a fresh reader, one problem in hand under a cap | this skill |
| Diagnose | the construct behind the top tax, with its contrast, its why-chain and its cause class | [[isolating-causes]] for the contrast, [[root-cause]] for the chain |
| Design | the smallest change at the cause, registered with its prediction, estimate and cap | [[decompose]] when it crosses modules or adds a concept |
| Change | the change gated, landed and read through the cheapest instrument | [[whole-first]] and [[vet-proposal]] as the gate |
| Verify | held, missed or released, with the count before and after | this skill, [[step-back]] after three failed changes on one kind |

The method skills are steps of this loop, run in place by the attendant, in the cycle they
belong to. A cycle is complete when its change is loaded and its yardstick is named. The
next cycle starts at once on the next tax in the table. Several cycles may be open at a
time, one per kind, each waiting only on its own yardstick.

## The clock

A unit reaches the loop from one of two sources, and the loop names which:

- **A feed.** The process delivers on its own. Every notification, ten to thirty minutes
  apart, is a **read** and gets one line in a fixed shape, so lines compare across ticks:

  ```
  <stage> · lap <k>, stage median <m> · turn <elapsed> · doing: <phrase from the transcript> · seen before: <lap or none> · working: <tax in hand, or converged>
  ```

  "Doing" names what the current turn is at, read from its transcript, not from the node
  name. "Seen before" names the earlier lap of this unit that did the same thing, or none.
  "Working" names the tax the attendant is removing between this tick and the next. A line
  without "doing" and "seen before" is a check not made. A line reading "working: none"
  while the table holds a tax is the attendant's own dead time, and it counts like any
  other. A lap count above the stage's median, or a "seen before" that names a lap, starts
  a measure at once, while a rewind can still save the rest of the unit.
- **A paid run.** No feed delivers, so the loop runs the unit itself, at the cheapest rung
  of the instrument ladder under "Change" that reads what the cycle needs. Before each run,
  name the record already paid for that answers the same question, or why none does. A
  record that answers is cited, not re-run.

Every unit delivered, from either source, is a full **measure** and **rank**: the whole
table rebuilt with the new unit, the fresh judge, and the grade of every open cycle.
Between units, the loop runs the diagnose, design and change steps of the top open tax.

Everything appends to one file, `EXAMINED.md`, in the run's directory beside its event log,
or in the caller's working directory. The next cycle and the fresh judge read the previous
ones from there.

## The records

Work from what the process recorded: the telemetry store, the turn transcripts,
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
turns, retries, minutes, money, and what came out. The gap is the unit's waste, per stage,
from the records.

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
| Oversize pass | a stage's single pass costing more than its ideal term | an input larger than the stage reads, or work the unit never needed |

The last kind is the profile's own: a stage that costs more than its term on the ideal path
even when it passes once. Break its cost down by turn, by test, by call or by failure kind,
from what the system records, or add the recording first. A total says a stage is slow. A
breakdown says one fixture runs 400 times, or one turn reads the whole corpus. A timed
breakdown records the script, its hash, and the machine's load at the start and the end,
with repeated short readings on a shared machine.

For each item in the gap write its **reach**: what the unit's cost reads if the item went
to zero, held against the purpose. An item whose vanishing moves the unit less than the
reading can resolve is not a problem, whatever its share. Write the **roof** of each large
item too: the fastest the hardware or the task allows for the work it does. An item near its
roof needs less work, not more tuning, and its problem is the work's existence.

A kind named without the lap, turn or commit it rests on is a guess. Each row carries its
evidence, its minutes and its money. Done when every stage has an ideal term, an actual
cost, the gap between, a reading for every kind, and every item in the gap has its reach
and, when large, its roof.

## Rank

Set this unit's table beside the previous units'. For each kind, count the units it appeared
in, out of the units delivered. That count, times the item's reach, is the rank.

- **Two units make a tax.** A kind seen on two units will be seen on every unit left. Its
  **price** is its waste per unit times the units remaining, in the purpose's own units,
  or minutes for a live run with no purpose written. A tax of three minutes
  on thirty remaining units outranks a one-off of an hour.
- **A one-off is a note.** It joins the table and waits for a second occurrence. It becomes a
  tax on its own only when it alone exceeds the unit's ideal path.
- **The previous unit is a reading, never a reference.** A unit that cost what the last one
  cost, with the same waste, shows the tax is stable. Stable is the problem.

Whether to run the process at all is a different question, answered on one line at run end.
It never ranks a tax, and it never clears one.

**The fresh judge.** The one who drew the paths does not grade them. Their frame produced
the table, and it holds the blind spots the workflow's author held. Hand the table to a
reader with fresh context on every measure: a new agent started from a written brief, never
a fork of the attendant, on the cheapest model that reasons well. Skipping it when the table
is short is skipping it when the blind spot is in play. The brief carries the two paths with
their costs per stage, the kind table with its recurrence counts over every unit, and one
question: **which waste here will the next unit pay again, and what in the workflow produces
it?** The judge argues for the next unit, not for the run. It returns the kinds it expects
to recur, ranked by cost per unit, each with the lap, turn or commit it rests on and the
construct it suspects. The attendant adds them to the table and does not overrule them. The
judge reads records and runs nothing.

The ranked table is the loop's queue. Take
the top tax with no cycle open whose reach clears the floor and whose cheapest instrument
fits the budget left, and mark it **in hand**. One problem is in hand at a time per kind: a
fix that would touch two problems at once is two fixes measured apart. Set its **cap** at
registration: the problem's reach as a share of the unit's total gap to the ideal path, times the
budget left, in money and hours. A budget with no money left leaves a cap in hours alone,
and every reading of the problem then comes from a record. The cap is what the loop may spend on this problem, cause-finding included, before
it releases it.

Done when the table carries every kind's recurrence and price, the judge's expected
recurrences, and one problem in hand with its cap in money and hours.

## Diagnose

A problem's cause is a decision in the system: a line of a prompt, a loop bound, a default,
a retry, a step that runs when nothing needs its output, an input larger than the step
reads, a check that fails for a reason nobody looks at. A stage name is where the cost sits,
not why. The fix goes at the why.

Read the transcript of each occurrence of the tax, oldest first. Then load
[[isolating-causes]] and run its loop here, before any cause is written down: show the cost
on demand through the cheapest rung of the instrument ladder, contrast the units that pay it
with the units that do not, and change one variable at a time until one cause is confirmed.
The traces of runs already paid for answer most of this at no cost: read them before running
anything. The row holds the contrast: which units pay, which do not, and the one variable
that separates them.

Then load [[root-cause]] and write its why-chain into the row: why the cost exists, what
decision caused that, how it could have been prevented, asked again on the prevention until
the answer is a property of the task or of the process that produces the system's inputs.
The chain stops at a producer, never at its product. A defect in an artifact another process
produced, a document, a plan, a fixture, a generated file, a prompt rendered from a template,
is a symptom: the producer will produce it again, and the question the chain asks is why the
producer let it through, which construct of the producer, and whether the producer's own
check ran on it. A tail commit that repairs a stage's output is produced by the stage that
does not finish its output, not by the unit that needed repairing.

Last, sort the cause into its **class**, by one question: would removing this waste redraw
the mechanism's ideal path?

- **Execution cause.** The stages stay as they are and one of them stops wasting: a prompt
  line, a bound, a check, a tool. The fix is this loop's, at the size the tax sets.
- **Design cause.** The waste is inherent to a decision of the mechanism: a stage exists
  that the unit does not need, two stages redo each other's work, a stage's single pass
  costs more than its term because of what it was built to do. Removing it redraws the
  ideal path. Redraw the path with the cost inherent and hand it to the caller, who judges
  whether the mechanism still serves the goal. One that does returns here with the new path
  as the reference. One that does not is dead, and this loop releases every problem on it.

Done when the row holds the contrast and the why-chain, the cause is named as a construct
of the producer or the process with the file and the lines, its class is written, and one
sentence predicts what the unit's cost reads once it changes.

## Design

Write the change before making it: the construct, what it becomes, the kind it removes, the
prediction from the diagnosis, the estimate in minutes and money from the instrument's
price, the cap from the rank, and the yardstick. Write the smallest change that removes the
cause. Removing work beats making it cheaper, and making it cheaper beats making it faster.
One variable per fix, on the same yardstick.

The fix lands where the why-chain stopped. When that is a producer, the fix changes the
producer, and the artifact it produced is repaired beside it only to unblock the reading, as
its own row that names the producer fix it stands in for. A retry, a cap, a sleep, a skip, a
default, a fallback, a smaller model or a hand repair of an artifact is a **symptom fix**.
It is taken only with the chain in its row saying why the cause is out of reach, and its
`EXAMINED.md` line says it is a symptom fix, so the next reader knows the cause still stands.

The yardstick is the first reading that can show the kind gone, not the next unit by
default: a prompt change is read at the stage's next visit, a tool fix at the tool's next
call, a gate change at the next gate. One change per kind in flight. Two changes aimed at
one kind would share a yardstick and answer for neither.

The tax sets the size of the change, not the gap between two ticks. Price the change in
minutes to design, build and land, against the tax's price. When the tax is the larger
number the change is made at whatever size it needs, and a stage rebuilt or removed is one
cycle like a prompt line is. Lean has the two words: **kaizen**, the small step every cycle
takes, and **kaikaku**, the rebuild when the small steps have stopped moving the count or
the tax dwarfs them. Both keep the mechanism's stages, so both are execution fixes. A change
that drops or merges a stage is a design cause and goes to the caller first.

A change that crosses two modules, adds a concept, or gives the workflow a second way to do
something runs [[decompose]] here, and its design note is the change written. A rebuild
then runs [[vertical-slicing]] on the note, and its first slice is this cycle's change,
with the stage's next visit as its yardstick.

Three entries that look like a place to leave the tax are not:

- **"Route: operator"** is a question about one of the three things the mandate leaves with
  the operator, asked now with a recommendation through the run's gate or the operator's
  inbox, with the work that does not depend on the answer done.
- **An open loop** has the attendant as its receiver. A defect with no owner is filed now,
  as a story, an issue or a fix, and the filing is the evidence the row closes on.
- **"After the run"** names a boundary and the reason the run must end first. Without the
  reason it is waiting, and the row stays open at the top of the queue.

Done when the row holds the construct, the change, the prediction, the estimate, the cap
and the yardstick, and a symptom fix is labelled as one.

## Change

Gate the design. [[vet-proposal]] decides whether the change deserves to exist as written,
and [[whole-first]] joins it when the change adds a construct the workflow did not have. A
change that fails the gate goes back to diagnose with the reason. The gate judges fit, never
size: a rebuild that fits is landed, slice by slice.

Then land it and make the run pick it up at its next boundary. For a workhorse run that is
a commit on the workflow and a `reload` from [[workhorse-operate]]. The run's state is not
edited. The change lives in the workflow, where every later unit and every later run
inherits it.

Read the change through the **cheapest instrument**: the smallest apparatus that reads the
variable the change moved, at the resolution the floor needs. Freeze every input the
variable's stage receives from upstream, once, as a fixture, cut everything downstream the
reading does not need, and collapse down the ladder as far as the reading survives:

| Rung | Runs | Reads |
| --- | --- | --- |
| a trace | nothing: the record of a run already paid for | what happened, replayed under the change on paper |
| one turn | one prompt on a frozen context | what the turn does and spends |
| one stage | the stage on its frozen inputs | the stage's cost and output |
| whole system | every stage on a real unit | the purpose itself |

Each rung up costs about an order of magnitude more. Take the cheapest rung that still reads
the variable, and price it from one run. A reading the trace already holds is never bought
again. An instrument that costs more than a tenth of the budget left says in the row why no
lower rung reads the variable. A fix proven on one stage is confirmed on the whole system
once, when the loop claims the process serves its purpose, and not at every run. Before the
expensive part runs, compute the best result the run could show from its inputs alone: a
best case under the prediction kills the run before it costs anything. A probe past twice
its estimate is stopped, its row keeps the partial reading, and the estimate is a finding.

A fix that needs something the run holds, such as the device, the backend or the checkout,
is priced, not parked: the tax's price against the minutes the run loses while the resource
is borrowed. When the tax wins, borrow it at the next turn boundary, take the measurement or
land the fix, and resume. When the run wins, do every part that does not need the resource
now, and write the boundary at which the rest lands.

Done when the change is committed, the run reports the new code, and `EXAMINED.md` names
the change, its instrument with its rung and price, and the boundary it is read at.

## Verify

Read the yardstick at the first boundary it names, project it to the full workload, and
hold it against the purpose and against the prediction, in the row: "30 min a page × 1,000
pages is 3 weeks against 8 hours: 60× off." The reading has one of three verdicts:

- **Held.** The kind's count fell by at least the floor, in the direction predicted. Keep
  the change, write the line as worked, and set every other kind beside its previous
  reading too. A change that moved its own kind to zero and raised another is the siloed fix
  [[whole-first]] warns about, and the rise is the next tax.
- **Missed.** The count moved less than the floor, or the other way. The cause was wrong or
  incomplete, and the reading is new evidence. Go back to diagnose once, with the reading in
  the contrast. A second miss on the same problem releases it.
- **Released.** The cap is spent, or the best case killed the run. Write the line with the
  reason, take the next problem, and never spend the released problem's past cost as an
  argument for one more probe on it. Three kaizen changes aimed at one kind with the count
  still standing is the stream [[step-back]] judges, in place, before a fourth, and its
  usual answer is kaikaku or a design cause.

Releasing is what the budget buys. Sitting out a run past its estimate, or trying the
released fix again with more of the same, is what patience buys.

Done when the row carries its verdict and `EXAMINED.md` carries the line.

## Convergence

The queue empties when no kind appears on two units and the one-offs are each below the
unit's ideal path. The process has **converged**. Say so once. The read step keeps running,
and the first kind seen twice opens a new cycle.

Under a caller, the loop also ends when the caller reads the goal again and says the process
serves it. The waste still above the ideal path is priced per unit in the report, and a loop
beside the live process keeps removing it.

## The report

Written at every measure, one screen. Lead with the top tax, as one sentence: the kind, the
units it appeared in, its price per unit, and the cycle open on it. Then at most five kinds,
ranked by price, each with its evidence, its construct, its cause class and its cycle's
state.

Then the **grades**: every change whose boundary has passed, its verdict, its kind's count
before and after, and every other kind before and after.

Then the **null report**: one line per kind, saying which stages were read and what each
read. A line the attendant cannot fill is a check not made. A report that says the process
is fine and carries no table has examined nothing.

Close with one verdict: **improving** when the last change held, **taxed** when a kind
recurs and no cycle is open on it, **converged** when no kind recurs, **unrecorded** when a
stage left no record. At run end add
the one adoption line: wall time and bill against what a person would need.

## Completion criterion

Each line checkable from `EXAMINED.md` alone:

- Every unit source got its reading: a line in the fixed shape per notification with
  "doing", "seen before" and "working" filled, or a paid run with the record it cites.
- Every delivered unit has its ideal path and actual path side by side, with cost per
  stage, a reading for every kind, zero readings included, and each gap item's reach.
- Every kind carries its recurrence count and its price, and a fresh judge's expected
  recurrences are in the table.
- Every tax has a cycle open: a problem in hand with its cap, a construct with a contrast,
  a why-chain ending on the workflow or its producer and a cause class, a change committed
  with its prediction, instrument and boundary, or the gate's reason it has none.
- Every design cause went to the caller before its change, and every symptom
  fix is labelled as one.
- Every change whose boundary has passed carries its verdict with the count before and
  after, and every measure sets every kind beside its previous reading.
