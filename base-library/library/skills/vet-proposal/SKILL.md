---
name: vet-proposal
description: "Judging whether a proposed change deserves to exist, when it is already defensible on its own terms: goal-fit and design-fit asked as separate passes, a beneficiary named, and a cited constraint priced instead of treated as a veto. Load when extending a plan to reach a goal, filtering proposed improvements, deciding what an agent may add on its own, or about to reject a proposal by citing something the code already does. Reads the project's constitution and escalates a conflict it does not rank. For judging whether a fix reaches a defect's origin, load root-cause."
tags: [standards, review]
---

# Vet a proposal

Catch the change that is **defensible from inside the diff and wrong from outside it** — a
position built on the nearest citable fact, every step of it checking out, while the judgment
actually on the table was about the *product*.

## What you are vetting

The proposals are whatever is on the table to be added, kept or dropped — named in the
request, or in the plan file, the diff or the candidate list. Read them and **write out the
set** before vetting. A pass whose inputs were never stated grades whatever the previous
reasoning left lying around.

## 1. Read the constitution

`{{ template.constitution_path | default("docs/CONSTITUTION.md") }}` states what the project
is being built **toward**, who it is for, and which aim wins when two collide. It describes no
existing code, which is why it is the one input here you cannot reconstruct by reading the
repository. Read it before looking at the proposals.

With no such file, run the rest in reduced form: ask both questions in §3, and send every §5
tension to the operator, since nothing here outranks the goal. A codebase records what was
built, not what it was for, so take the aims from the operator rather than from the code.

## 2. Goal-fit, closed before §3 is opened

Per proposal, in one line: does it move the stated goal, and is it in scope?

**Scope is the half that fails.** The proposals exist *because* of the goal, so the first half
mostly confirms itself; the second catches the improvement that is genuinely good and
unrelated — which is a `drop`, and is caught nowhere else. A well-shaped change that serves a
different goal passes §3 cleanly.

Write the answer down before opening §3. Asked together, "serves the goal and fits the design"
gets answered by the half that is already true, and the design half stops rejecting anything.

## 3. Design-fit

Does this change's *shape* belong in the product? A proposal routinely passes §2 and fails
here: it reaches the goal through a surface nobody would choose. Three questions, none
answerable by asserting the change is reasonable.

**Who benefits, and who pays?** Name the beneficiary from the stakeholders the constitution
names, plus two available in every project: **the codebase's internal consistency** and **the
implementer's convenience** (yours — fewer call sites to touch). Those two are legitimate
answers and both are **findings**: each is a cost someone else absorbs. Where the beneficiary
is one of them and the payer is a person the constitution names, the proposal is reshaped or
dropped.

**If the constraint were not there, what would you propose?** Ask wherever an existing fact
was cited against a simpler or better option:

> Without that constraint, what is the proposal? And what would removing the constraint
> cost — which files, how many call sites, what breaks?

This is the load-bearing question, and the one to ask even with no constitution. A cited
constraint is a **price**, not a veto: unpriced it ends the discussion, priced it is a number
the operator can weigh. "We can't, because X" ends a conversation that "we can, for the cost
of X" would have started.

**What would a restriction remove?** The mirror of the question above, and the one that fires
wherever a proposal handles cases instead of choosing one:

> Which input could the product refuse, and how many of these cases disappear when it does?

Handling every nested path, flag combination and config shape is *handling*; requiring the
command to run from the repo root is *choosing*. Cases admitted by an open interface grow
combinatorially, and each is tested, documented and carried forever — the restriction costs one
habit, once. A constraint on a *user* is a legitimate design output, and the constitution is
what tells you whether that user can be asked.

## 4. Three verdicts

Every proposal gets exactly one:

| Verdict | When |
|---|---|
| **keep** | passes §2 and §3 as proposed |
| **reshape → `<the shape>`** | the goal is right, the form is not; name the form it should take, and the aim it moves toward |
| **drop** | it does not serve the goal, or its cost exceeds what it buys |

**Reshape is the common verdict and the reason this skill exists.** A filter that only keeps
or drops does almost nothing, because the right answer is frequently *not in the candidate
set* — it is the option talked itself out of before anything was proposed. The price question
puts that option back on the table; reshape is where it lands, and the constitution's aims are
what it aims at. Between two shapes that both pass, the one carrying an aim further wins.

Four records are the wrong shape, and go back for restatement before their merit is argued:
no beneficiary named ("this is cleaner" names no one); a constraint cited with no price;
internal consistency as the whole argument; and a **keep** that answers none of the §3
questions — approval is a judgment too, and it is the one that gets waved through.

## 5. When the goal pulls against an aim

The reshape that carries an aim further sometimes reaches the goal less directly than the
proposal as written. The goal is a local instruction you were handed; the aims are what the
project is for, so **the constitution outranks the goal**. Apply it and cite the line.

Where it is silent there is nothing to outrank with, so **stop and ask the operator**: state
the tension in two sentences, give both shapes with their price, and recommend one. Deciding it
yourself hands the goal every unranked case, and the aims then bind nothing.

## What to return

One record per proposal, in the order given:

```
<proposal>
  goal-fit:    pass | fail — <one line>
  beneficiary: <stakeholder> (paid for by <stakeholder>)
  price:       <constraint cited> costs <what changing it takes>   [omit if none cited]
  restriction: <what the product could refuse> removes <the cases>  [omit if none]
  verdict:     keep | reshape → <shape>, toward <aim> | drop
```

Then, separately, **every tension you sent to the operator** — each with its two shapes, their
price, and your recommendation.

Report the records before acting on any of them. A record produced after the plan is already
edited documents a decision instead of exposing it.
