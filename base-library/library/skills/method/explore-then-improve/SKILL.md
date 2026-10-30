---
name: explore-then-improve
description: "Running a research or optimization loop alone until the operator's question is answered or its budget is spent, and reporting what was tried, what worked and what did not: a budget in money and hours written before the first probe, a mandatory TRIED.md in plain words, a frozen yardstick, a profile before any hypothesis, an instrument collapsed to the smallest stage that reads the variable, isolated framings, a field of original candidates, a paper gate that discards a candidate that answers another question or cannot succeed by construction, single-variable probes, a release rule that drops an approach once its share of the budget is gone, a self-check that puts the loop's own spending decisions to the operator, and a ledger that keeps every failure with its spend. Load when told to find a way to make something faster, cheaper or better, when handed a goal or research question to pursue without the operator, when a measurement comes back and the next step is unclear, or when hours went to apparatus."
argument-hint: "[the question, or the purpose: what must improve, by how much, over what workload]"
tags: [research, process]
---

# Research study

A study searches a field of solutions and reports on the whole field. The output is a
**ledger**: every probe, what it cost, what it settled, and the failures in full. The best
result is one row in it.

The operator hands over a question, not a study. The skill runs as a **loop**: when one
study ends without answering the question, the next one starts from the field without
asking, inside the budget that remains. The operator reads one file, `TRIED.md`, and hears
from the loop when a method dies, a method wins, the loop stops, or a decision is the
operator's to take. The loop releases approaches and never the question: a released
candidate is one row in the ledger, and the question closes only on the operator's word or
on the stop conditions of step 11.

Twelve traps turn a study into one idea pursued for days, or into days with no result:

- **The first idea wins.** One plausible fix absorbs the session, and the rest of the field
  is never compared against it.
- **The yardstick moves.** Each probe runs on different inputs, so no two results compare.
- **Apparatus eats the time.** Hours go to making an experiment runnable, and nothing asks
  whether the experiment still matters.
- **A number is recorded and never judged.** A result that projects to three weeks against
  an eight-hour purpose gets logged, and the next slice starts.
- **The number replaces the question.** A study meets its bar with a method that does not
  answer what the operator asked, and the win is recorded as progress. The commonest route
  is a registration that restates the bar with a clause missing and a sentence saying the
  loss favours the reference.
- **Framings inbreed.** Each new framing grows out of the last one's parts, and every brief
  a study writes carries the briefer's reading of the question. Every candidate then shares
  one reading, and a failure of that reading passes for a failure of the question.
- **The framing decides the answer.** The study casts the problem so that no method can
  succeed, builds the method, measures the failure, and reports a "no" that was known on
  paper before anything ran.
- **The method eats the time.** Framings, cards and checker rounds multiply, each one
  correct by its own rule, and no probe runs.
- **The instrument is the whole system.** A change to one stage is read by running every
  stage, so each reading costs a whole run, and the study affords five readings a day.
- **Patience replaces judgement.** The agent waits out any run and tries any approach once
  more, because nothing in its own view runs out. The operator's money and quota do.
- **The loop never looks up.** Every choice follows the loop's own rules, each one correct,
  and the operator learns what the money bought after it is gone.
- **A stopped probe closes the question.** The operator stops one round, the loop reads it
  as a no to the whole question, and the field dies with the probe.

You do not perceive wall-clock time. A 15-minute command and a 1-minute command reach you
as one result each. The ledger's timestamps are how you see time. Read them. You do not
perceive money either. Every probe, every agent you brief and every turn you spend
attending draws on the operator's budget, and the ledger's `usd` field is how you see it.

## The question is the work

Every step below serves the done-condition in `QUESTION.md`. The steps are how the loop
avoids the traps, and none of them is the goal. A step done to the letter that leaves the
done-condition where it was has produced nothing.

Before starting a step, a probe or an agent, write one sentence: what it changes about the
answer to the question. When that sentence cannot be written, the action is apparatus, and
it waits for a decisive step that needs it.

The skill's own paperwork is held to the same sentence. Framings, cards and checker rounds
answer nothing by themselves. They earn their time by killing a candidate more cheaply
than a run would. When a short run on things that exist today would read the fact a card
is arguing about, run it and cite the reading.

Reread `QUESTION.md` at every reflection and after every result. Then say in one sentence
what the operator would have in hand if the loop stopped now. That sentence, not the count
of steps finished, is the loop's progress.

## Ask what you are doing

The loop decides the mechanics alone. It does not decide alone what the operator's money
buys. Before a step spends, and at every reflection, answer in writing:

- What am I doing, in one line a reader outside the project follows?
- Who asked for it: a line of `QUESTION.md`, quoted, or the loop? What the loop added is a
  proposal until the operator takes it.
- What does it cost, and what share of the budget left?
- What has the spend so far bought, in one sentence of result?
- Would the operator fund this step if shown the ledger now?
- Is the loop still the cheapest reader of the question, or does the ledger answer it?

An answer the loop cannot give is a question to the operator, sent with a recommendation
and the ledger's one-sentence verdict, before the step runs. These decisions are the
operator's: the budget and its date, spending on once either is gone, a step priced above
a tenth of the budget left, a redesign of the yardstick, and a reading of the question that
drops or adds a premise. The loop proposes each with a figure and waits. A question about
money offers, beside stopping, the next reading from the field at its price, and recommends
the cheapest one that moves the answer. The operator's answer stops what it names: a probe,
a round or an instrument. The loop then releases the candidate that probe served, takes the
next one at a cheaper rung, and holds the question open until the operator closes it in
words. Unattended, with
no channel to the operator, it takes the cheaper branch, records the proposal in
`QUESTION.md`, and the report lists every decision taken this way.

## 1. Open the working directory

The loop keeps its state in `.study/<question-slug>/` at the root of the repository it
runs in. Add `/.study/` to `.git/info/exclude` when it is missing, so the directory stays
out of git without a change to a tracked file.

```
.study/<question-slug>/
  QUESTION.md    the question and its done-condition, in the operator's words
  TRIED.md       one line per method or route: what it was, whether it worked, why
  FRAMINGS.md    each reading of the question, in plain words, with its status
  FIELD.md       the standing field of candidates, ordered, each with its framing and kill result
  ledger.jsonl   every step, in the format of references/ledger.md
  reports/       one report per finished study, in the format of references/report.md
  logs/          background job logs
```

When the directory already exists, the loop is resuming. Read `QUESTION.md`, `TRIED.md`,
`FIELD.md` and the ledger's last rows, then continue from the open row or the top of the
field. Every session and every wake-up starts here.

The directory is the loop's memory, not its publication. When the project keeps its own
committed record, copy findings into it by the project's rules. Keep transcripts, secrets
and large artifacts in the directory only.

Done when the directory exists, is excluded from git, and holds `QUESTION.md`.

## 2. Write the question, then the purpose

Copy the operator's question into `QUESTION.md` word for word. Under it, copy every
premise, suggestion and constraint the operator gave anywhere in the conversation, also
word for word, each with where it came from. A suggestion the operator made in passing is
a premise until the operator drops it. A study that reads the question and not its
premises answers a narrower question than the one asked.

Take the premises from the record, not from memory, and read every message the operator
wrote, including the arguments of a command such as a `/loop` prompt. The three kinds
easiest to lose are under "Where the premises come from" in
[references/framings.md](references/framings.md).

Under the premises, write the **done-condition**: what a reader would have to see to agree
the question is answered. Take it from the project's own completion criteria when they
exist. This is the only purpose the loop has. Every study serves it.

A study's purpose is a number that reads the done-condition. Write one sentence: what must
improve, the target, and the full workload it applies to. "1,000 pages in 8 hours" is a
purpose. It also gives the per-unit bar: 28 seconds a page. Every later projection is held
against this sentence.

Test the number before any result exists: could a method meet it without answering the
question? A benchmark whose gap is vocabulary rewards a lexicon. A benchmark whose answer
is printed in the prompt rewards arithmetic. When a method could win that way, the number
is a proxy. Change the number now, while it costs nothing.

When the purpose is a margin over a control, state the target as a share of the control's
shortfall, with the reference it is measured to and a **resolution floor**.
[references/measurement.md](references/measurement.md) holds the rule under "A purpose
stated as a share". Read it before writing a purpose that compares against a control.

Then write the **budget**: the money and the wall hours the whole loop may spend, every
probe, every briefed agent and the attending turns counted. The operator's figure wins when
there is one. Without one, the loop proposes a share of what the answer is worth: the saving
the purpose promises over the horizon the operator named, and never more than a tenth of it.
The proposal states what the loop spent before it, in money and hours, and what that spend
bought, and the operator takes it before the first row spends against it. When the spend so
far already exceeds what the loop would propose, the proposal says so and asks for the next
tranche: how much more, priced as the readings it buys, and never whether. Closing the
question is the operator's call, and the loop's recommendation is the cheapest reading that
moves the answer. A budget that would not buy
three readings of the cheapest decisive probe calls for a cheaper instrument, found in step
4b, or for a question to the operator before anything runs. The ledger spends the budget
down row by row, and the loop never extends it. At half of it with no verdict, a reflection
fires. At all of it, the study ends banked or negative and the loop stops. Add a date, which
works the same way.

A plan meets its date and its budget at the load the machine has shown during the study,
never at idle. The rule is under "A plan at the measured load" in
[references/timing.md](references/timing.md). Read it before pricing a plan on a machine
another process shares.

Done when `QUESTION.md` holds the question and its done-condition, and the study's
sentence carries a target, its reference, a resolution floor if it is a share, a workload
size, a budget in money and hours, and a date.

## 3. Freeze the yardstick

Pick the benchmark: a small fixed set of inputs that covers the kinds the workload holds.
Run the current system on it and record the baseline row. Pin what defines the yardstick:
the input set, the commit, the seeds, and the judge or scorer. The judge scores on cases
the system under test never saw: a judge that checks only the examples the prompt shows
credits a copy of them. The judge, the bar and both controls stay frozen for the whole
study. A change to any of them is its own ledger row that quotes the old wording beside the
new, signed by the operator or a checker before it counts. The rule is under "A change
to the yardstick" in [references/measurement.md](references/measurement.md).

Four cases add a rule, and [references/measurement.md](references/measurement.md) holds
each under its own heading. Read the section when its case applies: the benchmark is
generated, the purpose is a share of a control's shortfall, the method learns, or an
apparatus change must reproduce an earlier output.

Done when the baseline row is in the ledger with the commit and input set it ran on.

## 4. Profile before any hypothesis

Break the baseline cost down by stage, by turn, by test, or by call. Take the breakdown
from what the system records, or add the recording first. A total says something is slow.
A breakdown says one fixture runs 400 times, or one turn reads the whole corpus. The
hypotheses come from the breakdown.

Every timed reading stores the script that took it, the script's hash, and the machine's
load at its start and end. A reading without them is void, and this step retakes it. On a
machine another process shares, one reading is not a rate. Take repeated short readings
across a window and record the lowest, the median and the highest.
[references/timing.md](references/timing.md) holds the rules for both. Read it before the
first timed reading on a machine another process shares.

Before tuning a stage, compute its roof: the fastest the hardware allows for the work it
does. Model decode on a CPU streams every weight once per token, so its roof is memory
bandwidth divided by weight bytes, however many threads run. A stage already near its roof
needs less work, not more tuning.

Measure here every rate that decides whether a verdict can be read, when one timed unit on
the machine at hand reads it in minutes. Framings cite the measure. "Deciding rates" in
[references/timing.md](references/timing.md) lists the rates and what each record holds.

Done when the top cost items are named with their share of the total.

## 4b. Collapse the instrument

A probe changes one variable, and the variable lives in one place: one stage, one turn, one
prompt, one call. The **instrument** is the smallest apparatus that reads the variable at
the resolution the purpose needs. Run the whole system only when the variable is the whole
system.

Build the instrument by isolating. Freeze every input the variable's stage receives from
upstream, once, as a fixture, and cut everything downstream that the reading does not need.
Then collapse down the ladder as far as the reading survives:

| Rung | Runs | Reads |
| --- | --- | --- |
| whole system | every stage on a real unit | the purpose itself |
| one stage | the stage on its frozen inputs | the stage's cost and output |
| one turn | one prompt on a frozen context | what the turn does and spends |
| a trace | nothing: the record of a run already paid for | what happened, replayed under the change on paper |

Each rung down costs about an order of magnitude less and loses something the purpose may
need. Take the cheapest rung that still reads the variable against the yardstick. A reading
the trace already holds is never bought again from a run. A change proven on one stage is
confirmed on the whole system once, at the end, and not at every probe.

Price the instrument before any probe runs: its cost per reading in money and minutes, read
from one run of it. That price, times the readings the field needs, is held against the
budget. When it does not fit, collapse further or shrink the field. A probe whose instrument
costs more than a tenth of the budget says in its registration why no lower rung reads the
variable.

Done when the instrument for the top cost item is named with its rung, its price per
reading, and the fixture that freezes its inputs.

## 5. Frame the question, then map the field

### Framings first

A **framing** is a reading of the question. It says what the thing under study does, on
which input, to produce which output, judged how, and what the question's key verb means,
such as "use", "replace" or "speed up". It names no mechanism, no architecture and no
file. Those belong to candidates, and a candidate always sits under one framing.
A framing that learns also names whose work supplies its training data.

Write at least three framings. Agents that share a model and read the same documents
converge on one reading, and isolation alone does not make framings differ. Framings differ
when each is built from its own choice on every open axis.

Build the framings in four moves. [references/framings.md](references/framings.md) holds
the full rules for each move and for the brief every framing agent receives. Read it before
briefing the first framing agent, and again before judging a row an agent returns.

1. **Restate the question by analogy.** At least three agents each restate the question
   in the terms of one distant field. Each reads the question and the premises, and no
   other restatement. Each returns the parts its field cuts the problem into, and the axes
   the literal reading lacks.
2. **List the axes.** One agent lists the axes a reading must choose on. It marks each
   **fixed**, with the operator's words that fix it, or **open**, with at least three
   values. A value says what, never how.
3. **Draw the rows.** Pick one value per open axis for each framing, so that any two
   framings differ on at least half of the open axes. No row is the "direct" reading.
4. **Write each row in isolation.** A fresh agent gets the question, the premises word
   for word, pointers into the project and its row. It reads nothing the study has
   produced. A row agent never repairs its own row. A value that fails a gate goes back
   to the axis agent, which corrects it for every row.

Then compare the framings pair by pair, on the values each framing holds as written and
not on the row it was assigned, and list the assumptions each pair shares. Two
framings that share their input, their output and the role they give the thing under study
are one framing. Merge them and generate another. Put each surviving framing through
step 6's two gates at the framing level before any candidate is mapped under it.

Write the framings into `FRAMINGS.md` in plain words a reader outside the project follows.
The file records meaning, not implementation: what each reading takes the question to ask,
what it assumes, and its status. A framing's status changes only on a framing-level
reason. A candidate that dies kills the candidate. A framing dies when it fails a paper
gate, or when its candidates die of an assumption the framing holds and no mechanism
could change.

### Then the candidates

Read `TRIED.md` and `FIELD.md` first, then the project's own history of what was tried.
Then load [[brainstorm]] and generate before judging. Judging while generating settles on
the obvious candidate, because it arrives with a metric and a price already attached.

The field is built for originality. Each time it is mapped or refilled:

- give every surviving framing at least 3 candidates, so no framing is judged by one
  mechanism,
- generate at least 10 candidates that differ in **mechanism**, not in size, such as less
  input per step, fewer steps, a cheaper model per stage, different work order, skipping
  work a cheap check proves unneeded, parallelism, or a different instrument,
- make at least 3 of them absent from `TRIED.md` and from the project's history,
- borrow at least 2 from another discipline, and name the discipline and the technique,
- carry at least 1 candidate you expect to fail, with a sentence on why it might not.

A candidate that repeats a `TRIED.md` line with a bigger model, more data, more compute or
more retries is the baseline. A repeat says what changed since the line was written.

The field always holds two controls. The **no-method control** is the simplest mechanism
that uses none of the idea under test. Measure it early: when it matches the method, the
yardstick cannot credit the method. The **broken-link control** is the method's own output
attached to the wrong case. A method that ties it wins on what it adds, not on the link it
claims. "Controls" in [references/measurement.md](references/measurement.md) holds the
rules for building both. Read it before building either.

For each candidate write the expected gain, tied to a line of the profile, the cost to
test it, and the result that would kill it.

Write the field into `FIELD.md`, where it outlives the session. Order it by expected gain
over cost to test and start at the top. Do not wait for the operator.

Done when the field holds at least as many candidates as the profile has cost items, meets
the originality counts above, and gives each candidate its kill result.

## 6. Reason on paper before building

A candidate reaches a build only after it survives on paper. The paper phase reads the
question, the field and the repository, and nothing runs. A build that measures a failure
the paper predicted says nothing about the question.

For each candidate that is about to be probed, write a **card** into `FIELD.md` before any
code, data or model call. The card holds:

- the question's task, copied from the operator's words,
- the method's task, under test and in use,
- the training task, when the method learns,
- the judge,
- every assumption, marked as stated by the operator, checked, or assumed,
- which inputs are fixed and which are designed,
- the named method's defining parts, each marked built or left out.

"The card" in [references/paper-gates.md](references/paper-gates.md) says what each line
states. Read it before writing the first card.

### Gate 1: does it answer the question as posed?

Hold the method's task against the question's task, part by part.

- **The input matches.** A method that swaps the question's input for a proxy answers
  another question. A method that copies the nearest solved case does not derive the
  answer from the specification the question names. A chooser that never reads that
  specification is not a method for it.
- **The output matches.** A method that produces a slice of the output answers the
  question only when the question allows a slice and the rest has a named author.
- **The role matches.** A question that asks how to use a component is not answered
  by casting that component as a replacement for the whole system. A component the method
  only consults authors no part of the output.
- **Every premise holds.** A premise the operator stated and the method dropped makes a
  different question.
- **The input exists in use.** Trace one request from the operator's hands to the method's
  input, as it would run after the study ends, and name the producer of every designed
  input there.

A candidate that fails gate 1 leaves the field with the mismatch as its reason. A rewrite
that makes the input, the output and the role match is a new candidate with its own card.

### Gate 2: can it succeed by construction?

Each check asks whether the method can succeed when everything uncertain goes its way. One
"no" means the build can only confirm a failure already known.

- **Identifiability.** For each part of the output the method decides, the card names the
  part of the input it comes from and its route in. A part with no source is guessed.
- **Train equals test.** The training task has the input and the output of the measured
  task.
- **The judge accepts every right answer.** A judge that credits one reference output
  fails a correct output that differs from it.
- **The judge rejects wrong answers.** Name a wrong output the judge would pass, starting
  with the unchanged state.
- **Method fidelity.** Every defining part of the named method is built, or the verdict
  names the gap.
- **The data fits the target.** The training data comes from the test's distribution, in
  kind and in volume, counted before building.
- **The compute fits the claim.** Price what the method needs to learn the task, in time
  and memory, on the hardware the run will use. This check alone never assumes the
  uncertain part goes the method's way.
- **The ceiling covers the workload.** Sample the operator's real work and table the cases
  the framing could serve.
- **The operator's levers are used.** The card says how the method uses each lever the
  question names.

Each check of gate 2 has a section of the same name in
[references/paper-gates.md](references/paper-gates.md), and so do the role check and the
in-use check of gate 1. A section holds the cases where its check passes wrongly, such as
a leak through a test input, a judge that is a model call, or a ceiling stated without its
table. Read a check's section before writing its answer on a card, and before checking a
card someone else wrote.

A candidate that fails gate 2 is repaired on paper, with the failed check named in the
repair, or it leaves the field. Record it in `TRIED.md` as "did not work (on paper)" with
the failed check as its reason.

### Declare the framing each probe tests

Every card names its framing from `FRAMINGS.md`. Test each framing against the operator's
words, sentence by sentence, as its own claim: which component does what, on which input,
judged how. A framing that makes the question unanswerable yields a "no" about the
framing, and a "no" found under one framing is a "no" for that framing. The question is
answered in the negative only when every surviving framing has died, each for its own
reason.

Have the framings and the cards checked by a second agent that did not write them. A
finding it raises is a predicate it can run again, and it stays open until a repair
answers it in writing or the framing dies. No decisive run launches under a framing with
an open finding, and none launches without the design check of step 7. How the checker
is briefed and what it returns is under "Checking the cards and framings" in
[references/second-agent.md](references/second-agent.md).

Done when at least three framings survive in `FRAMINGS.md` or the rest died on paper,
every candidate about to be probed has a card that passed both gates in writing, and a
second agent agreed.

## 7. Probe

**Read the ceiling before running the instrument.** Most instruments have an expensive
part: a model call, a full rerun, a human judge. Compute the best result the run could
show from its inputs alone, with the expensive part assumed to go the candidate's way
wherever it is uncertain. A ceiling under the bar kills the run before it costs anything.

**Read the consumer's ceiling too.** When the method's output reaches the purpose through
another system, hand that system the perfect output before building the method's run. If
the oracle does not clear the bar, no method can.

**Register a decisive probe, have its design checked, then launch.** The registration row
quotes every clause of the done-condition the run bears on, word for word from
`QUESTION.md`, and gives each clause its anchors: the arm, the code line that enforces it,
and the ledger row that measured how the run meets it. A clause the run does not meet is a
`gap` line carrying the row that measured the gap's size. A sentence that compares the run
to the bar, a control or a budget and cites no row id is an invented argument: "the
difference favours the reference" and "that is what the question asks" are its usual
shapes. A script flags such a sentence and the registration fails until it becomes a gap
line or a cited row.

A second agent then writes a `design-check` row and designs a cheat arm, the cheapest
route to a passing score that uses none of the method. The decisive command refuses to
start until that row exists with no open finding. What the checker reads, what the cheat
must cover and what a script enforces instead is under "Checking a decisive
registration" in [references/second-agent.md](references/second-agent.md).

**Order by cost before launching anything.** List the next decisive checks with their
estimates, and run the cheapest first. A long job in the background is not free: a
three-minute check can make its answer moot, and then the long job is apparatus for
nothing.

Change one variable per probe, on the frozen yardstick, through the instrument of step 4b.
Before each probe, write two things into its ledger row:

- **What it settles.** "A result of ⟨X⟩ on ⟨clause, quoted⟩ settles ⟨claim⟩." A probe
  whose sentence quotes no clause is `exploration`, labelled so, and that label is a
  finding about the probe's reach, not a failure. The sentence never argues a gap away. A
  gap is a line under `gaps` or it is an open finding.
- **The estimate.** Wall minutes and money, from the instrument's price. A probe that
  passes twice its estimate is stopped, its row keeps the partial reading, and the broken
  estimate is a finding about the instrument.

Run anything over a few minutes as a background job with its log in `logs/`, and do cheap
work while it runs. Combine winners only after each has won alone, and measure the
combination as its own probe.

## 8. Record, including the failures

One ledger row per step, appended before the step starts and completed when it ends. The
command that appends the row takes the start time from `date -Iseconds`, so the row exists
before the work does. A row written after the step began says its start is reconstructed.
Each row carries its `kind`: `decisive`, `exploration`, `apparatus`, `design-check` or
`reflection`, defined in [references/ledger.md](references/ledger.md), and its `usd`, the
spend it drew from the budget, read from the host's usage record at its start and its end.

A failed probe keeps its row with the reason it failed. The row is the report. The row
format is in [references/ledger.md](references/ledger.md).

**`TRIED.md` is mandatory.** It is the operator's view of the whole loop, and it is kept
current. Add or change its line when a candidate dies, wins, is parked, or blocks, and do
it before the next probe starts. One line per method or route, newest first, in plain
words a reader outside the project follows. The line format is under "TRIED.md" in
[references/ledger.md](references/ledger.md).

## 9. Project every result against the question

When a number arrives, extrapolate it to the full workload and hold it against the
sentence from step 2. Write the projection into the row's outcome: "30 min a page × 1,000
pages is 3 weeks against 8 hours: 60× off." A path that projects 10× off the purpose is
dead as it stands. Say so in the row, then go back to the field for a candidate that
changes the order of magnitude.

Hold it against the done-condition too. A result that meets the study's number and leaves
the question unanswered is a finding about the number, and the next reflection redesigns
it.

A result that means the instrument cannot resolve the target is the most valuable reading
a study produces. "Every arm scores zero" says the full run can only compare zero with
zero. Stop that path before spending on it.

**Have a decisive result checked before it counts.** A second agent regrades the
retained replies and its number goes into the row's `checked` field. The rule is under
"Checking a decisive result" in
[references/second-agent.md](references/second-agent.md).

## 10. Step back

Write a `reflection` row when any of these fires:

- a probe passed twice its estimate,
- the budget is half spent with no verdict,
- a candidate's spend reached its cap, or two probes on it moved less than the resolution
  floor,
- two hours of wall time passed since the last reflection,
- `apparatus` holds more than half the time since the last reflection, with the paper
  work of steps 5 and 6 counted as apparatus,
- a second checker round on the same cards ended with no probe run since the first,
- three probes in a row moved nothing,
- a result met the study's number and left the question unanswered.

A reflection starts by rereading `QUESTION.md`. It then answers eight questions: what would
the operator have in hand if the loop stopped now, where did the time go, what has been
settled, is the current path still the cheapest route to the done-condition, does the
yardstick still measure the question, does the framing in `QUESTION.md` still pass both
paper gates, what did the loop do that no line of `QUESTION.md` asked for, and would the
operator fund the next step if shown the ledger. If a cheaper route exists, name it and
take it. Continuing on the current path is a decision the reflection argues for in numbers:
the readings the budget still buys, and what each one settles. A reflection whose answers
touch the budget, the date, the yardstick or the question goes to the operator as a
question with a recommendation before the next probe.

**Release before patience.** A candidate is released, and its `TRIED.md` line written, when
its kill result fires, when two probes on it moved less than the resolution floor, or when
its spend reaches its cap. The cap is set at registration: the candidate's expected gain as
a share of the field's total, times the budget left. The spend on a released candidate
never argues for one more probe on it. The next probe runs the next mechanism in the field,
from another framing. Releasing is what the budget buys. Sitting out a run that is past its
estimate, or trying the released idea again with more of the same, is what patience buys.

When the paper work holds the time and no probe has run, the cheaper route is a probe.
Take the surviving candidate with the cheapest kill result and run it. Its reading
replaces the argument the cards were having.

**The loop holds standing authority to propose a redesign.** When a reflection finds that
a benchmark, a bar, a judge or an instrument measures something other than the question,
design the replacement and put it to the operator in the same turn. The redesign is its own
`reflection` row, stating what the old yardstick measured and what the new one measures,
and it runs once the operator takes it, or at once when no channel exists. It applies only to
probes that run after it and starts a new baseline, so a result already read is never
re-scored under a friendlier judge. Earlier results stay in the ledger and in `TRIED.md`,
unchanged.

When two reflections in a row find no cheaper route, refill the field with step 5 instead
of stopping.

## 11. End a study, continue the loop

A study ends on one of three verdicts, and its report states it first:

- **reached**: the purpose is met on the yardstick.
- **banked**: a claim the study can defend that is not the purpose, stated with its gap
  to the purpose in numbers. Banking records a real result without moving the bar.
- **negative**: a kill result fired, or the study's candidates are exhausted. A negative
  verdict lists every assumption on the cards that could flip it. A verdict that one
  undeclared assumption could flip is not negative. It is open.

Write the study's report from the ledger into `reports/`. The format is in
[references/report.md](references/report.md). Update `TRIED.md`. Then tell the operator in
a few lines: what died or won, and what the loop takes next. A verdict that names what has to
replace the current shape is a design, and when the study runs inside a [[self-improve]]
cycle the build is that cycle's next step. "Needs building" is not a verdict. Take the next
candidate from `FIELD.md` and start the next study at step 2, inside the budget left, and
only when that budget holds at least three readings of the candidate's instrument. When the study died of its framing, update
`FRAMINGS.md` first, and take the next candidate from another framing. The next study does
not start from a neighbour of the framing that just failed.

The loop stops only when:

- the done-condition in `QUESTION.md` is met, with a reached study as its evidence,
- the field is exhausted and a refill under step 5 produced no candidate absent from
  `TRIED.md`, which answers the question in the negative,
- the budget or the date in `QUESTION.md` is spent, and the report prices what the field
  still holds, so the operator can fund the next study or close the question.

When the host offers a self-paced loop, each wake-up reads the working directory as in
step 1 and continues. A wake-up with a background job still running does cheap work from
the field or waits for the job.
