---
name: step-back
description: "Judging whether a stream of attempts is going anywhere, from outside it: the attempts treated as a reference class instead of the next case to fix, three moves (test the lever, go wide not deep, split the progress number), the side each stuck failure sits on, and a read-only reviewer with fresh context that recommends and does no work. Load when the same kind of attempt has been made three times on one goal, when a progress number falls slower each round, when a long or unattended run is being tended, when about to report nearly done again, or when a gate asks whether to keep going. For finding a defect once the stuck subset is named, load diagnosing-bugs. For judging the fix, load root-cause."
tags: [review, process]
---

# Step back

[[diagnosing-bugs]] finds a defect from a symptom. [[root-cause]] judges a fix. This skill judges
the **stream**: whether the attempts so far are moving the goal, and which question to ask next.
It fires on a count, not a topic. Three attempts of the same kind on the same goal is the trigger,
whatever the attempts were.

Each attempt is reasoned from the case in front of it: this failure, this edit, this retry. That
is the inside view, and every step of it checks out. It cannot see that the last five attempts
looked exactly like this one and moved nothing. The outside view treats your own attempts as a
**reference class**: what happened to the attempts like this one, and what does that predict for
the next?

## Who steps back

Not the one who made the attempts. Their context is the frame that produced them, and a review
that inherits it reproduces it. Hand the review to a reader with **fresh context**: a new agent
started from a written brief, never a fork or a continuation of the worker. A person who has not
followed the work counts too.

The reviewer is **read-only**. It reads the records, forms a view and recommends. It edits
nothing, answers no gate, restarts nothing and messages no one. Doing the work would put it back
inside the frame it was brought in to leave.

The brief names the goal, where the records are, what an attempt is, and the questions below. It
does not carry the worker's theory of what is wrong. A reviewer handed a theory checks the theory.

Run it on a slow schedule while the work is long, and at once when the trigger fires. Act on its
top finding before the next review. A finding that stands across two reviews is the finding.

## Move 1: test the lever

For each recent attempt, ask: **did it change what gets measured?**

The measurement is the input the judge reads: the request sent, the command run, the value
compared, the file the check opens. An attempt that edits something the measurement never reads
cannot move it, however good the edit.

Compare the measured input before and after the attempt, not the artifact that was edited. Two
attempts that changed the artifact and left the measured input byte-identical are a dead lever.
Every further attempt on that lever is waste, and so is every attempt that only rewords it.

## Move 2: go wide, not deep

Put every open failure side by side and group them by **the observation itself**: the status,
the error text, the missing field, the exception type. Do not group by where the failure was
reported, such as the file, the page, the test or the owner. That grouping is the one the
attempts already used, one case at a time.

- **One observation, many owners.** A group that spans many owners has one cause that none of
  them holds. Repairing each owner is the dead lever of move 1, run in parallel.
- **The largest group first.** Rank the groups by size. The top group is worth more than the
  rest of the list together, more often than not.
- **Read the group's members together.** What do they share that the passing cases lack? That
  contrast is the hypothesis to hand to [[diagnosing-bugs]].

## Move 3: split the progress number

A total that falls each round reads as convergence. Split it by the groups from move 2 and follow
each group across the last few rounds. A falling total can hide a group that has not moved at
all. The flat group is where the time goes.

Price it: the rounds the flat group has survived, times the time each round takes. The price is
what keeping going costs, and it goes in the report as time, not as a count.

Ask also whether the falling part is falling slower each round. A curve that halves its gain each
round has an end in sight. One that loses a constant amount is a backlog with a known finish.
Neither is the same as a flat group, and the report says which it is.

## Which side

Every stuck group sits on one side of the work:

- **the work itself**: the artifact the attempts edit;
- **the instrument**: what turns the work into a measurement, such as a compiler, a test harness
  or a checker;
- **the subject**: the system the measurement runs against;
- **the environment**: the machine, network, data and credentials around the subject.

A group whose cause sits on any side but the first cannot be fixed by attempts on the first. Name
the side from evidence: an observation the side would produce and the others would not. A side
named because it is where the attempts were going is the inside view again.

## The attendant

Whoever tends the work is part of what is reviewed. Ask where their time went over the review
window, and set that against where the waste is. Name what they kept doing that moved nothing,
and what they never looked at. A tender who answers every gate with "keep going" has delegated
the step back to nobody.

## The report

Lead with the one finding that costs the most time, in a sentence a person would understand
without knowing the code. Then at most five findings, most costly first, each with:

- what is happening;
- the evidence: which streams, which groups, the counts, the times;
- the side it is on;
- the one action recommended.

End with one verdict per stream of work: **converging**, **slow** or **stuck**. Keep the report
under one screen. Form the view first, then read the previous report and say which of its
findings still stand and whether anyone acted on them.

## Completion criterion

Each line checkable from the report alone:

- The reviewer had fresh context and changed nothing.
- Every recent attempt was tested against the measured input, and dead levers are named.
- Failures were grouped by observation, and the groups are ranked by size.
- The progress number was split by group across rounds, and each flat group carries its price
  in time.
- Each stuck group names its side, with the observation that places it there.
- The attendant's time was set against the waste.
- Each stream has a verdict, and the top finding has one action.

A review that lists failures one by one has not stepped back. It is one more attempt, written
down.
