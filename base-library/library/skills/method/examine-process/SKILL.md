---
name: examine-process
description: "Improving a running process that nobody asked a question about: a coder run, a book pipeline, a benchmark, any loop an agent tends from a feed. Each delivered unit is held against its own ideal path, one pass per stage with no retry, no hand step and no dead time. Everything in the gap is waste, classified by kind, ranked by how many units it recurred in, traced to the construct in the workflow that produces it, and removed by one change before the next unit starts. The next unit grades the change. Load when tending a run from a feed and about to acknowledge a notification, when a unit of work was just delivered, when asked whether a process wastes or converges, or when a run looks normal because nothing in the prompt said otherwise. For a stream of attempts stuck on one goal, load step-back. For a question already in hand, load research-study."
tags: [review, process]
---

# Examine a process

An agent tending a process reads silence as approval. No budget in the prompt becomes an
unlimited budget. A lap that repeats the previous one looks like progress because it is
busy. The run looks normal because nothing said what normal is, and three notifications
in four end with "nothing needs action".

A process improves only when a waste it paid on one unit is gone by the next. The reference
for that is not a person, a budget or the previous run. It is the unit's own **ideal path**:
every stage passed once, no retry, no hand step, no dead time, nothing done and undone.
The delivered artifact fixes what the ideal path had to contain. Everything the run did
beyond it is **waste**, and every waste has a cause in the workflow: a prompt, a node, a
check, a gate or a tool. A waste that appears on two units is a **tax**, paid on every unit
left until the workflow changes.

**"Nothing wrong" is a claim.** It stands only on the readings below. **"Improving" is a
claim too.** It stands only on a waste kind counted on one unit and absent on the next.

[[step-back]] judges a stream of attempts once a count trips. [[research-study]] answers a
question the operator wrote. This skill sits before both: it finds the tax, changes the
workflow to remove it, and checks the next unit for it. The loop closes inside the skill.

## Two tiers

A feed delivers a notification every ten to thirty minutes. A full examination at that rate
would cost more than the run, so the work splits in two:

- **On every notification**, the **reading**: one line in a fixed shape, so lines compare
  across ticks:

  ```
  <stage> · lap <k>, stage median <m> · turn <elapsed> · doing: <phrase from the transcript> · seen before: <lap or none>
  ```

  "Doing" names what the current turn is at, read from its transcript, not from the node
  name. "Seen before" names the earlier lap of this unit that did the same thing, or none.
  That line is the acknowledgement. A line without "doing" and "seen before" is a check not
  made. A lap count above the stage's median, or a "seen before" that names a lap, starts an
  examination at once, while a rewind can still save the rest of the unit.
- **On every unit delivered**, and at run end, the **examination**: steps 1 to 7 below, with
  the judge. A unit is a story through its gate, a book round closed, a benchmark task scored.

Both tiers append to one file, `EXAMINED.md`, in the run's directory beside its event log.
The run directory is the run's record. The next examination and the fresh judge read the
previous one from there, and the previous examination's change is the first thing the next
one grades.

## The records

Work from what the process recorded: the telemetry store, the ledger, the turn transcripts,
the checker reports, the git log of what it delivered. The code says what the process was
meant to do. The records say what it did. For a workhorse run the store and the commands
that read it are in [[groom-telemetry]]. The workflow's code is read in step 5, once a
waste kind points at it.

A process that left no record of a stage has a finding before anything else is read: the
stage is unrecorded, and recording it is the first change.

## 1. Draw the ideal path and the actual one

Name the **unit of delivery**: the thing the operator gets, such as a story merged, a page
written, a surface documented. For the unit just delivered, draw the ideal path: one box per
stage, in order, each passed once. Beside each box write what the run did: visits, laps,
turns, retries, minutes, and what came out.

The gap between the two columns is the unit's waste. Write it per stage in minutes, from the
records. Done when every stage has an ideal count, an actual count and the minutes between.

## 2. Classify the waste by kind

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

A kind named without the lap, turn or commit it rests on is a guess. Each row of the table
carries its evidence and its minutes.

## 3. Rank by recurrence

Set this unit's table beside the previous units'. For each kind, count the units it appeared
in, out of the units delivered. That count is the rank.

- **Two units make a tax.** A kind seen on two units will be seen on every unit left. Its
  price is its minutes per unit times the units remaining. A tax of three minutes on thirty
  remaining units outranks a one-off of an hour.
- **A one-off is a note.** It joins the table and waits for a second occurrence. It becomes a
  finding on its own only when it alone exceeds the unit's ideal path.
- **The previous unit is a reading, never a reference.** A unit that cost what the last one
  cost, with the same waste, shows the tax is stable. Stable is the problem.

Spend in dollars, and what a person would need, belong to a different question: whether to
run the process at all. That answer goes on one line at run end, once. It never ranks a
finding, and it never clears one.

## 4. The fresh judge

The one who drew the paths does not grade them. Their frame produced the table, and it holds
the blind spots the workflow's author held. Hand the table to a reader with fresh context on
every examination: a new agent started from a written brief, never a fork of the examiner, on
the cheapest model that reasons well. Skipping it when the table is short is skipping it when
the blind spot is in play.

The brief carries three things and no reasoning:

- the two paths from step 1, with minutes per stage,
- the kind table from step 2 and the recurrence counts from step 3, this unit and the previous ones,
- one question: **which waste here will the next unit pay again, and what in the workflow produces it?**

The judge argues for the next unit, not for the run. It returns the kinds it expects to recur,
ranked by minutes per unit, each with the lap, turn or commit it rests on and the construct it
suspects. The examiner adds them to the table and does not overrule them.

## 5. Name the construct

Take the top tax. Read the transcript of each occurrence, oldest first, and name the construct
in the workflow that produced it: the prompt section that stops a stage short, the node that
runs before its check, the gate that accepts unfinished output, the tool that fails. Read the
workflow's code now, at that construct only.

Two tests before the name stands:

- **Contrast.** If the kind appears on some units and not others, [[isolating-causes]] holds
  the move: what differs between the units that paid and the units that did not.
- **Origin.** Ask why the construct behaves so, and why that, until the answer is a property
  of the workflow and not of the unit. [[root-cause]] holds the chain. A tail commit that
  restamps citations is produced by a documentation stage that does not restamp, not by the
  story that needed restamping. A change that adds a cleanup stage handles the symptom. A
  change that makes the stage finish its output reaches the origin.

Done when the construct is named with the file and the lines, and the why-chain ends on the
workflow.

## 6. Change the workflow

Write the change before making it: the construct, what it becomes, the kind it removes, and
the yardstick, which is that kind's count on the next unit. One change per examination. A
second change on the same unit makes the next unit grade two things at once and answer for
neither.

Gate it. [[vet-proposal]] decides whether the change deserves to exist as written, and
[[whole-first]] joins it when the change adds a construct the workflow did not have. A
change that fails the gate goes back to step 5 with the reason.

Then land it and make the run pick it up before the next unit starts. For a workhorse run
that is a commit on the workflow and a `reload` from [[workhorse-operate]]. The run itself
is not touched: no rewind, no answer, no edit to its state. The change lives in the
workflow, where every later unit and every later run inherits it.

Done when the change is committed, the run reports the new code, and `EXAMINED.md` names
the change and its yardstick.

## 7. Grade the change on the next unit

The next examination opens with the previous change. Set the removed kind's count on the new
unit beside its count before. Then set every other kind beside its previous reading, not
only the one the change aimed at. A change that moved its own kind to zero and raised
another is the siloed fix [[whole-first]] warns about, and the rise is the next tax.

- Count at zero: the change holds. Say so in one line and take the next tax.
- Count unchanged or higher: the finding reopens with the new occurrence as evidence, and
  step 5 runs again on it. Three changes aimed at one kind with the count still standing is
  the stream [[step-back]] judges.

## When the loop stops

The loop takes up a tax while there is one. When no kind appears on two units and the
one-offs are each below the unit's ideal path, the process has **converged**. Say so once.
The reading tier keeps running, and the first kind seen twice reopens the loop.

## The report

The report fits one screen. Lead with the top tax, as one sentence: the kind, the units it
appeared in, its minutes per unit, and the change made or the reason none was. Then at most
five kinds, ranked by recurrence, each with its evidence, its construct and its change or
its routing.

Then the **grade**: the previous change, its kind's count before and after, and every other
kind before and after.

Then the **null report**: one line per kind, saying which stages were read and what each
read. A line the examiner cannot fill is a check not made. A report that says the process is
fine and carries no table has examined nothing.

Close with one verdict: **improving** when the last change removed its kind, **taxed** when
a kind recurs and no change has landed, **converged** when no kind recurs, **unrecorded**
when a stage left no record. At run end add the one adoption line: wall time and bill
against what a person would need.

## Completion criterion

Each line checkable from `EXAMINED.md` alone:

- Every notification since the last examination got a reading line in the fixed shape, with
  "doing" and "seen before" filled.
- The unit's ideal path and actual path stand side by side, with minutes per stage.
- Every kind has a reading at every stage, zero readings included, each with its evidence.
- Every kind carries its recurrence count over the units delivered.
- A fresh judge returned its expected recurrences, and they are in the table.
- The top tax is traced to a named construct with a why-chain that ends on the workflow.
- One change is committed and loaded, with its yardstick, or the gate's reason it was not.
- The previous change is graded on this unit, with every kind before and after.
