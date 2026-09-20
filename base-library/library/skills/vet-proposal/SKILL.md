---
name: vet-proposal
description: "Judging whether a proposed change deserves to exist, when it is already defensible on its own terms: the two passes kept apart (does it reach the goal, and is its shape one the project is aiming for), the beneficiary named from a closed list, the counterfactual price that turns a cited constraint from a veto into a number, the three verdicts with reshape as the common one and the project's aims as what it reshapes toward, and the records refused on their form before their merit. Load when extending a plan to reach a goal, filtering proposed improvements, deciding what an agent may add on its own, or about to reject a proposal by citing something the code already does. Reads the project's constitution and escalates a conflict it does not rank. For judging whether a fix reaches a defect's origin, load root-cause."
argument-hint: "[the proposals to vet, or a path to them]"
tags: [standards, review]
---

# Vet a proposal

[[root-cause]] judges a **fix** — whether it reaches the origin or handles the symptom.
This skill judges whether a **change deserves to exist at all**, and it fires on a
different action: extending a plan, filtering improvements, or citing an existing fact
against a simpler option.

The failure it catches is a change that is **defensible from inside the diff and wrong
from outside it**. An agent extending a plan reaches for the nearest citable fact and builds a position
on it: one
call site, one naming convention, one thing the code already does. That, without having registered that a judgment about the *product* was on the table. The
argument is locally true and globally wrong, and it persuades precisely because every
step of it checks out.

Nothing here asks you to have taste. It asks two questions whose answers you do not
author, and refuses records that are the wrong shape before anyone argues their merit.

## What you are vetting

$ARGUMENTS

If that names nothing, the proposals are whatever is currently on the table to be added,
kept or dropped. Establish them **explicitly before vetting** — read the plan file, the
diff, or the candidate list — and write out the set you are judging. A vetting pass whose
inputs were never stated grades whatever the previous reasoning left lying around, which
is the same contamination this skill exists to break.

## 1. Read the constitution

`{{ template.constitution_path | default("docs/CONSTITUTION.md") }}` states what this
project is being built **toward**, who it is for, and which aim wins when two collide. It
describes no existing code, which is what makes it the one input here you cannot
reconstruct by reading the repository. Read it now, **before** looking at the proposals.

**If that file does not exist**, this skill still runs, in reduced form: do §2, ask the
price question in §3, and escalate every tie to the operator instead of resolving it. Do
not infer the aims from the codebase. A codebase records what was built, not what it was
for, and inferring one from the other is the failure this skill exists to catch.

## 2. Pass A — goal-fit

For each proposal: does it move the stated goal, and is it in scope?

Expect nearly everything to pass. The proposals were generated *because* of the goal, so
this pass mostly confirms the obvious. Its job is to be finished and out
of the way, so that §3 is asked separately.

**Do not merge pass A into pass B.** Asked together, "does this serve the goal and fit the
design" is answered by the half that is already true, and the design half stops rejecting
anything.

## 3. Pass B — design-fit

Does this change's *shape* belong in the product? A proposal routinely passes §2 and
fails here: it reaches the goal through a surface nobody would choose.

Two questions per proposal. Neither is answerable by asserting that the change is reasonable.

### Who benefits, and who pays?

Name the beneficiary from the stakeholders the constitution names, plus these two, available in every project:

- **the codebase's internal consistency**
- **the implementer's convenience** (yours: fewer call sites to touch, less to rewrite)

Both are legitimate answers and both are **findings**. Neither is a reason to ship a shape; each is a cost someone else absorbs. Where the beneficiary is one of them and the payer is a person the constitution names, the proposal is reshaped or dropped.

### If the constraint were not there, what would you propose?

Ask this wherever an existing fact was cited against a simpler or better option:

> Without that constraint, what is the proposal? And what would removing the constraint
> cost — which files, how many call sites, what breaks?

This is the load-bearing question, and the one to ask even with no constitution.

A cited constraint is a **price**, not a veto. Left unpriced it ends the discussion; once
priced it is a number that can be weighed against what the better shape is worth, and the
weighing is the operator's to do. An agent reporting "we can't, because X" has ended a
conversation that "we can, for the cost of X" would have started.

## 4. Three verdicts

Every proposal gets exactly one:

| Verdict | When |
|---|---|
| **keep** | passes both passes as proposed |
| **reshape → `<the shape>`** | the goal is right, the form is not; name the form it should take, and the aim it moves toward |
| **drop** | it does not serve the goal, or its cost exceeds what it buys |

**Reshape is the common verdict and the reason this skill exists.** A filter that only
keeps or drops does almost nothing, because the right answer is frequently *not in the
candidate set* — it is the option talked itself out of before anything was proposed. The
price question in §3 is what puts that option back on the table; reshape is where it
lands.

Reshape needs somewhere to aim, and the constitution is it. Its aims describe what the
project is reaching for rather than what it already is, so they can name a direction a
proposal does not yet have — and "this moves toward none of them" is itself a verdict.
Between two shapes that both pass, the one carrying an aim further wins.

## 5. Records refused on their shape

Check the form before arguing the merit. These are refused as written and returned for
restatement rather than debated:

- **No beneficiary named.** "This is cleaner" / "this is more consistent" identifies no
  one. Name a stakeholder or withdraw.
- **A constraint cited with no price.** An objection resting on an existing fact carries
  what changing that fact would cost, or it is inadmissible.
- **Internal consistency as the whole argument.** A real cost, never a complete reason.
  What does a person get for it?
- **A keep verdict with no answer to either §3 question.** Approval is a judgment too, and
  it is the one that gets waved through.

## 6. When the two passes conflict

They will: the proposal that best reaches the goal is sometimes the one with the worse
shape. Resolve in this order.

1. **The constitution decides**, if it ranks the two aims in play. Cite the line you are
   applying.
2. **If it is silent, stop and ask the operator.** State the conflict in two sentences,
   give both options with their §3 price, and recommend one. Do not resolve a tie the
   project has not ranked — resolving it silently is how an unranked aim gets decided by
   whichever agent happened to be running.

A tie broken toward the goal by default is not a neutral outcome. The goal is the thing
you were handed, so it wins every unranked conflict, and the aims never bind
anything.

## What to return

One record per proposal, in the order given:

```
<proposal>
  goal-fit:    pass | fail — <one line>
  beneficiary: <stakeholder> (paid for by <stakeholder>)
  price:       <constraint cited> costs <what changing it takes>   [omit if none cited]
  verdict:     keep | reshape → <shape>, toward <aim> | drop
```

Then, separately, **the conflicts you did not resolve** — each with its two options and
your recommendation.

Report the records before acting on any of them. This skill makes the reasoning legible
so a human can reject it; a record produced after the plan is already edited documents a
decision instead of exposing it.
