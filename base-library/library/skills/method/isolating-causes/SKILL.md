---
name: isolating-causes
description: "Load when you need to know why something happens: a bug or an error, a flaky test, a slowdown, a metric or score that moved, a behaviour that differs between two runs, inputs or versions, or a set where some cases fail and others pass. Also load when a fix or a change did not have the effect you expected. Builds a loop that shows the effect on demand before any hypothesis, then reproduces and minimises it, ranks 3 to 5 falsifiable hypotheses by contrast between the cases that show the effect and the cases that do not, and changes one variable at a time until one cause is confirmed. A defect ends with its fix behind a regression test. To judge whether a fix reaches the origin, load root-cause. After three attempts that left the effect in place, load step-back."
tags: [tests, standards]
---

# Isolating causes

A discipline for finding what causes an effect that did not explain itself at the first look.
The effect is often a bug: an error, a wrong value, a flake, a slowdown. It can also be a score
that moved, a behaviour that differs between two runs, or a set where some cases pass and others
fail. Skip a phase only by saying which one and why.

Throughout, the **effect** is the thing to explain, and **red** means the loop shows it.

## Phase 1: a loop that goes red

**This is the skill.** Everything after it is mechanical. With a **tight** pass/fail signal
that goes **red** on *this* effect, bisection, hypothesis-testing and instrumentation all
consume it. Without one, no amount of reading code substitutes. Spend disproportionate effort
here.

The loop serves the question. Before building it, write the effect in one sentence, in the
reporter's words. Every phase ends by holding its result against that sentence.

### Pick the seam

Reach for the highest seam that can go red on the effect. A loop closer to the code that
produces the effect is faster and sharper than one further away.

| Seam | Loop | Goes red on |
| --- | --- | --- |
| **Unit** | call the function directly from a test | one function's own logic |
| **Component** | the component's own test suite, narrowed to the case | anything inside one package or module |
| **CLI** | the command with a fixture input, diffed against a known-good output | an output regression |
| **Repo gate** | the lint, type or custom check whose exit status settles it | a standard the tree violates |
| **Experiment** | the run, benchmark or job with one input changed, compared against a baseline | a score or a behaviour that moved |
| **Live system** | the running system's status, logs, traces and telemetry | what a process actually did, or is doing now |
| **Replay** | the real payload, trace or event log saved to disk and driven through the code path | an effect only the production input triggers |
| **Throwaway harness** | a script in the scratchpad that calls the path directly | everything above being too far from the effect |

The repo's own tool skills and its `Makefile` name its concrete seams. Reach for those before
inventing one.

**Substitute, don't patch.** When code takes its collaborators as arguments or fields, a test
supplies its own. Assigning over module attributes means restoring them afterwards, and a loop
built on a patch that leaks is a loop that lies.

### Tighten the loop

Treat the loop as the product of this phase. Once you have *a* loop, make it:

- **Faster.** Narrow the test scope, skip unrelated setup, reuse a cached fixture.
- **Sharper.** Assert the reported effect exactly, not "did not crash".
- **More deterministic.** Pin time, seed randomness, isolate the filesystem, freeze the
  network. Clocks, random numbers and live network are the three that make a loop flap.

A 30-second flaky loop is barely better than none. A 2-second deterministic one is a
superpower.

### An intermittent effect

The goal is a **higher reproduction rate**, not a clean repro. Loop the trigger 100 times,
parallelise, add stress, narrow the timing window, inject a sleep at the suspected race. A 50%
flake is debuggable. A 1% flake is not, so raise the rate until it is.

### An effect that shows on a set

Some effects show on several examples and not on others: part of a test suite, some inputs of a
batch, some seeds or configs. Make the loop run **every** example and print each verdict. The
**failing set** and the **passing set** it prints are the evidence Phase 3 ranks against, and
the passing set is the half that is easy to throw away.

### Completion criterion: a red-capable command you have already run

Phase 1 is done when you can name **one command**, and have **already run it at least once**
showing its invocation and output, that is:

- **Red-capable.** It drives the code path that produces the effect and asserts the **reported
  effect**, so it goes red now and green once the cause is removed.
- **Deterministic.** It gives the same verdict every run, or a pinned high reproduction rate.
- **Fast.** It takes seconds, not minutes.
- **Unattended.** It runs with no human in the middle.

Reading code to build a theory before that command exists is the exact failure this skill
prevents. No red-capable command, no Phase 2.

### When the loop cannot be built

Bound the effort per seam. Three attempts to make one seam go red is the limit. After the
third, move to the next seam down the table. Repairing the seam itself is a second problem, and
it has replaced the first. When no seam in the table goes red, the loop cannot be built.

Say so explicitly, list what you tried, and ask for one of: access to the environment that
reproduces it, a captured artifact (a log, a trace, a HAR, a core dump, the run's output
directory), or permission to add temporary instrumentation to the running system. Redact every
secret first: write `<REDACTED>` in its place, and build loops against a variable so the
credential stays out of what you show.

## Phase 2: reproduce, then minimise

Run the loop and watch it go red. Confirm three things:

- It produces the effect **the report described**, not a different one nearby. Wrong effect,
  wrong cause.
- It reproduces across runs, or at a rate high enough to work against.
- You have captured the exact effect (message, wrong value, timing, score), so a later phase
  can prove the cause it names is *this* effect's cause.

Then shrink to the **smallest scenario that still goes red**. Cut inputs, callers, config, data
and steps **one at a time**, re-running after each cut. Done when every remaining element is
load-bearing: removing any one turns the loop green.

Every cut that turns the loop green is a passing neighbour of the failing scenario. Keep them.
They are the passing set when the effect started as a single case.

A minimal repro shrinks the hypothesis space in Phase 3 and becomes the confirming experiment
in Phase 5. Do not proceed until you have both reproduced and minimised.

## Phase 3: hypothesise

Generate **3 to 5 hypotheses before testing any of them**. Testing the first plausible one anchors
the whole diagnosis on it.

Each must be **falsifiable**. State the prediction: *if X is the cause, then changing Y makes
the effect disappear, and changing Z makes it worse.* A hypothesis with no prediction is a vibe.
Sharpen it or drop it.

**Rank by contrast, not by coverage.** A hypothesis earns its rank by separating the failing
examples from the passing ones. "Every failing run goes through X" is coverage, and the passing
runs usually go through X too. For each hypothesis, write down the examples whose verdict it
would change. The best one changes every failing example and no passing one. When the loop
prints more than a couple of each, read
[references/contrast-ranking.md](references/contrast-ranking.md) before ranking. It carries the
score, the shuffled control that tells a cause from a busy site, the check budget, peeling a
second fault, and where the method goes blind.

Show the ranked list before testing. The person who reported the effect often re-ranks it
instantly ("we deployed a change to #3 yesterday") or has already ruled one out. Do not block
on the answer. Proceed with your own ranking if nobody is there.

## Phase 4: instrument

Every probe maps to a specific prediction from Phase 3, and you **change one variable at a
time**.

1. Inspect state directly where the environment allows it. One breakpoint beats ten logs.
2. Otherwise log at the **boundary that distinguishes two hypotheses**, not everywhere.

**Tag every debug log with a unique prefix**, such as `[DEBUG-a4f2]`, so cleanup is one grep.
Untagged debug logs survive into the tree. Tagged ones die.

**A measured effect takes the other branch.** When the effect is a number, such as a slowdown
or a score, logs are usually the wrong instrument. Establish a baseline measurement first, from
the system's own wall-time breakdown, a timer, a profiler for in-process work, or the scorer
the effect was reported in. Then bisect against that number. Measure first, change second.

## Phase 5: confirm the cause

A hypothesis is confirmed when removing its cause turns the loop green and restoring the cause
turns it red again. Do both. A loop that went green once may have gone green for another reason.
Then re-run the Phase 1 loop against the **original, un-minimised** scenario, and against every
example when the effect showed on a set.

**A change that leaves the loop red has refuted its hypothesis.** Revert it, cross the
hypothesis off the Phase 3 list and take the next one. A second change stacked on the first
tests two variables at once, and the loop can no longer say which one mattered. When the list is
exhausted, return to Phase 3 with what the refutations showed and write a new list.

Three refuted hypotheses on one effect is a stream of attempts. Load [[step-back]] before the
fourth.

### A defect: fix behind a regression test at a confirmed seam

When the effect is a defect, write the regression test **before the fix**, but only at a
**correct seam**: one where the test exercises the real defect as it occurs at the call site. A
seam too shallow to replicate the chain that triggered the defect gives false confidence, which
is worse than no test.

**If no correct seam exists, that is itself the finding.** Say so. The architecture is what
prevents the defect from being locked down, and that belongs in the post-mortem.

With a correct seam:

1. Turn the minimised repro into a failing test there.
2. Watch it fail.
3. Apply the fix.
4. Watch it pass.
5. Re-run the Phase 1 loop against the original scenario, as above.

## Phase 6: cleanup and post-mortem

Before calling it done:

- The confirmed cause is written down with the experiment that confirmed it.
- For a defect, the original repro no longer reproduces. Re-run the Phase 1 loop, not the
  minimised one.
- For a defect, the regression test passes, or the absence of a seam is written down.
- Every `[DEBUG-…]` probe is gone. Grep the prefix.
- Throwaway harnesses are deleted or left in the scratchpad, never in the tree.
- The repo's lint and type gates and the affected tests pass.
- **The hypothesis that turned out correct is in the commit message or the report**, so the
  next person working near this code starts where you finished.

When the effect was a defect, ask what would have prevented it. If the answer is a gate the repo
could have had, that is an automated check, not a note. Make the recommendation *after* the fix
is in, because you know more now than when you started.

## When to reach for the neighbours

- **You have a fix and must judge whether it reaches the origin**, or you are about to add a
  retry, a waiver, a default or a broader catch: [[root-cause]].
- **Three hypotheses have been refuted**, or the work on the loop has grown larger than the
  question: [[step-back]].
- **The loop runs one of the repo's own tools**, such as its test harness, its telemetry or its
  graph checks: the skill that owns that tool carries its commands and its traps.

---

*The phase structure is adapted from [`mattpocock/skills`](https://github.com/mattpocock/skills)
(`diagnosing-bugs`), MIT-licensed. Contrast ranking comes from a study of fault localisation on
generated faults.*
