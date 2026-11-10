---
name: explore-then-improve
description: "Finding a mechanism for a goal when no stage of the current process is the problem: a field of framings and candidate mechanisms, each gated on paper against the goal's dimensions and against construction before any build; the survivor built as a prototype, the thinnest end-to-end run that does the job once; the prototype judged against every dimension the caller handed over, its cost per stage measured or assumed; a candidate that dies on paper or in build written to TRIED.md with its reason. Load when a goal has no mechanism yet, when a profile has no dominant problem or its top items sit at their roof, when a prototype has to be built, or when the same stage has been fixed three times and the goal stands. For removing waste from a mechanism that already works, load self-improve."
argument-hint: "[the goal, and the dimensions a mechanism must serve]"
tags: [research, process]
---

# Explore, then improve

The caller hands over a goal in the operator's words, its dimensions in priority order, its
`TRIED.md` and the spend left under the ceiling. This skill hands back one of two things: a
**prototype** that did the job once, judged against every dimension, or the sentence that
every surviving framing died, each for its own reason. The choice of mechanism is settled
here by searching a field of readings of the goal, never by fixing a stage: a stage is fixed
in [[self-improve]], and the caller arrives here because no stage was the problem.

The search is paperwork, and it is held to one sentence: it earns its time by killing a
candidate more cheaply than a run would. When a short run on things that exist today would
read the fact a card is arguing about, run it and cite the reading. A second checker round
on the same cards with no new fact between them says the search has stalled.

Every run this skill pays for, a short run that reads a fact or the prototype's own run, is
preceded by one question: which record already paid for answers it. A record that answers is
cited, not re-run. One that does not is named as missing, and the run's cost is written
before it starts.

Every death line this skill writes to `TRIED.md` names what read the result: the gate, or the
run with its measure and its cases. A line already there is as dead as what read it. A
candidate killed by a measure, or on cases, that the caller has since replaced returns to the
field.

## 1. Frame the goal

A **framing** is a reading of the goal: what the thing under study does, on which input, to
produce which output, judged how, and what the goal's key verb means. It names no mechanism
and no file. Write at least three, each built from its own choice on every open axis, by the
four moves in [references/framings.md](references/framings.md): restate the goal by analogy
from distant fields, list the axes as fixed or open, draw rows that differ on at least half
of the open axes, and write each row in isolation. Merge two framings that share input,
output and role. Record them in `FRAMINGS.md` in the caller's working directory, in plain
words, each with its status.

Done when `FRAMINGS.md` holds three or more framings that differ on half the open axes, each
with its status and the premise it reads from.

## 2. Map the field

Read `TRIED.md` and the project's own history first, then load [[brainstorm]] and generate
before judging. Give every surviving framing at least three candidates, at least ten in all
that differ in mechanism and not in size, at least three absent from `TRIED.md`, at least
two borrowed from another discipline, and one expected to fail with a sentence on why it
might not. The field always holds two controls: the current process unchanged, and the
strongest way of doing the job with no mechanism at all, so a candidate's gain is read
against both. For each candidate write its expected gain tied to a dimension or to a line of
the profile, its cost to test, and the result that would kill it. Write the field into
`FIELD.md`, ordered by the dimension each candidate protects, then by expected gain over cost
to test.

Done when `FIELD.md` meets every count above and each candidate carries its gain, its cost
to test and its kill result.

## 3. Gate each candidate on paper

Before any build, write the candidate's card and pass it through the two gates in
[references/paper-gates.md](references/paper-gates.md). Gate 1 asks whether it answers the
goal as posed: input, output, role, every premise, and an input that exists in use. Gate 2
asks whether it can succeed by construction when everything uncertain goes its way. A
candidate that fails gate 1 leaves the field with the mismatch as its reason. One that fails
gate 2 is repaired on paper or leaves, recorded in `TRIED.md` as "did not work (on paper)".

A second agent that did not write the cards checks them, under "The checker" in the same
file. A finding it raises stays open until a repair answers it in writing or the framing
dies.

Done when every card in `FIELD.md` carries both gate verdicts and the checker's findings,
each finding answered or the candidate gone.

## 4. Pick the survivor

The candidate at the top of `FIELD.md` that passed both gates is the mechanism to build. Its
cost to test is its **cap**: what this skill may spend building and running its prototype
before the candidate dies. A framing dies only on a framing-level reason: a candidate's death
kills the candidate. The next search after a death starts from a framing that is not a
neighbour of the one that just failed.

Done when one candidate is marked in hand in `FIELD.md` with its cap in money and hours.

## 5. Build the prototype

A **prototype** is the thinnest end-to-end run of the mechanism that does the job once:
every stage the mechanism needs, each present in the thinnest form that produces what the
next stage reads, on the smallest input the goal accepts. Nothing the first-ranked dimension
reads is faked. Everything else is a stub, a fixed input or a hand step, and each one is
written down as a stage the judgement will have to price. Time and money are not judged
here: a prototype that takes an hour where the goal wants a minute has still done the job,
and whether its ideal path fits is the judgement of step 6.

Build the stages in the order the unit flows through them, and run the whole path at each
addition, so the first thing that exists is a path and not a stage. A stage that cannot be
made to produce what the next one reads inside the cap is the candidate's death: write the
`TRIED.md` line as "did not work (built)" with the stage and what it produced instead, and
return to step 4. A hand step is allowed in a prototype and forbidden in the mechanism, so
every hand step is named as the stage that would replace it.

Done when one run of the prototype did the job on a real unit, its record holds the input,
the commit and what came out, and every stub, fixed input and hand step is listed.

## 6. Judge the mechanism

Hold the prototype against every dimension the caller handed over, in order, with the
evidence from its run cited: what it shipped, how long it took, where it stalled or was
misled, what it cost. A dimension nothing buys back that the prototype failed is the
candidate's death, whatever the others show.

Where a dimension is time or money, draw the mechanism's **ideal path**: one pass per stage,
in order, with no retry, no hand step and no dead time, each stage with its cost per unit.
Label every term **measured**, with the run that read it, or **assumed**, with its source: a
rate card, a vendor's figure, a similar stage's record, or the cost of the stage that
replaces a hand step. An assumed term with no source is a guess, and the record says so. A
stub or a fixed input is a stage whose cost the prototype did not pay, so its term is
assumed. A hand step is priced as the stage that replaces it, never at zero.

Done when every dimension has its line with evidence, and every stage of the ideal path has a
labelled term with its run or source.

## 7. Hand back

Hand the judgement to the caller, who decides whether this mechanism is the one to converge
on. A mechanism the caller keeps goes to [[self-improve]], which removes what it wastes
beyond its ideal path. A mechanism the caller rejects names the dimension that sank it: write
the `TRIED.md` line with that dimension, mark the candidate dead in `FIELD.md`, and return to
step 4 with the next survivor. A mechanism rejected on an assumed term alone may be re-judged
once, when a short run can measure that term for less than a tenth of the cap left.

The goal has no mechanism only when every surviving framing has died, each for its own
reason, and that sentence, with the reasons, goes back to the caller.

Done when the caller holds the judgement, or `TRIED.md` carries a death line per framing and
the caller holds the negative.
