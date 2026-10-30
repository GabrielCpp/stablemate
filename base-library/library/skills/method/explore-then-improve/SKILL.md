---
name: explore-then-improve
description: "Making a process faster, cheaper or better by solving its problems one at a time until the operator's question is answered or its budget is spent: a budget in money and hours written before the first probe, a frozen yardstick, a profile that ranks where the cost or the failure sits, one problem at a time taken to its cause, the smallest fix at that cause, a reading through the cheapest instrument that resolves it, a release rule that drops a fix once its share of the budget is gone, a self-check that puts the loop's own spending to the operator, a plain-words TRIED.md and a ledger that keeps every failure with its spend. A wide search over framings and candidates is a disclosed branch for a profile with no dominant problem. Load when told to find a way to make something faster, cheaper or better, when handed a goal or research question to pursue without the operator, when a measurement comes back and the next step is unclear, or when hours went to apparatus."
argument-hint: "[the question, or the purpose: what must improve, by how much, over what workload]"
tags: [research, process]
---

# Explore, then improve

The loop's job is to move one number the operator cares about, by solving the problems
that hold it where it is. A **problem** is one place in the profile where the cost or the
failure sits. The loop profiles, takes the largest problem the budget can read, finds its
cause, fixes it at the cause with the smallest change, reads the effect through the cheapest
instrument, and takes the next problem. The output is `TRIED.md`, one plain line per problem
solved or released, and a **ledger** that keeps every reading with its spend.

The operator hands over a question, not a method. The loop runs alone: when a fix holds or
dies, the next problem starts without asking, inside the budget that remains. The loop
releases fixes and never the question. A released fix is one row in the ledger, and the
question closes only on the operator's word or on the stop conditions of step 11.

Nine traps turn the loop into one idea pursued for days, or into days with no result:

- **The first idea wins.** One plausible fix absorbs the session before the profile has
  said where the cost sits.
- **The fix sits at the symptom.** A retry, a cap, a skip or a cheaper model makes a cost
  smaller without asking why the work exists, and the cost comes back in the next unit.
- **The instrument is the whole system.** A change to one stage is read by running every
  stage, so each reading costs a whole run and the loop affords five readings a day.
- **The yardstick moves.** Each probe runs on different inputs, so no two results compare.
- **The method eats the time.** Framings, cards and checker rounds multiply, each correct
  by its own rule, and no problem is solved.
- **A number is recorded and never judged.** A result that projects to three weeks against
  an eight-hour purpose gets logged, and the next step starts.
- **Patience replaces judgement.** The agent waits out any run and tries any approach once
  more, because nothing in its own view runs out. The operator's money and quota do.
- **The loop never looks up.** Every choice follows the loop's own rules, each one correct,
  and the operator learns what the money bought after it is gone.
- **A stopped probe closes the question.** The operator stops one round, the loop reads it
  as a no to the whole question, and the work dies with the probe.

You do not perceive wall-clock time. A 15-minute command and a 1-minute command reach you
as one result each. The ledger's timestamps are how you see time. Read them. You do not
perceive money either. Every probe, every agent you brief and every turn you spend
attending draws on the operator's budget, and the ledger's `usd` field is how you see it.

## Value before procedure

Every step below serves the done-condition in `QUESTION.md`. A step done to the letter
that leaves the done-condition where it was has produced nothing.

Before a step, a probe or an agent, write one sentence: which problem it removes, and what
the yardstick reads if it works. When that sentence cannot be written, the action is
apparatus, and it waits for a step that needs it. The loop's own paperwork is held to the
same sentence. A reading that exists today is cited, never argued about.

Reread `QUESTION.md` at every reflection and after every result. Then say in one sentence
what the operator would have in hand if the loop stopped now. That sentence, not the count
of steps finished, is the loop's progress.

## Ask what you are doing

The loop decides the mechanics alone. It does not decide alone what the operator's money
buys. Before a step spends, and at every reflection, answer in writing:

- What am I doing, in one line a reader outside the project follows?
- Which problem does it solve, and which line of `QUESTION.md` says that problem matters?
- Who asked for it: a line of `QUESTION.md`, quoted, or the loop? What the loop added is a
  proposal until the operator takes it.
- What does it cost, and what share of the budget left?
- What has the spend so far bought, in one sentence of result?
- Is the loop still the cheapest reader of the question, or does the ledger answer it?

An answer the loop cannot give is a question to the operator, sent with a recommendation
and the ledger's one-sentence verdict, before the step runs. These decisions are the
operator's: the budget and its date, spending on once either is gone, a step priced above
a tenth of the budget left, a redesign of the yardstick, and a reading of the question that
drops or adds a premise. The loop proposes each with a figure and waits. A question about
money offers, beside stopping, the next reading at its price, and recommends the cheapest
one that moves the answer. The operator's answer stops what it names: a probe, a round or
an instrument. The loop then releases the fix that probe served, takes the next problem at
a cheaper rung, and holds the question open until the operator closes it in words.
Unattended, with no channel to the operator, it takes the cheaper branch, records the
proposal in `QUESTION.md`, and the report lists every decision taken this way.

## 1. Open the working directory

The loop keeps its state in `.study/<question-slug>/` at the root of the repository it
runs in. Add `/.study/` to `.git/info/exclude` when it is missing, so the directory stays
out of git without a change to a tracked file.

```
.study/<question-slug>/
  QUESTION.md    the question, its premises, its done-condition and its budget, in the operator's words
  PROBLEMS.md    the profile's items ranked by share, each with its reach, its cause and its status
  TRIED.md       one line per fix: what it was, whether it held, why
  ledger.jsonl   every step, in the format of references/ledger.md
  reports/       one report per finished study, in the format of references/report.md
  logs/          background job logs
```

When the directory already exists, the loop is resuming. Read `QUESTION.md`, `TRIED.md`,
`PROBLEMS.md` and the ledger's last rows, then continue from the open row or the problem
marked in hand. Every session and every wake-up starts here.

The directory is the loop's memory, not its publication. When the project keeps its own
committed record, copy findings into it by the project's rules. Keep transcripts, secrets
and large artifacts in the directory only.

Done when the directory exists, is excluded from git, and holds `QUESTION.md`.

## 2. Write the question, the purpose and the budget

Copy the operator's question into `QUESTION.md` word for word. Under it, copy every
premise, suggestion and constraint the operator gave anywhere in the conversation, also
word for word, each with where it came from. Take them from the record, not from memory,
including the arguments of a command such as a `/loop` prompt. A suggestion the operator
made in passing is a premise until the operator drops it.

Under the premises, write the **done-condition**: what a reader would have to see to agree
the question is answered. Take it from the project's own completion criteria when they
exist. Then write the **purpose** in one sentence: what must improve, the target, and the
full workload it applies to. "1,000 pages in 8 hours" is a purpose, and it gives the
per-unit bar: 28 seconds a page. Every later projection is held against this sentence.

Test the number before any result exists: could a method meet it without answering the
question? When one could, the number is a proxy. Change it now, while it costs nothing.
When the purpose is a margin over a control, state the target as a share of the control's
shortfall, with the reference it is measured to and a **resolution floor**, under "A
purpose stated as a share" in [references/measurement.md](references/measurement.md).

Then write the **budget**: the money and the wall hours the whole loop may spend, every
probe, every briefed agent and the attending turns counted. The operator's figure wins when
there is one. Without one, the loop proposes a share of what the answer is worth, never
more than a tenth of the saving the purpose promises over the horizon the operator named.
The proposal states what the loop spent before it and what that spend bought, and the
operator takes it before the first row spends against it. When the spend so far already
exceeds what the loop would propose, the proposal says so and asks for the next tranche:
how much more, priced as the readings it buys, and never whether. A budget that would not
buy three readings of the cheapest instrument calls for a cheaper instrument, found in step
8, or for a question to the operator before anything runs. The ledger spends the budget
down row by row, and the loop never extends it. At half of it with no fix held, a
reflection fires. At all of it, the study ends banked or negative and the loop stops. Add a
date, which works the same way, priced at the load the machine has shown, under "A plan at
the measured load" in [references/timing.md](references/timing.md).

Done when `QUESTION.md` holds the question, its premises, its done-condition, a purpose
with a target, a workload and a resolution floor if it is a share, a budget in money and
hours, and a date.

## 3. Freeze the yardstick

Pick the benchmark: a small fixed set of inputs that covers the kinds the workload holds.
Run the current system on it and record the baseline row. Pin what defines the yardstick:
the input set, the commit, the seeds, and the judge or scorer. The judge scores on cases
the system under test never saw. The judge, the bar and the controls stay frozen for the
whole study. A change to any of them is its own ledger row that quotes the old wording
beside the new, signed by the operator before it counts, under "A change to the yardstick"
in [references/measurement.md](references/measurement.md). That file also holds the rule
for a generated benchmark, a method that learns, a repeated unit and the two controls. Read
the section whose case applies.

Done when the baseline row is in the ledger with the commit and input set it ran on.

## 4. Profile

Break the baseline cost down by stage, by turn, by test, by call or by failure kind. Take
the breakdown from what the system records, or add the recording first. A total says
something is slow. A breakdown says one fixture runs 400 times, or one turn reads the whole
corpus. The problems come from the breakdown, never from a hunch about the system.

Every timed reading stores the script that took it, the script's hash, and the machine's
load at its start and end. On a machine another process shares, take repeated short
readings and record the lowest, the median and the highest, by the rules in
[references/timing.md](references/timing.md). Measure here every rate that decides whether
a reading can resolve the floor.

For each item, write its **reach**: what the purpose would read if the item went to zero.
An item whose vanishing moves the purpose less than the resolution floor is not a problem,
whatever its share. Compute the roof of each large item too: the fastest the hardware or
the task allows for the work it does. An item near its roof needs less work, not more
tuning, and its problem is the work's existence.

Write the items into `PROBLEMS.md`, ranked by reach, each with its share of the total, its
reach, and the rows that measured them.

Done when the top items are named with their share and their reach, and the top one alone
could move the purpose past the floor.

## 5. Take one problem

Take the top of `PROBLEMS.md` whose reach clears the floor and whose cheapest instrument
fits the budget left. Mark it in hand. One problem is in hand at a time: a second one waits,
and a fix that would touch two problems at once is two fixes measured apart.

Set its **cap** at registration: the problem's reach as a share of the purpose's total
shortfall, times the budget left. The cap is what the loop may spend on this problem,
cause-finding included, before it releases it.

Done when `PROBLEMS.md` marks one problem in hand with its cap in money and hours.

## 6. Find its cause

A problem's cause is a decision in the system: a line of a prompt, a loop bound, a default,
a retry, a step that runs when nothing needs its output, an input larger than the step
reads, a check that fails for a reason nobody looks at. A stage name is where the cost sits,
not why. The fix goes at the why.

Load [[isolating-causes]]. Show the cost on demand through the cheapest rung of step 8,
contrast the units that pay it with the units that do not, and change one variable at a
time until one cause is confirmed. The traces of runs already paid for answer most of this
at no cost: read them before running anything.

Then ask of the cost itself: what work does it buy, who asked for that work, and what fails
when the work is not done? Ask why of each answer until the answer is a property of the
task or a construct the loop can change. A cost whose work nobody asked for has a one-line
fix. A cost whose work the task needs has a fix in how the work is done, and the chain says
which part of how.

Done when the cause is named as a construct the loop can edit, and one sentence predicts
what the yardstick reads once it changes.

## 7. Fix at the cause

Write the smallest change that removes the cause. Removing work beats making it cheaper,
and making it cheaper beats making it faster. One variable per fix, on the frozen
yardstick.

Before adding a retry, a cap, a sleep, a skip, a default, a fallback or a smaller model,
load [[root-cause]] and write the why-chain. A fix that handles the symptom is taken only
with that chain written into its row, and its `TRIED.md` line says it is a symptom fix,
so the next reader knows the cause still stands.

Register the fix as a ledger row before it runs: the problem it removes, the cause, the
prediction from step 6, the estimate in minutes and money from the instrument's price, and
the cap from step 5. A fix whose row cannot quote a clause of the done-condition it bears
on is `exploration`, labelled so, and the label is a finding about its reach.

Done when the change exists on a commit and its row holds the prediction, the estimate and
the cap.

## 8. Read it through the cheapest instrument

The **instrument** is the smallest apparatus that reads the variable the fix changed, at
the resolution the floor needs. Freeze every input the variable's stage receives from
upstream, once, as a fixture, cut everything downstream the reading does not need, and
collapse down the ladder as far as the reading survives:

| Rung | Runs | Reads |
| --- | --- | --- |
| a trace | nothing: the record of a run already paid for | what happened, replayed under the change on paper |
| one turn | one prompt on a frozen context | what the turn does and spends |
| one stage | the stage on its frozen inputs | the stage's cost and output |
| whole system | every stage on a real unit | the purpose itself |

Each rung up costs about an order of magnitude more. Take the cheapest rung that still reads
the variable against the yardstick, and price it from one run: its cost per reading in
money and minutes. A reading the trace already holds is never bought again from a run. An
instrument that costs more than a tenth of the budget left says in the row why no lower
rung reads the variable. A fix proven on one stage is confirmed on the whole system once,
at the end, and not at every probe.

Before the expensive part runs, compute the best result the run could show from its inputs
alone. A ceiling under the bar kills the run before it costs anything. Run anything over a
few minutes as a background job with its log in `logs/`, and do cheap work while it runs. A
probe that passes twice its estimate is stopped, its row keeps the partial reading, and the
broken estimate is a finding about the instrument.

Done when the row holds the reading, the instrument's rung, and its price.

## 9. Judge the reading

Project the reading to the full workload and hold it against the purpose, in the row's
outcome: "30 min a page × 1,000 pages is 3 weeks against 8 hours: 60× off." Hold it against
the prediction too. The reading has one of three verdicts:

- **Held.** The reading moved at least the floor, in the direction predicted. Keep the
  change, write the `TRIED.md` line as worked, and go to step 10.
- **Missed.** The reading moved less than the floor, or the other way. The cause was wrong
  or incomplete, and the reading is new evidence. Go back to step 6 once, with the reading
  in the contrast. A second miss on the same problem releases it.
- **Released.** The cap is spent, or the kill result fired. Write the `TRIED.md` line with
  the reason, take the next problem, and never spend the released problem's past cost as an
  argument for one more probe on it.

Releasing is what the budget buys. Sitting out a run that is past its estimate, or trying
the released fix again with more of the same, is what patience buys.

A reading that decides the study's verdict is regraded by a second agent before it counts,
under "Checking a decisive result" in [references/second-agent.md](references/second-agent.md).
A reading that means the instrument cannot resolve the floor is the most valuable one a
study produces: stop that path before spending on it.

One ledger row per step, appended before the step starts and completed when it ends, with
its `kind` and its `usd`, in the format of [references/ledger.md](references/ledger.md). A
failed probe keeps its row with the reason. **`TRIED.md` is mandatory**: it is the
operator's view of the whole loop, one line per fix in plain words a reader outside the
project follows, changed before the next probe starts.

Done when the row carries its verdict and `TRIED.md` carries the line.

## 10. Next problem, and step back

After a fix held, the shares have changed. Re-profile at the cheapest rung that reads the
new breakdown, rewrite `PROBLEMS.md`, and take the next problem from step 5. Combine fixes
only after each has held alone, and measure the combination as its own row.

Write a `reflection` row when any of these fires:

- a probe passed twice its estimate,
- the budget is half spent with no fix held,
- a problem was released,
- two hours of wall time passed since the last reflection,
- `apparatus` holds more than half the time since the last reflection,
- three probes in a row moved nothing,
- a result met the purpose and left the done-condition unanswered.

A reflection starts by rereading `QUESTION.md`. It then answers in writing: what would the
operator have in hand if the loop stopped now, where did the time go, which problems are
solved and which stand, is the problem in hand still the one with the largest reach, does
the yardstick still measure the question, what did the loop do that no line of
`QUESTION.md` asked for, and would the operator fund the next step if shown the ledger.
Continuing is a decision the reflection argues for in numbers: the readings the budget
still buys, and which problem each one removes. A reflection whose answers touch the
budget, the date, the yardstick or the question goes to the operator as a question with a
recommendation before the next probe.

The loop holds standing authority to propose a redesign. When a reflection finds that a
benchmark, a bar, a judge or an instrument measures something other than the question,
design the replacement and put it to the operator in the same turn, as its own `reflection`
row. It applies only to probes that run after it and starts a new baseline. Earlier results
stay unchanged.

When the profile has no dominant problem, the top items are all near their roof, or two
reflections in a row found no problem whose reach clears the floor, the problem is the
shape of the system and not a stage of it. Load
[references/wide-search.md](references/wide-search.md), which maps framings of the
question and a field of candidate shapes, gates each on paper, and returns the survivor as
the next problem for step 5. Load [[step-back]] when the same kind of fix has failed three
times on one problem.

## 11. End a study, continue the loop

A study ends on one of three verdicts, and its report states it first:

- **reached**: the purpose is met on the yardstick.
- **banked**: a claim the study can defend that is not the purpose, stated with its gap
  to the purpose in numbers.
- **negative**: every problem whose reach clears the floor is released, and the wide search
  returned no candidate absent from `TRIED.md`. A negative verdict lists every assumption
  that could flip it. A verdict one undeclared assumption could flip is open, not negative.

Write the report from the ledger into `reports/`, in the format of
[references/report.md](references/report.md). Update `TRIED.md`. Then tell the operator in
a few lines: what held or died, what the number reads now against the purpose, and what
the loop takes next. A verdict that names what has to replace the current shape is a
design, and inside a [[self-improve]] cycle the build is that cycle's next step. "Needs
building" is not a verdict. Take the next problem from `PROBLEMS.md` and start the next
study at step 5, inside the budget left, only when that budget holds at least three
readings of the problem's instrument.

The loop stops only when:

- the done-condition in `QUESTION.md` is met, with a reached study as its evidence,
- the verdict is negative by the rule above,
- the budget or the date in `QUESTION.md` is spent, and the report prices what
  `PROBLEMS.md` still holds, so the operator can fund the next study or close the question.

When the host offers a self-paced loop, each wake-up reads the working directory as in
step 1 and continues. A wake-up with a background job still running does cheap work from
`PROBLEMS.md` or waits for the job.
