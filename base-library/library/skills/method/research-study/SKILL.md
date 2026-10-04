---
name: research-study
description: "Running a research or optimization loop alone until the operator's question is answered, and reporting what was tried, what worked and what did not: a working directory that holds the question and its done-condition, a mandatory TRIED.md in plain words, a frozen yardstick, a profile before any hypothesis, several framings of the question written in isolation, a field of original candidates, a paper gate that discards a candidate that answers another question or cannot succeed by construction, single-variable probes cheapest-decisive first, a ledger that keeps every failure, a projection of each result against the question, and a loop that starts the next study when one dies. Load when told to find a way to make something faster, cheaper or better, when handed a goal or research question to pursue without the operator, when a measurement comes back and the next step is unclear, or when the last hours went to making an experiment runnable rather than to results."
argument-hint: "[the question, or the purpose: what must improve, by how much, over what workload]"
tags: [research, process]
---

# Research study

A study searches a field of solutions and reports on the whole field. The output is a
**ledger**: every probe, what it cost, what it settled, and the failures in full. The best
result is one row in it.

The operator hands over a question, not a study. The skill runs as a **loop**: when one
study ends without answering the question, the next one starts from the field without
asking. The operator reads one file, `TRIED.md`, and hears from the loop only when a
method dies, a method wins, or the loop stops.

Eight traps turn a study into one idea pursued for days, or into days with no result:

- **The first idea wins.** One plausible fix absorbs the session, and the rest of the field
  is never compared against it.
- **The yardstick moves.** Each probe runs on different inputs, so no two results compare.
- **Apparatus eats the time.** Hours go to making an experiment runnable, and nothing asks
  whether the experiment still matters.
- **A number is recorded and never judged.** A result that projects to three weeks against
  an eight-hour purpose gets logged, and the next slice starts.
- **The number replaces the question.** A study meets its bar with a method that does not
  answer what the operator asked, and the win is recorded as progress.
- **Framings inbreed.** Each new framing grows out of the last one's parts, and every brief
  a study writes carries the briefer's reading of the question. Every candidate then shares
  one reading, and a failure of that reading passes for a failure of the question.
- **The framing decides the answer.** The study casts the problem so that no method can
  succeed, builds the method, measures the failure, and reports a "no" that was known on
  paper before anything ran.
- **The method eats the time.** Framings, cards and checker rounds multiply, each one
  correct by its own rule, and no probe runs.

You do not perceive wall-clock time. A 15-minute command and a 1-minute command reach you
as one result each. The ledger's timestamps are how you see time. Read them.

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

Take the premises from the record, not from memory. When the conversation's transcript is
on disk, extract every message the operator wrote and read each one. The operator also
writes as the arguments of a command, such as a `/loop` prompt or a skill's arguments. The
transcript wraps those in the command's own markup, so a filter on plain messages drops
them, and they often carry the setting. Memory keeps the premises that fit the reading
already formed and drops the ones that rule it out. Three kinds are the easiest to lose:

- **the end goal** behind the question, such as "cut what we pay the vendor",
  which fixes what the result is compared against,
- **a ruling** on an approach, such as "a fixed rule table is too rigid", which removes a
  whole reading before any agent proposes it,
- **the setting**, such as "this runs on real customer data", which rules out a
  testbed that only works because it is small.

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

Add a date. After it, an unmet purpose ends the study as banked or negative, and the loop
takes the next candidate. The date is never extended.

A plan meets its date and its budget at the load the machine has shown during the study,
never at idle. The rule is under "A plan at the measured load" in
[references/timing.md](references/timing.md). Read it before pricing a plan on a machine
another process shares.

Done when `QUESTION.md` holds the question and its done-condition, and the study's
sentence carries a target, its reference, a resolution floor if it is a share, a workload
size and a date.

## 3. Freeze the yardstick

Pick the benchmark: a small fixed set of inputs that covers the kinds the workload holds.
Run the current system on it and record the baseline row. Pin what defines the yardstick:
the input set, the commit, the seeds, and the judge or scorer. The judge stays frozen for
the whole study. The cheapest way to look faster is to make the judge pass sooner, so a
change to the judge is its own probe, reported as one.

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

Have the framings and the cards checked. A second agent that did not write them reads the
question, the premises, the framings and the cards, and nothing of the study's reasoning.
It answers both gates for each, names any assumption that makes the question unsolvable,
and names any two framings that share their input, output and role. A card or a framing it
fails goes back to repair. The rules for its counts, and for a rule that would return
every row, are under "The checker" in
[references/paper-gates.md](references/paper-gates.md).

A checker finding against a gate stays open until a repair answers it in writing or the
framing dies. No decisive run launches under a framing that carries an open gate finding.
A run that would read the same fact the finding states is apparatus for a known answer.

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

**Check for leaks before a decisive run.** List every route by which the answer could
reach the measured path without the method, and test each with a script over the generated
inputs. Then remove the method's learned part and confirm the result falls to the control.
"The consumer's ceiling" and "Leaks" in
[references/measurement.md](references/measurement.md) hold both rules in full. Read them
before the first decisive run.

**Order by cost before launching anything.** List the next decisive checks with their
estimates, and run the cheapest first. A long job in the background is not free: a
three-minute check can make its answer moot, and then the long job is apparatus for
nothing.

Change one variable per probe, on the frozen yardstick. Before each probe, write two
things into its ledger row:

- **What it settles.** "This changes the answer by ⟨how⟩, and a result of ⟨X⟩ settles
  ⟨claim⟩." A probe that settles nothing is `exploration`, labelled so.
- **The estimate.** Wall minutes, from the profile or a timed single unit.

Run anything over a few minutes as a background job with its log in `logs/`, and do cheap
work while it runs. Combine winners only after each has won alone, and measure the
combination as its own probe.

## 8. Record, including the failures

One ledger row per step, appended before the step starts and completed when it ends. The
command that appends the row takes the start time from `date -Iseconds`, so the row exists
before the work does. A row written after the step began says its start is reconstructed.
Each row carries its `kind`:

| kind | what it is |
| --- | --- |
| `decisive` | its result settles a claim about the purpose |
| `exploration` | it informs the field without settling anything |
| `apparatus` | it makes a decisive step runnable, and names that step |
| `reflection` | a step back, written by the triggers in step 10 |

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

**Have a decisive result checked before it counts.** A second agent that did not write the
probe reads the row's `settles` sentence, the command and the bar, and nothing of the
study's reasoning. It re-runs the scorer on the recorded outputs, holds its number against
the bar, and repeats the leak check. Its number goes into the row's `checked` field. When
the two numbers differ, the row records both and the result stays open until explained.

## 10. Step back

Write a `reflection` row when any of these fires:

- a step ran more than 3× its estimate,
- two hours of wall time passed since the last reflection,
- `apparatus` holds more than half the time since the last reflection, with the paper
  work of steps 5 and 6 counted as apparatus,
- a second checker round on the same cards ended with no probe run since the first,
- three probes in a row moved nothing,
- a result met the study's number and left the question unanswered.

A reflection starts by rereading `QUESTION.md`. It then answers six questions: what would
the operator have in hand if the loop stopped now, where did the time go, what has been
settled, is the current path still the cheapest route to the done-condition, does the
yardstick still measure the question, and does the framing in `QUESTION.md` still pass
both paper gates. If a cheaper route exists, name it and take it. Continuing is a decision
the reflection has to argue for.

When the paper work holds the time and no probe has run, the cheaper route is a probe.
Take the surviving candidate with the cheapest kill result and run it. Its reading
replaces the argument the cards were having.

**The loop holds standing authority to redesign.** When a reflection finds that a
benchmark, a bar, a judge or an instrument measures something other than the question,
redesign it without waiting for the operator. The redesign is its own `reflection` row,
stating what the old yardstick measured and what the new one measures. It applies only to
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
a few lines: what died or won, and what the loop takes next. Take the next candidate from
`FIELD.md` and start the next study at step 2. When the study died of its framing, update
`FRAMINGS.md` first, and take the next candidate from another framing. The next study does
not start from a neighbour of the framing that just failed.

The loop stops only when:

- the done-condition in `QUESTION.md` is met, with a reached study as its evidence,
- the field is exhausted and a refill under step 5 produced no candidate absent from
  `TRIED.md`, which answers the question in the negative,
- the next step would spend money beyond a budget the operator agreed.

When the host offers a self-paced loop, each wake-up reads the working directory as in
step 1 and continues. A wake-up with a background job still running does cheap work from
the field or waits for the job.
