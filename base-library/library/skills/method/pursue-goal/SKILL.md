---
name: pursue-goal
description: "Load when handed a goal to pursue without the operator, when told to make a process better, faster, cheaper or more reliable, to 'reassess until we land on' something, or to show 'where I sit compared to my goal', when a track just closed and the next step is unclear, or when a goal directory is resumed. Pursues a goal that is an aspiration and not a figure, as a loop: the problem and the operator's own use cases kept in their words and reread at every reading, its dimensions inferred and put to the operator in priority order before any run, the record already paid for read first, one cause question from the dominant loss, tracks worked one at a time under a spending ceiling, then the goal judged again on the operator's benchmark across every dimension. For the cause of one effect, load isolating-causes; for a mechanism that does not exist yet, load explore-then-improve; for waste in one that does, load self-improve."
argument-hint: "[the problem and the use cases, in the operator's words]"
tags: [process]
---

# Pursue a goal

An agent handed a goal picks the one thing in it that it can count, drives that figure to a
bar, and stops. The figure clears while the person who set the goal is still exposed on
every side the figure never measured. This loop keeps the person in view. It owns the goal,
the dimensions the goal has, the reading of what the process already recorded, and the
judgement after each change. Everything in between it hands to the skill that does that work,
with the dimensions in hand.

The loop works in a directory per goal, `.goal/<slug>/`, under the directory the operator
keeps for such records and outside any tracked tree: `GOAL.md` holds steps 1 and 2 and
every reading of step 7, `PROFILE.md` holds step 3, `TRACKS.md` holds steps 5 and 6, and
`TRIED.md` holds one plain-words line per track or fix that ended, with its result, why, and
what read the result: the measure and the cases it was read on.
A resumed goal starts by reading all four. Nothing paid runs before step 6: every reading
up to there comes from the record.

## 1. The problem and the use cases, in the operator's words

Copy the operator's problem statement into `GOAL.md` word for word, with the benchmark they
named, the record they pointed at, and every figure they gave. Rewrite nothing. A restated
problem is what the loop then pursues, and the restatement is the agent's, not the operator's.

Under it, copy the operator's use cases: numbered, each one a concrete situation they want to
work and what they expect to see when it does, in their words. The use cases are the
operator's acceptance of the goal, and the readings of step 7 are written against them. An
operator who gave a one-line goal and no use cases is asked for them once, with a drafted
list as the recommendation. Until they answer, the loop runs on the draft, marked as the
agent's, and the operator's list replaces it the moment it arrives. A use case the operator
adds later is appended with its date, and the next reading covers it.

Done when `GOAL.md` quotes the operator's problem, holds their numbered use cases, and names
the benchmark and the record.

## 2. The dimensions

A goal fails in more than one way, and each way is felt by someone. For every way the goal
can fail, write who feels it, what they lose, whether the loss can be bought back afterwards,
and with what. Then order the list:

- A loss nothing buys back comes first. It is never traded for anything below it.
- A loss that money or time buys back comes next, and the currency that buys it is thereby
  a tradeable, not an objective.
- A figure the operator gave, a budget or a deadline, is a **ceiling**. A quality the
  operator asked of a currency, cheaper or faster than today, is a dimension of its own,
  and it stays a tradeable: it is bought with spend under the ceiling, and it buys nothing
  above it.

Then look for the dimension nobody named: what the process reads to do its work. Ask what
every stage takes as its input and who produces that input, the process's own state and its
checkpoints included. The quality of that input sits under every loss above it, and it is a
dimension of its own.

The order is the agent's inference, and the operator's words stay as written in step 1.
Write the list to the operator once, in its order, with the order as the recommendation, and
continue on that order while they are away. Their answer, when it comes, reorders the list,
and the loop goes on from the reordered list. A list with one entry means the person was
lost; go back to who feels it before continuing.

Done when `GOAL.md` holds the ordered list, each entry with who feels it and what trades
against it, and the list has been sent to the operator.

## 3. Read the record

Before anything runs, read what the process already recorded: its runs, its transcripts, its
benchmark results and the diffs it delivered. For each dimension, write where its loss shows,
by stage and by producer, with the record cited: a diff, a report, a lap count, a transcript,
a bill. A transcript says where the process was misled or stalled, and a bill says only that
it cost, so the transcripts come first. A record too large to read is scanned by a script
that counts what each dimension shows and names the visits to read, and the reading cites
those visits.

Done when `PROFILE.md` names, for every dimension, where its loss shows and the record that
shows it, and the dominant loss is named in one line.

## 4. The cause question

From the dominant loss, write one question in plain words: why does this happen. Hand it to
isolating-causes with the record as its cases. Its answer is a cause, or a split between
producers that says which of them the loss comes from. A split is an answer: it decides
which fixes exist. A confirmation that needs a new run is a track for step 5, and the
answer stands as the split until that track runs.

Done when `PROFILE.md` holds the question and its answer, each hypothesis with the cases
for and against it from the record.

## 5. Tracks

Hand the question, the profile and the dimension list to brainstorm, and ask for the tracks
that would answer it. Each track gets the cheapest check that confirms or kills it, from the
record where the record can. A check that splits a cause between producers goes ahead of any
fix, because it decides which fixes are worth running. A reading the operator alone can
supply, such as what their own way of working costs, goes to the operator and not into a
track.

Done when `TRACKS.md` holds the ranked tracks, each with its check and the dimension it
protects.

## 6. Work one track

Take the top track. Run its check. A track that dies gets its `TRIED.md` line and the next
track starts. A track that lives is worked by the skill that does its kind of work: a
mechanism that does not exist yet is explore-then-improve, waste in a mechanism that exists
is self-improve, and a fix is judged by root-cause before it lands. Each of them takes the
dimension list in place of a bar. Spend sits under the ceiling, and a spend above the
operator's standing authorization goes to the operator with the figure and a recommendation,
with the work that does not depend on the answer done.

One track is in hand at a time. A second one started before the first was read answers for
neither.

Done when the track's `TRIED.md` line is written, with the result, why, and the measure and
cases that read it.

## 7. Measure again

Run the operator's benchmark, or read its last run when a fresh one is forbidden. A benchmark
with no task that reads the goal gets that task as the next track before any other. Judge
the goal across every dimension with the evidence cited: the diff and the report for what
was shipped, the lap count and the wall for how late, the transcripts for where the process
was misled, the bill for the ceiling. A count appears only where a dimension counts. A track
that cleared its own check has moved nothing until this reading says so.

Then reread the use cases of step 1 and write one line per use case: works, works in part,
or not yet, each with the evidence that shows it and, for one not yet met, what stands in its
way. This is the progress the operator reads when they come back, so it is written for them
and in their vocabulary, and a use case nothing in the loop has touched says so instead of
being left out.

Done when `GOAL.md` holds the reading, one line per use case and one line per dimension, each
with its evidence, and one line saying where the goal stands.

## 8. Again

Rewrite the dimensions and the profile with what the reading taught. Then reread `TRIED.md`.
A line is as dead as the measure that killed it. When the cause answer or the measure has
changed since a line was written, a line whose verdict rested on the old one returns to
`TRACKS.md` with a check on the new one. Return to step 4.
The loop ends when the operator says the goal is met, never when a track clears. Before a
session or a tranche ends, write where the goal stands in one line, so the next session
starts from the reading and not from the last track.

## Completion criterion

Each line checkable from the directory alone:

- `GOAL.md` quotes the operator's problem and their numbered use cases, holds the ordered
  dimensions with who feels each, and holds a reading per loop with one line per use case and
  one per dimension.
- `PROFILE.md` cites the record for every dimension and holds the cause question with its
  answer.
- `TRACKS.md` ranks every track by the dimension it protects, each with its check.
- `TRIED.md` has a line for every track or fix that ended, in words a reader outside the
  project follows, each naming the measure and the cases that read its result.
- No spend went above the ceiling, and every spend above the standing authorization carries
  the operator's answer.
