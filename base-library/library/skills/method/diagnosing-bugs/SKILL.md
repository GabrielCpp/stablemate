---
name: diagnosing-bugs
description: "Diagnosis discipline for a hard bug, a flake, or a performance regression, in any codebase: build a loop that goes red on this bug before forming any hypothesis, reproduce and minimise, rank 3 to 5 falsifiable hypotheses, instrument one variable at a time behind a tagged prefix, and land the fix behind a regression test at a confirmed seam. When some examples fail and others pass, rank the hypotheses by contrast: which examples each one would change, scored against the failing set and a shuffled control. Load when something is broken, throwing, failing intermittently or slower than it was, when a fix has already been attempted and did not hold, or when a test suite or a batch of inputs fails in part and you are choosing which hypothesis to test first. To judge whether a fix reaches the origin, load root-cause. After three fixes that left the loop red, load step-back."
tags: [tests, standards]
---

# Diagnosing bugs

A discipline for a bug that did not fall to the first look. Skip a phase only by saying which
one and why.

## Phase 1: a loop that goes red

**This is the skill.** Everything after it is mechanical. With a **tight** pass/fail signal
that goes **red** on *this* bug, bisection, hypothesis-testing and instrumentation all consume
it. Without one, no amount of reading code substitutes. Spend disproportionate effort here.

The loop serves the bug. Before building it, write the reported symptom in one sentence, in
the reporter's words. Every phase ends by holding its result against that sentence.

### Pick the seam

Reach for the highest seam that can go red on the symptom. A loop closer to the bug is faster
and sharper than one further away.

| Seam | Loop | Goes red on |
| --- | --- | --- |
| **Unit** | call the function directly from a test | one function's own logic |
| **Component** | the component's own test suite, narrowed to the case | anything inside one package or module |
| **CLI** | the command with a fixture input, diffed against a known-good output | an output regression |
| **Repo gate** | the lint, type or custom check whose exit status settles it | a standard the tree violates |
| **Live system** | the running system's status, logs, traces and telemetry | what a process actually did, or is doing now |
| **Replay** | the real payload, trace or event log saved to disk and driven through the code path | a bug only the production input triggers |
| **Throwaway harness** | a script in the scratchpad that calls the failing path directly | everything above being too far from the bug |

The repo's own tool skills and its `Makefile` name its concrete seams. Reach for those before
inventing one.

**Substitute, don't patch.** When code takes its collaborators as arguments or fields, a test
supplies its own. Assigning over module attributes means restoring them afterwards, and a loop
built on a patch that leaks is a loop that lies.

### Tighten the loop

Treat the loop as the product of this phase. Once you have *a* loop, make it:

- **Faster.** Narrow the test scope, skip unrelated setup, reuse a cached fixture.
- **Sharper.** Assert the user's exact symptom, not "did not crash".
- **More deterministic.** Pin time, seed randomness, isolate the filesystem, freeze the
  network. Clocks, random numbers and live network are the three that make a loop flap.

A 30-second flaky loop is barely better than none. A 2-second deterministic one is a
superpower.

### An intermittent bug

The goal is a **higher reproduction rate**, not a clean repro. Loop the trigger 100 times,
parallelise, add stress, narrow the timing window, inject a sleep at the suspected race. A 50%
flake is debuggable. A 1% flake is not, so raise the rate until it is.

### A bug that shows on a set

Some bugs fail several examples and pass others: part of a test suite, some inputs of a batch,
some seeds or configs. Make the loop run **every** example and print each verdict. The
**failing set** and the **passing set** it prints are the evidence Phase 3 ranks against, and
the passing set is the half that is easy to throw away.

### Completion criterion: a red-capable command you have already run

Phase 1 is done when you can name **one command**, and have **already run it at least once**
showing its invocation and output, that is:

- **Red-capable.** It drives the actual bug code path and asserts the **reported symptom**, so
  it goes red now and green once fixed.
- **Deterministic.** It gives the same verdict every run, or a pinned high reproduction rate.
- **Fast.** It takes seconds, not minutes.
- **Unattended.** It runs with no human in the middle.

Reading code to build a theory before that command exists is the exact failure this skill
prevents. No red-capable command, no Phase 2.

### When the loop cannot be built

Bound the effort per seam. Three attempts to make one seam go red is the limit. After the
third, move to the next seam down the table. Repairing the seam itself is a second bug, and
it has replaced the first. When no seam in the table goes red, the loop cannot be built.

Say so explicitly, list what you tried, and ask for one of: access to the environment that
reproduces it, a captured artifact (a log, a trace, a HAR, a core dump, the run's output
directory), or permission to add temporary instrumentation to the running system. Redact every
secret first: write `<REDACTED>` in its place, and build loops against a variable so the
credential stays out of what you show.

## Phase 2: reproduce, then minimise

Run the loop and watch it go red. Confirm three things:

- It produces the failure **the report described**, not a different one nearby. Wrong bug,
  wrong fix.
- It reproduces across runs, or at a rate high enough to debug against.
- You have captured the exact symptom (message, wrong value, timing), so a later phase can
  prove the fix addressed *it*.

Then shrink to the **smallest scenario that still goes red**. Cut inputs, callers, config, data
and steps **one at a time**, re-running after each cut. Done when every remaining element is
load-bearing: removing any one turns the loop green.

Every cut that turns the loop green is a passing neighbour of the failing scenario. Keep them.
They are the passing set when the bug started as a single failure.

A minimal repro shrinks the hypothesis space in Phase 3 and becomes the regression test in
Phase 5. Do not proceed until you have both reproduced and minimised.

## Phase 3: hypothesise

Generate **3 to 5 hypotheses before testing any of them**. Testing the first plausible one anchors
the whole diagnosis on it.

Each must be **falsifiable**. State the prediction: *if X is the cause, then changing Y makes
the bug disappear, and changing Z makes it worse.* A hypothesis with no prediction is a vibe.
Sharpen it or drop it.

**Rank by contrast, not by coverage.** A hypothesis earns its rank by separating the failing
examples from the passing ones. "Every failing run goes through X" is coverage, and the passing
runs usually go through X too. For each hypothesis, write down the examples whose verdict it
would change. The best one changes every failing example and no passing one. When the loop
prints more than a couple of each, read
[references/contrast-ranking.md](references/contrast-ranking.md) before ranking. It carries the
score, the shuffled control that tells a cause from a busy site, the check budget, peeling a
second fault, and where the method goes blind.

Show the ranked list before testing. The person who reported the bug often re-ranks it
instantly ("we deployed a change to #3 yesterday") or has already ruled one out. Do not block
on the answer. Proceed with your own ranking if nobody is there.

## Phase 4: instrument

Every probe maps to a specific prediction from Phase 3, and you **change one variable at a
time**.

1. Inspect state directly where the environment allows it. One breakpoint beats ten logs.
2. Otherwise log at the **boundary that distinguishes two hypotheses**, not everywhere.

**Tag every debug log with a unique prefix**, such as `[DEBUG-a4f2]`, so cleanup is one grep.
Untagged debug logs survive into the tree. Tagged ones die.

**A performance regression takes the other branch.** Logs are usually the wrong instrument.
Establish a baseline measurement first, from the system's own wall-time breakdown, a timer, or
a profiler for in-process work. Then bisect against that number. Measure first, fix second.

## Phase 5: fix behind a regression test at a confirmed seam

Write the regression test **before the fix**, but only at a **correct seam**: one where the
test exercises the real bug pattern as it occurs at the call site. A seam too shallow to
replicate the chain that triggered the bug gives false confidence, which is worse than no test.

**If no correct seam exists, that is itself the finding.** Say so. The architecture is what
prevents the bug from being locked down, and that belongs in the post-mortem.

With a correct seam:

1. Turn the minimised repro into a failing test there.
2. Watch it fail.
3. Apply the fix.
4. Watch it pass.
5. Re-run the Phase 1 loop against the **original, un-minimised** scenario, and against every
   example when the bug showed on a set.

**A fix that leaves the loop red has refuted its hypothesis.** Revert it, cross the hypothesis
off the Phase 3 list and take the next one. A second fix stacked on the first tests two
changes at once, and the loop can no longer say which one mattered. When the list is
exhausted, return to Phase 3 with what the refutations showed and write a new list.

Three refuted fixes on one bug is a stream of attempts. Load [[step-back]] before the fourth.

## Phase 6: cleanup and post-mortem

Before calling it done:

- The original repro no longer reproduces. Re-run the Phase 1 loop, not the minimised one.
- The regression test passes, or the absence of a seam is written down.
- Every `[DEBUG-…]` probe is gone. Grep the prefix.
- Throwaway harnesses are deleted or left in the scratchpad, never in the tree.
- The repo's lint and type gates and the affected tests pass.
- **The hypothesis that turned out correct is in the commit message**, so the next person
  diagnosing near this code starts where you finished.

Then ask what would have prevented it. If the answer is a gate the repo could have had, that is
an automated check, not a note. Make the recommendation *after* the fix is in, because you know
more now than when you started.

## When to reach for the neighbours

- **You have a fix and must judge whether it reaches the origin**, or you are about to add a
  retry, a waiver, a default or a broader catch: [[root-cause]].
- **Three fixes have left the loop red**, or the work on the loop has grown larger than the bug: [[step-back]].
- **The loop runs one of the repo's own tools**, such as its test harness, its telemetry or its
  graph checks: the skill that owns that tool carries its commands and its traps.

---

*The phase structure is adapted from [`mattpocock/skills`](https://github.com/mattpocock/skills)
(`diagnosing-bugs`), MIT-licensed. Contrast ranking comes from a study of fault localisation on
generated faults.*
