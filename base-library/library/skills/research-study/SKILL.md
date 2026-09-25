---
name: research-study
description: "Running a research or optimization loop alone until the operator's question is answered, and reporting what was tried, what worked and what did not: a gitignored working directory in the repo, the question's done-condition written before any number, a mandatory TRIED.md in plain words, a frozen yardstick, a profile before any hypothesis, a field of original candidates mapped before digging, single-variable probes cheapest-decisive first, a ledger that keeps every failure, a projection of each result against the question, standing authority to redesign an instrument that measures the wrong thing, and a loop that starts the next study when one dies. Load when told to find a way to make something faster, cheaper or better, when handed a goal or research question to pursue without the operator, when a measurement comes back and the next step is unclear, or when the last hours went to making an experiment runnable rather than to results."
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

Five traps turn a study into one idea pursued for days:

- **The first idea wins.** One plausible fix absorbs the session, and the rest of the field
  is never compared against it.
- **The yardstick moves.** Each probe runs on different inputs, so no two results compare.
- **Apparatus eats the time.** Hours go to making an experiment runnable, and nothing asks
  whether the experiment still matters.
- **A number is recorded and never judged.** A result that projects to three weeks against
  an eight-hour purpose gets logged, and the next slice starts.
- **The number replaces the question.** A study meets its bar with a method that does not
  answer what the operator asked, and the win is recorded as progress.

You do not perceive wall-clock time. A 15-minute command and a 1-minute command reach you
as one result each. The ledger's timestamps are how you see time. Read them.

## 1. Open the working directory

The loop keeps its state in `.study/<question-slug>/` at the root of the repository it
runs in. Add `/.study/` to `.git/info/exclude` when it is missing, so the directory stays
out of git without a change to a tracked file.

```
.study/<question-slug>/
  QUESTION.md    the question and its done-condition, in the operator's words
  TRIED.md       one line per method or route: what it was, whether it worked, why
  FIELD.md       the standing field of candidates, ordered, each with its kill result
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

Copy the operator's question into `QUESTION.md` word for word. Under it, write the
**done-condition**: what a reader would have to see to agree the question is answered.
Take it from the project's own completion criteria when they exist. This is the only
purpose the loop has. Every study serves it.

A study's purpose is a number that reads the done-condition. Write one sentence: what must
improve, the target, and the full workload it applies to. "1,000 pages in 8 hours" is a
purpose. It also gives the per-unit bar: 28 seconds a page. Every later projection is held
against this sentence.

Test the number before any result exists: could a method meet it without answering the
question? A benchmark whose gap is vocabulary rewards a lexicon. A benchmark whose answer
is printed in the prompt rewards arithmetic. When a method could win that way, the number
is a proxy. Change the number now, while it costs nothing.

When the purpose is a margin over a control, state the target as a **share of the
control's shortfall**, not as a fixed number of points. "+10 points" is a fifth of the
shortfall when the control scores 50%, and out of reach when it scores 95%, and nobody
knows which until the control runs. Name the reference the shortfall is measured to:
100%, an oracle, or a stronger system the method must approach. "The small model with the
method closes 30% of its gap to the large model" is a purpose. Fix the share now, before
any number is read, so it cannot drift toward what the data allows.

Add the **resolution floor**: the smallest shortfall, in cases per seed, that can resolve
the share. One lucky case meets any share of a shortfall of three.

Add a date. After it, an unmet purpose ends the study as banked or negative, and the loop
takes the next candidate. The date is never extended.

Done when `QUESTION.md` holds the question and its done-condition, and the study's
sentence carries a target, its reference, a resolution floor if it is a share, a workload
size and a date.

## 3. Freeze the yardstick

Pick the benchmark: a small fixed set of inputs that covers the kinds the workload holds.
A generated benchmark needs a census first: sample real instances of the workload, sort
them by the shape the generator makes, and count. A shape that is 4% of real work caps
any method on it at 4% of the purpose, however well it scores on the benchmark.
Run the current system on it and record the baseline row. For a share, run the control and
the reference too, and write the shortfall per seed as a count of cases. A shortfall under
the resolution floor means the benchmark cannot read the purpose. Grow it or change it
before any method runs. That is a fact about the benchmark, not a result about the method.
Convert the share into the count of cases the method must win per seed, and write it into
the baseline row. Pin what defines the yardstick:
the input set, the commit, the seeds, and the judge or scorer. The judge stays frozen for
the whole study. The cheapest way to look faster is to make the judge pass sooner, so a
change to the judge is its own probe, reported as one.

When the method learns, hold part of the yardstick out of its training and score only on
that part. A method that scores on the cases it trained on has shown memory.

Run the control on every seed before any method runs. When its spread across seeds is as
large as the margin the share asks for, one lucky seed can meet the share. Add seeds or
cases until the margin clears the spread.

Run one unit twice on the same seed and compare the outputs. When they differ, the arms
cannot be compared until the source of the difference is pinned, such as a thread count
or an unseeded shuffle. A later apparatus change, such as batching or a faster runtime,
must reproduce that output too. When it does not, it starts a new baseline.

Done when the baseline row is in the ledger with the commit and input set it ran on.

## 4. Profile before any hypothesis

Break the baseline cost down by stage, by turn, by test, or by call. Take the breakdown
from what the system records, or add the recording first. A total says something is slow.
A breakdown says one fixture runs 400 times, or one turn reads the whole corpus. The
hypotheses come from the breakdown.

Before tuning a stage, compute its roof: the fastest the hardware allows for the work it
does. Model decode on a CPU streams every weight once per token, so its roof is memory
bandwidth divided by weight bytes, however many threads run. A stage already near its roof
needs less work, not more tuning.

Done when the top cost items are named with their share of the total.

## 5. Map the field

Read `TRIED.md` and `FIELD.md` first, then the project's own history of what was tried.
Then load [[brainstorm]] and generate before judging. Judging while generating settles on
the obvious candidate, because it arrives with a metric and a price already attached.

The field is built for originality. Each time it is mapped or refilled:

- generate at least 10 candidates that differ in **mechanism**, not in size, such as less
  input per step, fewer steps, a cheaper model per stage, different work order, skipping
  work a cheap check proves unneeded, parallelism, or a different instrument,
- make at least 3 of them absent from `TRIED.md` and from the project's history,
- borrow at least 2 from another discipline, and name the discipline and the technique,
- carry at least 1 candidate you expect to fail, with a sentence on why it might not.

A candidate that repeats a `TRIED.md` line with a bigger model, more data, more compute or
more retries is the baseline, not a candidate. When a repeat is the right move, say what
changed since the line was written.

The field always holds the **no-method control**: the simplest mechanism that uses none of
the idea under test, such as brute-force search, a fixed rule, or the unchanged system
given the same extra compute. Measure it early. When it matches the method, the yardstick
cannot credit the method, and that is a finding about the yardstick. Give the control
every move the fault can need. A search that swaps names cannot fail on faults in operators
or literals and then count as the control for them.

The field also holds the **broken-link control**: the method's own output, attached to
the wrong case or the wrong site. A method that beats the no-method control and ties the
broken-link control wins on what it adds, such as more text or more compute, and not on
the link it claims. For each candidate write:

- the expected gain, tied to a line of the profile,
- the cost to test it,
- the result that would kill it.

Write the field into `FIELD.md`, where it outlives the session. Order it by expected gain
over cost to test and start at the top. Do not wait for the operator.

Done when the field holds at least as many candidates as the profile has cost items, meets
the originality counts above, and gives each candidate its kill result.

## 6. Probe

**Read the ceiling before running the instrument.** Most instruments have an expensive
part: a model call, a full rerun, a human judge. Compute the best result the run could
show from its inputs alone, with the expensive part assumed to go the candidate's way
wherever it is uncertain. A ceiling under the bar kills the run before it costs anything.
It takes minutes where the run takes days, and it reads the same inputs the run would.

**Read the consumer's ceiling too.** A method's output often reaches the purpose through
another system: a model that acts on advice, a person who reads a report, a tool with its
own input rules. Hand that system the perfect output before building the method's run. If
the oracle does not clear the bar, no method can, and the gap is in how the output is
delivered. Hand it the same format filled in by the no-method control as well, so the
format cannot take the method's credit.

**Check for leaks before a decisive run.** List every route by which the answer could
reach the measured path without the method: an oracle value, a name that spells the
answer, a template, a check that tells the agent more than the method would. Test each
route with a script over the generated inputs, because reading the generator misses what
the inputs hold. Then remove the method's learned part, such as zeroed weights or a
shuffled table, and confirm the result falls to the control. A result that survives its
own removal came from somewhere else.

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

## 7. Record, including the failures

One ledger row per step, appended before the step starts and completed when it ends. The
command that appends the row takes the start time from `date -Iseconds`, so the row exists
before the work does. A row written after the step began says its start is reconstructed.
Each row carries its `kind`:

| kind | what it is |
| --- | --- |
| `decisive` | its result settles a claim about the purpose |
| `exploration` | it informs the field without settling anything |
| `apparatus` | it makes a decisive step runnable, and names that step |
| `reflection` | a step back, written by the triggers in step 9 |

A failed probe keeps its row with the reason it failed. The row is the report.

The row format is in [references/ledger.md](references/ledger.md).

**`TRIED.md` is mandatory.** It is the operator's view of the whole loop, and it is kept
current. Add or change its line when a candidate dies, wins, is parked, or blocks, and do
it before the next probe starts. One line per method or route, newest first:

```
| date | what was tried | result | why |
| --- | --- | --- | --- |
| 2026-09-25 | Teach the small agent each dependent's fix from the change that broke it | did not work | The strong model won 8 of 8 against 2 of 8 for the best baseline, but the gap was vocabulary, not cause |
```

- **what was tried** says the idea in plain words a reader outside the project follows,
  with no file names, function names or check ids,
- **result** is one of: worked, did not work, undecided, blocked,
- **why** is one sentence, and any number in it carries the number it was compared against.

A `blocked` line names the layer it stopped at, apparatus, mechanism or question, and the
cheapest change that would unblock it.

## 8. Project every result against the question

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
probe re-runs the scorer on the recorded outputs. It reads the row's `settles` sentence,
the command and the bar, and nothing of the study's reasoning. It recomputes the number,
holds it against the bar, and repeats the leak check. Its number goes into the row's
`checked` field. When the two numbers differ, the row records both and the result stays
open until the difference is explained.

## 9. Step back

Write a `reflection` row when any of these fires:

- a step ran more than 3× its estimate,
- two hours of wall time passed since the last reflection,
- `apparatus` holds more than half the time since the last reflection,
- three probes in a row moved nothing,
- a result met the study's number and left the question unanswered.

A reflection answers four questions: where did the time go, what has been settled, is the
current path still the cheapest route to the done-condition, and does the yardstick still
measure the question. If a cheaper route exists, name it and take it. Continuing is a
decision the reflection has to argue for.

**The loop holds standing authority to redesign.** When a reflection finds that a
benchmark, a bar, a judge or an instrument measures something other than the question,
redesign it without waiting for the operator. Three rules bound that authority:

- the redesign is its own `reflection` row, stating what the old yardstick measured
  instead and what the new one measures,
- it applies only to probes that run after it and starts a new baseline, so a result
  already read is never re-scored under a friendlier judge,
- earlier results stay in the ledger and in `TRIED.md`, unchanged.

When two reflections in a row find no cheaper route, refill the field with step 5 instead
of stopping.

## 10. End a study, continue the loop

A study ends on one of three verdicts, and its report states it first:

- **reached**: the purpose is met on the yardstick.
- **banked**: a claim the study can defend that is not the purpose, stated with its gap
  to the purpose in numbers. Banking records a real result without moving the bar.
- **negative**: a kill result fired, or the study's candidates are exhausted.

Write the study's report from the ledger into `reports/`. The format is in
[references/report.md](references/report.md). Update `TRIED.md`. Then tell the operator in
a few lines: what died or won, and what the loop takes next. Take the next candidate from
`FIELD.md` and start the next study at step 2.

The loop stops only when:

- the done-condition in `QUESTION.md` is met, with a reached study as its evidence,
- the field is exhausted and a refill under step 5 produced no candidate absent from
  `TRIED.md`, which answers the question in the negative,
- the next step would spend money beyond a budget the operator agreed.

When the host offers a self-paced loop, each wake-up reads the working directory as in
step 1 and continues. A wake-up with a background job still running does cheap work from
the field or waits for the job.
