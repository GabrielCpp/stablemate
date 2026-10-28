---
name: examine-process
description: "Judging a running or finished process that nobody asked a question about: a coder run, a book pipeline, a benchmark, any loop an agent tends from a feed. The spend of every stage is held against what a competent human would need to deliver the same thing, the process is measured against itself (stage against stage, lap against lap, unit against the median), a short list of lenses covers what spend does not show, and a fresh short-context judge is asked what would surprise the operator. Each finding collapses into a question with a yardstick, is routed to the skill that answers it, and the loop continues with the top question. Load when tending a run from a feed and about to acknowledge a notification, when a unit of work was just delivered, when asked whether a process costs too much or converges, or when a run looks normal because nothing in the prompt said otherwise. For a stream of attempts stuck on one goal, load step-back. For a question already in hand, load research-study."
tags: [review, process]
---

# Examine a process

An agent tending a process reads silence as approval. No budget in the prompt becomes an
unlimited budget. No word on duration makes any duration fine. The run looks normal because
nothing said what normal is, and three notifications in four end with "nothing needs action".

The operator never wrote the reference down because to them it is common sense: spend scales
with what is delivered, and an agent finishes faster than a person. This skill carries that
sense as two generators that produce a reference for any stage, any lap and any unit, so no
list of expectations has to foresee the case. **"Nothing wrong" is a claim.** It stands only
on readings taken against every generator and every lens below.

[[step-back]] judges a stream of attempts once a count trips. [[research-study]] answers a
question the operator wrote. This skill sits before both: it turns a process with no question
into findings, each finding into a question one of them can take, and then continues with the
top question. It changes nothing in the process it examines.

## Two tiers

A feed delivers a notification every ten to thirty minutes. A full examination at that rate
would cost more than the run, so the work splits in two:

- **On every notification**, the **reading**: one line in a fixed shape, so lines compare
  across ticks:

  ```
  <stage> · <elapsed> of <proxy hours> · <spend> of <proxy bill> · lap <n> vs lap <n-1>: <cost> / <verdict moved or not>
  ```

  That line is the acknowledgement. An acknowledgement with no numbers in it is a check
  not made. A line whose elapsed time or spend crosses half the proxy starts an examination
  at once, while a rewind or a re-scope can still save the rest of the unit.
- **On every unit delivered**, and at run end, the **examination**: steps 1 to 6 below, with
  the judge. A unit is a story through its gate, a book round closed, a benchmark task scored.

Both tiers append to one file, `EXAMINED.md`, in the run's directory beside its event log.
The run directory is the run's record, and the next examination and the fresh judge read
the previous one from there.

## The records

Work from what the process recorded, never from its code: the telemetry store, the ledger,
the turn transcripts, the checker reports, the git log of what it delivered. The code says
what the process was meant to do. The records say what it did and what that cost. For a
workhorse run the store and the commands that read it are in [[groom-telemetry]].

A process that left no record of a stage's cost has a finding before anything else is read:
the stage is unrecorded, and adding the recording is the first question the report carries.

## 1. Draw the process

Draw the whole before reading any stage, at the level of the whole. One box per stage, in
order, and for each: what comes in, what goes out, who reads the output next, and the cost
it took in wall time, tokens or money, retries, and human interventions. Take the costs from
the records, as totals and as a share of the run.

Name the **unit of delivery**: the thing the operator gets at the end, such as a story
merged, a page written, a surface documented. Every reading below is per unit, because
spend only means something against what it bought.

Done when every stage has its share of the total and the run has its count of units.

## 2. The human proxy

The agent has no fatigue and no sense of money. It has a usable estimate of what a competent
person would need. For each unit delivered, write what a competent human would have spent to
deliver the same thing: hours of work, at a day rate the operator would pay. Assume a senior
practitioner's rate for the operator's market, write the rate used at the top of the report,
and let the operator correct it once. Reason from the delivered artifact, not from the run
that produced it: the size of the change, the number of behaviours it adds, the care it
needed. Write the estimate before reading what the run spent.

Then set the run's spend for that unit beside it. Two rules follow, and neither needs a number
from the operator:

- **An agent spends less than a person.** Spend above **half** the human estimate, in hours
  or in money, is a finding. Twelve hours for one story is a finding before anyone asks.
- **Spend scales with delivery.** Across units, spend per unit tracks the proxy. A two-line fix
  that cost what a feature cost is a finding, however small both numbers look.

**The previous run is a reading, never a reference.** "The last run took two hours, so this
pace is expected" shows the process is consistent, not that it is efficient. A baseline that
sits above half the proxy is itself the first finding.

The proxy is a scale, not a verdict. It turns tokens and minutes into something the operator
feels, and the report speaks in that currency: hours of a person's time, dollars of their
money, never counts of turns or tokens.

## 3. The process against itself

A process holds its own references, and these need no scale at all:

- **Stage against stage.** The stage holding the largest share of cost is a finding by
  contrast with the others. Name it and its share.
- **Lap against the lap before.** A lap that cost what the previous lap cost and left the
  verdict where it was is waste by contrast alone. Count such laps and price them.
- **Unit against the median unit.** The unit furthest above the median spend is where the
  process broke its own pattern. Read its transcript first.
- **The slope of the progress number.** Follow the checker's count across rounds, split by
  kind. A total that falls can hide a kind that has not moved. [[step-back]] holds the
  moves for splitting it and pricing a flat group.

This is the contrast [[isolating-causes]] uses between failing and passing cases, applied to
spend. The contrast names where to look. It does not yet say why.

## 4. Lenses beyond spend

Spend misses four shapes of waste. Apply each to every stage, and write a reading for each
even when the reading is clean:

| Lens | What to look for in the records | What it indicates |
| --- | --- | --- |
| Work by hand | the same sequence of tool calls or edits repeated across turns or units | a construct the process lacks: a command, a node, a check |
| Open loop | an output no later stage and no person reads | a stage with no receiver, or a receiver that stopped reading |
| Tool failure | a call that fails and is retried, worked around or ignored | a defect in the instrument, paid for on every unit |
| Stall | a stage waiting on a gate, a lock, a person or a quota | time the process spends delivering nothing |

A candidate construct found through the first lens is a proposal, not a finding. It goes to
[[whole-first]] and [[vet-proposal]] before anyone builds it.

## 5. The fresh judge

The one who drew the process and took the readings does not grade them. Their frame
produced the readings, and it holds the same blind spots the operator's list of expectations
would have held. Hand the judgement to a reader with fresh context on every examination: a
new agent started from a written brief, never a fork of the examiner, on the cheapest model
that reasons well. Its window is short on purpose, so it holds the whole picture and nothing
of the run's history. Skipping it when the findings are few is skipping it when the blind
spot is in play.

The brief carries three things and no reasoning:

- the drawing from step 1, with the share and the unit count on every stage,
- the proxy table from step 2 and the readings from steps 3 and 4,
- one question: **what here would surprise the operator?**

The judge argues for the operator, not for the run. It returns the surprises ranked by what
the operator loses, each in hours or money, with the reading it rests on. The examiner adds
them to the findings and does not overrule them.

## 6. Collapse each finding into a question

A finding is a reading that departs from a reference, and it carries that reading. A
judgement written without the number it rests on is a guess, and so is its retraction. A
finding becomes useful only as a question someone can answer. For each one write the
question, the done-condition, and the yardstick that will show the done-condition met, then
route it:

- a number to move, such as a stage's share or a unit's spend → [[research-study]], which
  takes the question and the yardstick as its steps 2 and 3,
- an effect with a cause to find, such as a tool failure or an outlier unit → [[isolating-causes]],
- a stream of laps that moved nothing → [[step-back]],
- a construct the process lacks → [[whole-first]], then [[vet-proposal]].

The examination changes nothing in the process. A fix done inside it is a finding nobody
vetted.

## 7. Continue with the top question

Write the report first. Then take the top question into the skill it was routed to, one
question at a time, and leave the rest in the report for the next examination. A loop that
stops at a report every cycle is a report generator, and the operator reads the report when
they come back, not while it is written.

The loop stops taking up questions on a price test: when the top finding's price, in hours
or money per unit, is below what answering it would cost. The reading tier keeps running,
the verdict reads efficient, and the operator is told so once.

## 8. Re-examine after a change

Once a routed question was acted on, run steps 1 to 4 again and set every stage beside the
previous report, not only the stage the change aimed at. Name what the change took from the
other stages, with each stage's share before and after. A fix graded on its own target alone
is the siloed idea [[whole-first]] warns about. The re-examination's findings join the next
report in the usual way.

## The report

The report fits one screen. Open with the day rate assumed. Lead with the finding that costs the operator the most, as one
sentence in hours or money a person understands without knowing the run. Then at most five
findings, costliest first, each with its reading, its reference, its routed question and the
skill it goes to.

Then the **null report**: one line per generator and per lens, saying what was checked and
what it read. A line the examiner cannot fill is a check not made. A report that says the
process is fine and carries no readings has examined nothing.

Close with one verdict for the process: **efficient**, **wasteful**, **stalled** or
**unrecorded**, and the single question to answer first.

## Completion criterion

Each line checkable from the report alone:

- Every notification since the last examination got a reading line in the fixed shape, and
  every line is in `EXAMINED.md`.
- Every stage carries its share of the cost and the unit of delivery is named.
- Every unit has a human proxy written before its spend was read, and the two stand side by
  side, with the rate assumed stated.
- The largest stage, the repeated laps and the outlier unit are named with their price.
- Every lens has a reading for every stage, clean readings included.
- A fresh judge returned its surprises, and they are in the findings.
- Every finding carries its reading and is a question with a done-condition, a yardstick and
  a destination skill.
- The process was left as it was found, and the top question was taken up or the price test
  says why not.
