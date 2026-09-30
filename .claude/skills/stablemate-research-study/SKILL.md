---
name: stablemate-research-study
description: "Running a research or optimization loop alone until the operator's question is answered, and reporting what was tried, what worked and what did not: a gitignored working directory in the repo, the question's done-condition written before any number, a mandatory TRIED.md in plain words, a frozen yardstick, a profile before any hypothesis, a field of original candidates mapped before digging, several framings of the question written in isolation so no reading inherits another's assumptions, a paper gate that discards any candidate answering another question or unable to succeed by construction before anything is built, single-variable probes cheapest-decisive first, a ledger that keeps every failure, a projection of each result against the question, standing authority to redesign an instrument that measures the wrong thing, and a loop that starts the next study when one dies. Load when told to find a way to make something faster, cheaper or better, when handed a goal or research question to pursue without the operator, when a measurement comes back and the next step is unclear, or when the last hours went to making an experiment runnable rather than to results."
metadata:
  generated_by: farrier
  source: library/skills/research-study/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-research-study/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
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

Seven traps turn a study into one idea pursued for days:

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
  a study writes carries the briefer's reading of the question. The field then varies the
  implementation while every candidate shares one reading. A failure of that reading
  passes for a failure of the question, and it steers the next study toward its neighbour.
- **The framing decides the answer.** The study casts the problem so that no method can
  succeed, builds the method, measures the failure, and reports a "no" that was known on
  paper before anything ran.

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
on disk, extract every message the operator wrote and read each one. Memory keeps the
premises that fit the reading already formed and drops the ones that rule it out. Three
kinds are the easiest to lose:

- **the end goal** behind the question, such as "reduce my dependency on frontier models",
  which fixes what the result is compared against,
- **a ruling** on an approach, such as "a compiler is over-restrictive, the model will have
  no agency", which removes a whole reading before any agent proposes it,
- **the setting**, such as "we are building this for production code", which rules out a
  testbed that only works because it is small.

Under the premises, write the
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

## 5. Frame the question, then map the field

### Framings first

A **framing** is a reading of the question. It says what the thing under study does, on
which input, to produce which output, judged how, and what the question's key verb means,
such as "leverage", "replace" or "speed up". It names no mechanism, no architecture, no
data source and no file. Those belong to candidates, and a candidate always sits under one
framing.

Write at least three framings. Isolation keeps a framing from inheriting another's details,
and it does not make framings differ. Agents that share a model and read the same documents
converge on one reading. Handing a later agent the first reading and one axis to vary does
not fix that either: the agent turns that axis and copies the first reading on every other
one, so every framing is a sibling of the first. Framings differ when each is built from
its own choice on every open axis:

1. **List the axes.** One agent reads the question and the premises from step 2, and
   nothing else. It lists the axes a reading must choose on: the role the thing under
   study plays, the input it reads when it runs, the output it produces, what counts as
   right and who judges, what the question's key verb is measured against, which part of
   the problem the study may redesign, and any axis the question adds. For each axis it
   writes **fixed**, with the operator's words that fix it, or **open**, with at least
   three values. An axis is fixed only as far as its words go. "Reduce my dependency"
   fixes a direction, not zero, and "prefer" fixes a preference, not a requirement. A
   fixed axis stated stronger than its quote removes readings the operator left open,
   and nothing downstream sees them go. A value says what, never how. A value that names
   an algorithm, an architecture, an algebra, a fitting method or a data generator is a
   candidate, and it waits for step "Then the candidates". Rows built from mechanisms
   differ in implementation and share one reading of the question. At least one value per open axis is one the project's existing apparatus
   does not support. It then holds every open value against every fixed axis and drops a
   value that breaks one, with the quote that breaks it.
2. **Draw the rows.** Pick one value per open axis for each framing, so that any two
   framings differ on at least half of the open axes. No row is the "direct" reading, and
   no row is written first for the others to vary. Each clause of the question is the
   measure a verdict rests on in at least one row. A clause such as "to limit training
   cost" that no row is judged by is a reading the field never tests.
3. **Write each row in isolation.** A fresh agent, or a fresh context, gets the question,
   the premises word for word, pointers into the project and its row. It reads nothing the
   study has produced and no other row's framing. It writes the framing its row implies. A
   row agent never repairs its own row. When a value fails gate 1, the agent stops and
   returns that value with the operator's words that break it. Agents that share a model
   and repair alone reach the same repair, so five repaired rows converge on one yardstick.
   The axis agent drops or corrects the value for every row, redraws the rows, and the
   failed rows are written again.

Three rules hold for every framing agent:

- the brief carries the question, the premises word for word, pointers into the project
  and the agent's row. It carries nothing the briefer concluded. A sentence such as "the
  task here means X" in a brief is the briefer's framing, and every agent that reads it
  inherits it. A premise the briefer paraphrased is the briefer's framing too,
- anything the loop or its agents made earlier counts as study output: a roadmap line, a
  hypothesis, a result, and also code, a benchmark, a judge or a testbed. A framing agent
  reads study output for facts it can check, never for goals, bars or verdicts. An artifact
  the study built is one value on an axis, never the default,
- on a refill after a study ends, the framing agents also read the one-line status of each
  past framing in `FRAMINGS.md`, so they can avoid it. They read none of its
  implementation, because a dead framing's details are the main route of contamination.

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

## 6. Reason on paper before building

A candidate reaches a build only after it survives on paper. The paper phase reads the
question, the field and the repository, and nothing runs. Most dead candidates die here,
because the reason they fail is already written in their own description. A build that
measures a failure the paper predicted says nothing about the question.

For each candidate that is about to be probed, write a **card** into `FIELD.md` before any
code, data or model call. The card holds:

- **the question's task**: its input, its output and the role it gives the thing under
  study, copied from the operator's words and not paraphrased,
- **the method's task**: the input the method reads at test time, the output it produces,
  and who or what produces each part of it,
- **the training task**, when the method learns: the input, the target, where the pairs
  come from and how many exist,
- **the judge**: what counts as a right output,
- **every assumption** the method needs, one per line, each marked as stated by the
  operator, checked, or assumed,
- **which inputs are fixed and which are designed**: an input the world hands over, such
  as an existing codebase, is fixed. An input whose format the study may choose, such as
  the notation a request is written in, is designed. Mark each, and cite the premise that
  makes it so,
- **the named method's defining parts**, when the candidate borrows a name such as an
  architecture, an algorithm or a published technique: each part that makes the name true,
  marked built or left out.

### Gate 1: does it answer the question as posed?

Hold the method's task against the question's task, part by part.

- **The input matches.** A method that swaps the question's input for a proxy answers
  another question. A model that writes a function from its nearest sibling does not write
  it from the specification the question names. A chooser that never reads that
  specification is not a method for it.
- **The output matches.** A method that produces a slice of the output answers the
  question only when the question allows a slice and the rest has a named author.
- **The role matches.** A question that asks how to leverage a component is not answered
  by casting that component as a replacement for the whole system. Write the role the
  question gives it on the card.
- **Every premise holds.** A premise the operator stated and the method dropped makes a
  different question.

A candidate that fails gate 1 leaves the field with the mismatch as its reason. A rewrite
that makes the input, the output and the role match is a new candidate with its own card.

### Gate 2: can it succeed by construction?

Each check asks whether the method can succeed when everything uncertain goes its way. One
"no" means the build can only confirm a failure already known.

- **Identifiability.** The input carries the information the output needs. For each part
  of the output, name the part of the input it comes from. A part with no source must be
  guessed, and the guess rate is the ceiling. Check the training pairs and the test cases
  separately. When the missing part sits in a designed input, the repair is to
  change the input's format so it carries the part. Accepting the loss is a choice the card
  must argue for, and a designed input never loses a fact by default.
- **Train equals test.** The training task has the same input and the same output as the
  measured task. A model trained to edit one artifact into another is not trained to write
  the second from a description.
- **The judge accepts every right answer.** A judge that credits only one reference
  output fails a correct output that differs from it. Prefer a functional judge, such as
  compiled checks, tests or a build. When the judge must compare against a reference, say
  how many right answers it accepts and why that is enough.
- **Method fidelity.** Every defining part of the named method is built, or the verdict
  names the gap. A result from a method missing its defining parts is a result about
  another method, and it cannot close the named one.
- **The data fits the target.** The training data comes from the distribution the test
  draws from, in kind and in volume. Name the source and count it before building.
- **The compute fits the claim.** Estimate what the method needs to learn the task at all,
  from the size of the output space and from published results. A budget short by orders
  of magnitude makes the run measure the budget.
- **The operator's levers are used.** When the question names a lever, such as a preset,
  a prior, a representation or a budget, the card says how the method uses it. A method
  that ignores a named lever tests the question without its premise.

A candidate that fails gate 2 is repaired on paper, with the failed check named in the
repair, or it leaves the field. Record it in `TRIED.md` as "did not work (on paper)" with
the failed check as its reason.

### Declare the framing each probe tests

Every card names its framing from `FRAMINGS.md`. Test each framing against the operator's
words, sentence by sentence, as its own claim: which component does what, on which input,
judged how. The framing is where a study goes blind. A framing that makes the question
unanswerable yields a "no" about the framing, and the study reports it as a "no" about the
question.

A "no" found under one framing is a "no" for that framing. The question is answered in the
negative only when every surviving framing has died, each for its own reason.

Have the framings and the cards checked. A second agent that did not write them reads the
question, the premises, the framings and the cards, and nothing of the study's reasoning.
It answers both gates for each, names any assumption that makes the question unsolvable,
and names any two framings that share their input, output and role. A card or a framing it
fails goes back to repair.

Done when at least three framings survive in `FRAMINGS.md` or the rest died on paper,
every candidate about to be probed has a card that passed both gates in writing, and a
second agent agreed.

## 7. Probe

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
probe re-runs the scorer on the recorded outputs. It reads the row's `settles` sentence,
the command and the bar, and nothing of the study's reasoning. It recomputes the number,
holds it against the bar, and repeats the leak check. Its number goes into the row's
`checked` field. When the two numbers differ, the row records both and the result stays
open until the difference is explained.

## 10. Step back

Write a `reflection` row when any of these fires:

- a step ran more than 3× its estimate,
- two hours of wall time passed since the last reflection,
- `apparatus` holds more than half the time since the last reflection,
- three probes in a row moved nothing,
- a result met the study's number and left the question unanswered.

A reflection answers five questions: where did the time go, what has been settled, is the
current path still the cheapest route to the done-condition, does the yardstick still
measure the question, and does the framing in `QUESTION.md` still pass both paper gates. If a cheaper route exists, name it and take it. Continuing is a
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
