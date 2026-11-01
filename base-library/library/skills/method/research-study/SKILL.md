---
name: research-study
description: "Answering an operator's research question about a process by running a study: the question, its premises, its done-condition, a per-unit bar and a budget in money and hours written before the first probe; a frozen yardstick with a baseline row; a state line that routes the study to explore-then-improve while no mechanism clears the bar and to self-improve once a prototype has; a ceiling test that prices a mechanism's ideal path against the bar on paper after each build and when a waste traces to a design; a probe gate that admits no paid probe without the ideal-path cost, the roof and the trace in hand; every spending decision put to the operator with a figure; a ledger with every reading and its spend, a plain-words TRIED.md and a verdict of reached, banked or negative. Load when handed a goal or research question to pursue without the operator, when told to make something faster, cheaper or better, when a measurement comes back and the next step is unclear, or when a study directory is resumed."
argument-hint: "[the question, or the purpose: what must improve, by how much, over what workload]"
tags: [research, process]
---

# Research study

A study answers one question the operator wrote, about one process, against one number. It
finds a **mechanism** that can reach the number, builds it until it does once, then removes
what the mechanism wastes until a real unit of work clears the bar. The output is a verdict
the operator can act on, a `TRIED.md` of one plain line per thing tried, and a **ledger**
that keeps every reading with its spend.

The study runs alone. The operator hands over a question, not a method. The study decides
the mechanics and never what the money buys. It releases mechanisms and fixes, never the
question, which closes only on the operator's word or on the stop conditions of step 7.

Seven traps turn a study into one idea pursued for days, or into days with no result:

- **The first idea wins.** A plausible mechanism absorbs the budget before anything priced
  it against the bar.
- **The yardstick moves.** Each probe runs on different inputs, so no two results compare.
- **The method eats the time.** Framings, cards and checker rounds multiply, each correct by
  its own rule, and no number moves.
- **A number is recorded and never judged.** A result that projects to three weeks against
  an eight-hour purpose gets logged, and the next step starts.
- **Patience replaces judgement.** The study waits out any run and tries any approach once
  more, because nothing in its own view runs out. The operator's money and quota do.
- **The study never looks up.** Every choice follows its own rules, each one correct, and
  the operator learns what the money bought after it is gone.
- **A stopped probe closes the question.** The operator stops one round, the study reads it
  as a no to the whole question, and the work dies with the probe.

You do not perceive wall-clock time. A 15-minute command and a 1-minute command reach you
as one result each. The ledger's timestamps are how you see time. Read them. You do not
perceive money either. Every probe, every agent you brief and every turn you spend
attending draws on the operator's budget, and the ledger's `usd` field is how you see it.

## The three states

A study is in one of three states, written on the `state:` line of `QUESTION.md`:

| State | Question it answers | Skill that runs it | Leaves when |
| --- | --- | --- | --- |
| **explore** | which mechanism could reach the bar at all | [[explore-then-improve]] | a prototype clears the outcome bar once and its ideal path is priced |
| **prototype** | does the mechanism's best case clear the bar | this skill, the ceiling test of step 4 | the test passes or misses |
| **converge** | what the mechanism wastes, and how to remove it | [[self-improve]] | a real unit clears the bar, or a waste traces to a design cause |

The one edge between them is the **ceiling test**: the mechanism's ideal path, one pass per
stage with no retry, no hand step and no dead time, priced term by term and held against the
bar on paper. A pass sends the study to converge. A miss sends it back to explore with the
mechanism dead. Converge comes back to the test whenever a waste traces to a decision of the
mechanism's design and not of its execution, because that decision changes the ideal path.
A directory with no `state:` line is in converge: the mechanism it studies already exists.

The study stops when a **real unit** clears the bar on the frozen yardstick. A real unit is
one drawn from the workload the purpose names, not the input the prototype was built on. The waste still in the mechanism is priced in the report, and a [[self-improve]]
loop beside the live process keeps removing it.

## Value before procedure

Every step below serves the done-condition in `QUESTION.md`. A step done to the letter
that leaves the done-condition where it was has produced nothing.

Before a step, a probe or an agent, write one sentence: which gap to the bar it closes, and
what the yardstick reads if it works. When that sentence cannot be written, the action is
apparatus, and it waits for a step that needs it. The study's own paperwork is held to the
same sentence. A reading that exists today is cited, never argued about.

Reread `QUESTION.md` at every reflection and after every result. Then say in one sentence
what the operator would have in hand if the study stopped now. That sentence, not the count
of steps finished, is the study's progress.

## Ask what you are doing

Before a step spends, and at every reflection, answer in writing:

- What am I doing, in one line a reader outside the project follows?
- Which gap to the bar does it close, and which line of `QUESTION.md` says that gap matters?
- Who asked for it: a line of `QUESTION.md`, quoted, or the study? What the study added is
  a proposal until the operator takes it.
- What does it cost, and what share of the budget left?
- What has the spend so far bought, in one sentence of result?
- Is the study still the cheapest reader of the question, or does the ledger answer it?

An answer the study cannot give is a question to the operator, sent with a recommendation
and the ledger's one-sentence verdict, before the step runs. These decisions are the
operator's: the budget and its date, spending on once either is gone, a step priced above
a tenth of the budget left, a redesign of the yardstick, and a reading of the question that
drops or adds a premise. The study proposes each with a figure and waits. A question about
money offers, beside stopping, the next reading at its price, and recommends the cheapest
one that moves the answer. The operator's answer stops what it names: a probe, a round or
an instrument. The study then releases what that probe served, takes the next step at a
cheaper rung, and holds the question open until the operator closes it in words.
Unattended, with no channel to the operator, it takes the cheaper branch, records the
proposal in `QUESTION.md`, and the report lists every decision taken this way.

## 1. Open the working directory

The study keeps its state in `.study/<question-slug>/` at the root of the repository it
runs in. Add `/.study/` to `.git/info/exclude` when it is missing, so the directory stays
out of git without a change to a tracked file.

```
.study/<question-slug>/
  QUESTION.md    the question, its premises, its done-condition, its budget and its state line
  PROBLEMS.md    the profile's items ranked by reach, each with its cause and its status
  TRIED.md       one line per mechanism or fix: what it was, whether it held, why
  FRAMINGS.md    the readings of the question, written by the explore state
  FIELD.md       the candidate mechanisms, written by the explore state
  EXAMINED.md    the paths, tables and cycles of the converge state
  ledger.jsonl   every step, in the format of references/ledger.md
  reports/       one report per finished study, in the format of references/report.md
  logs/          background job logs
```

When the directory already exists, the study is resuming. Read `QUESTION.md` for the
state line, then `TRIED.md`, `PROBLEMS.md` and the ledger's last rows, and continue from
the open row in the skill the state names. Every session and every wake-up starts here.

The directory is the study's memory, not its publication. When the project keeps its own
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
exist. When none exist, write one and put it to the operator with the budget proposal
below. Then write the **purpose** in one sentence: what must improve, the target, and the
full workload it applies to. "1,000 pages in 8 hours" is a purpose, and it gives the
**bar** per unit: 28 seconds a page. Name the **unit**: the thing the process delivers once
per run, which the bar is per, such as a page, a story or one run of a suite. The bar has
two faces, and the study names both: the **outcome bar**, what a unit must contain or score
to count as delivered, and the **cost bar**, the time and money a unit may take. Every
later projection is held against them.

Test the number before any result exists: could a method meet it without answering the
question? When one could, the number is a proxy. Change it now, while it costs nothing.
When the purpose is a margin over a control, state the target as a share of the control's
shortfall, with the reference it is measured to and a **resolution floor**, under "A
purpose stated as a share" in [references/measurement.md](references/measurement.md). A
bar stated as a count has a floor of one unit of that count.

Then write the **budget**: the money and the wall hours the whole study may spend, on two
lines. The **probe line** pays for runs: every probe and every agent briefed to run one.
The **attending line** pays for the study's own turns and the readers it briefs. A figure
the operator gives for probes, a zero included, is the probe line, and the attending line
is still proposed. Without an operator figure, the study proposes a share of what the
answer is worth, never more than a tenth of the saving the purpose promises over the
horizon the operator named, or over three months when none was named, with the horizon
written as an assumption. The proposal states what the study spent before it and what that
spend bought, and the operator takes it before the first row spends against it. When the
spend so far already exceeds what the study would propose, the proposal says so and asks
for the next tranche: how much more, priced as the readings it buys, and never whether. The
ledger spends the budget down row by row, and the study never extends it. At half of it
with no result held, a reflection fires. At all of it, the study ends banked or negative
and stops. Add a date, which works the same way: the operator's, or one the proposal
carries, priced at the load the machine has shown, under "A plan at the measured load" in
[references/timing.md](references/timing.md).

Last, write the **state line**. A process that already exists and delivers units is the
study's first prototype: price its ideal path from the record, at no cost, and run the
ceiling test of step 4 on it. The verdict sets the state. A question with no mechanism yet
starts in `state: explore`.

Done when `QUESTION.md` holds the question, its premises, its done-condition, a purpose
with both bars, a named unit, a workload and a resolution floor, a budget on both lines in
money and hours, a date, and a state line.

## 3. Freeze the yardstick

Pick the benchmark: a small fixed set of inputs that covers the kinds the workload holds.
Run the current system on it when one exists and record the baseline row. Pin what defines
the yardstick: the input set, the commit, the seeds, and the judge or scorer. The judge
scores on cases the system under test never saw. The judge, the bars and the controls stay
frozen for the whole study. A change to any of them is its own ledger row that quotes the
old wording beside the new, signed by the operator before it counts, under "A change to
the yardstick" in [references/measurement.md](references/measurement.md). That file also
holds the rule for a generated benchmark, a method that learns, a repeated unit and the
two controls. Read the section whose case applies. A timed baseline follows
[references/timing.md](references/timing.md).

A baseline and a reference run read what exists. They are exempt from the ceiling test and
the probe gate, and their rows say so. When the probe line is zero, or the operator forbids
a fresh run, the record of the last run stands as the baseline: its row cites the trace,
labels every reading **assumed**, and the first paid rung replaces it. The timing rules
void a timing for a verdict, never for a baseline labelled assumed.

Done when the baseline row is in the ledger with the commit and input set it ran on, or
the trace it stands on, or the row says no system exists to run, and the study is in the
skill its state line names.

## 4. The ceiling test

The **ideal path** of a mechanism is one pass per stage, in order, with no retry, no hand
step and no dead time. Each term of it is a cost per unit, labelled **measured**, with the
ledger row that read it, or **assumed**, with its source: a rate card, a vendor figure, a
similar stage's reading. The **ceiling** is the best a unit can cost on that path. It is
the mechanism's floor, and no execution beats it.

Run the test on paper, as its own `ceiling` row, at three moments:

- after a prototype clears the outcome bar once and its ideal path is priced, which is
  how the explore state hands back;
- when the converge state traces a waste to a **design cause**, a decision of the
  mechanism that redraws its ideal path, and re-prices the path with that cost inherent;
- before any paid probe whose mechanism has no priced ideal path yet.

Hold the ceiling against the cost bar and the mechanism's best recorded unit against the
outcome bar: the prototype's run, or for an existing process any run of it in the record,
cited by row or by trace.

- **Pass.** The ceiling is under the cost bar and the outcome bar was cleared. The margin
  between the ceiling and the bar is the room the converge state works in, and the sum of
  the assumed terms is the risk it carries. Write `state: converge` and the margin into
  `QUESTION.md`.
- **Miss.** The ceiling is at or over the cost bar, or no run of the mechanism ever
  cleared the outcome bar, the prototype inside its cap included. The mechanism cannot
  reach the bar however well it is executed. Write the `TRIED.md` line with the term that
  sank it, mark the mechanism dead in `FIELD.md`, and write `state: explore`.

A prototype that never cleared the outcome bar is a miss, with the bar it missed as its
reason. An existing process that never cleared it is one too, and the study that was asked
to improve it goes to explore for the mechanism that can. A pass does not say the mechanism works. It says the mechanism is worth converging.

Done when the row holds every term with its label and source, the ceiling, both bars, the
verdict and the state line it set.

## 5. The probe gate

A **probe** is any step that spends money or wall time on a run: a turn, a stage, a whole
system, an agent briefed to run one. An agent briefed to read records and run nothing, such
as a judge or a checker, is attending spend and not a probe. No probe runs until its ledger
row carries three fields:

- **ideal path**: the ceiling of the mechanism the probe serves, from its latest `ceiling`
  row, or the baseline exemption;
- **roof**: the fastest the hardware or the task allows for the work the probe's stage
  does, so the reading can say how far from it the stage sits;
- **trace**: the row or record of a run already paid for that answers the probe's
  question, or the sentence saying why none does.

A probe whose trace field names a row is not run: the row is cited. The two state skills
carry the same three fields, so a probe registered from either skill is gated the same
way. A probe that passes twice its estimate is stopped, its row keeps the partial reading,
and the broken estimate is a finding about the instrument. Run anything over a few minutes
as a background job with its log in `logs/`, and do cheap work while it runs.

Done when every `probe` row in the ledger carries the three fields before its `start`.

## 6. Spend, reflect and check

One ledger row per step, appended before the step starts and completed when it ends, with
its `kind` and its `usd`, in the format of [references/ledger.md](references/ledger.md). A
`usd` the host's usage record cannot supply is null, with the row saying where the figure
will come from. A failed probe keeps its row with the reason. **`TRIED.md` is mandatory**: it is the
operator's view of the whole study, one line per mechanism or fix in plain words a reader
outside the project follows, changed before the next probe starts.

Write a `reflection` row when any of these fires:

- a probe passed twice its estimate,
- the budget is half spent with no result held,
- a mechanism or a problem was released,
- two hours of wall time passed since the last reflection,
- the session, the tranche or the date is about to end, so the stop has a reflection
  before it,
- `apparatus` holds more than half the time since the last reflection,
- three probes in a row moved nothing,
- a result met the purpose and left the done-condition unanswered.

A reflection starts by rereading `QUESTION.md`. It then answers in writing: what would the
operator have in hand if the study stopped now, where did the time go, which state is the
study in and does the state line agree, does the yardstick still measure the question,
what did the study do that no line of `QUESTION.md` asked for, and would the operator fund
the next step if shown the ledger. Continuing is a decision the reflection argues for in
numbers: the readings the budget still buys, and which gap each one closes. A reflection
whose answers touch the budget, the date, the yardstick or the question goes to the
operator as a question with a recommendation before the next probe.

The study holds standing authority to propose a redesign. When a reflection finds that a
benchmark, a bar, a judge or an instrument measures something other than the question,
design the replacement and put it to the operator in the same turn, as its own
`reflection` row. It applies only to probes that run after it and starts a new baseline.

A probe that decides the study's verdict is registered and regraded by a second agent
before it counts, under [references/second-agent.md](references/second-agent.md). A
reading that means the instrument cannot resolve the floor is the most valuable one a
study produces: stop that path before spending on it. Load [[step-back]] when the same
kind of attempt has failed three times on one goal.

Done when every row carries its `kind`, its `usd` and its outcome, every trigger above
that fired has its `reflection` row, and `TRIED.md` carries a line per mechanism or fix.

## 7. End a study, continue the loop

A study ends on one of three verdicts, and its report states it first:

- **reached**: a real unit clears both bars on the yardstick.
- **banked**: a claim the study can defend that is not the purpose, stated with its gap
  to the purpose in numbers. A mechanism in converge with its margin is a banked claim.
- **negative**: every surviving framing died for its own reason, and the explore state
  returned no candidate absent from `TRIED.md`. A negative verdict lists every assumption
  that could flip it. A verdict one undeclared assumption could flip is open, not negative.

Write the report from the ledger into `reports/`, in the format of
[references/report.md](references/report.md), with the mechanism's remaining waste priced
per unit. Update `TRIED.md`. Then tell the operator in a few lines: what held or died, what
the number reads now against the bars, which state the study is in, and what it takes
next. "Needs building" is not a verdict: a mechanism that needs building is the explore
state's next prototype, inside the budget left.

The study stops only when:

- the done-condition in `QUESTION.md` is met, with a reached study as its evidence,
- the verdict is negative by the rule above,
- the budget or the date in `QUESTION.md` is spent, and the report prices what the state
  skill still holds, so the operator can fund the next tranche or close the question.

When the host offers a self-paced loop, each wake-up reads the working directory as in
step 1 and continues in the skill the state line names. A wake-up with a background job
still running does cheap work or waits for the job.
