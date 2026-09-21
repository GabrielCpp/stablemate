---
name: stablemate-vet-proposal
description: "Judging whether a proposed change deserves to exist, when it is already defensible on its own terms: goal-fit and design-fit asked as separate passes, a beneficiary named, a new carrier traced back to the variable it stands for, and a cited constraint priced instead of treated as a veto. Load when extending a plan to reach a goal, filtering proposed improvements, deciding what an agent may add on its own, about to reject a proposal by citing something the code already does, or about to add a flag, field, key, kind or state to a format. Reads the project's constitution if it has one, and escalates a conflict it does not rank. For judging whether a fix reaches a defect's origin, load root-cause."
metadata:
  generated_by: farrier
  source: library/skills/vet-proposal/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-vet-proposal/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
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

**Take the situation as evidence, not as analysis.** Whoever hands you a blocked item has
been reading code, and what they summarise will be in the code's vocabulary. Ask for three
things pasted verbatim: the item's identifier, the item as it currently stands, and whatever
reported it blocked. Their account of what it means is the thing under review, not the input
to reviewing it.

**What arrives here.** Adding a fact to an existing structure is content and does not need
this skill. Adding a *carrier* — a flag, field, key, kind, state, enum member or new type —
is shape, and shape comes here first. A carrier is how a format acquires the thing nobody can
read two months later.

## 1. Read the constitution, if there is one

`docs/CONSTITUTION.md` is where a project may
state what it is being built **toward**, who it is for, and how to settle two options that
both work. It describes no existing code, which is why it is the one input here you cannot
reconstruct by reading the repository. Read it before looking at the proposals.

Projects write these differently, so take the file's structure from the file. Two kinds of
statement turn up, and they behave differently under conflict:

- a statement that **ranks** yields to one the file places above it;
- a statement that **admits** names a property something must have, and does not yield at
  all. It refuses, or it is satisfied.

Which kind a given statement is comes from its own wording. Most files contain only the first
kind, and where a file does not distinguish them, treat every statement as ranking.

With no such file, run the rest in reduced form: ask the questions in §3, and send every §6
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
here: it reaches the goal through a surface nobody would choose. Four questions, none
answerable by asserting the change is reasonable.

**Who benefits, and who pays?** Name the beneficiary from the stakeholders the constitution
names, or from the people this product has if it names none, plus two available in every
project: **the codebase's internal consistency** and **the implementer's convenience**
(yours — fewer call sites to touch). Those two are legitimate answers and both are
**findings**: each is a cost someone else absorbs. Where the beneficiary is one of them and
the payer is a person the product serves, the proposal is reshaped or dropped.

**What is the carrier standing for?** Fires on every proposal that adds a flag, field, key,
kind, state or enum member. Answer three things before judging the carrier at all:

> Which variable does it stand for? How many values does that variable have? At what level
> does it vary — per item, per file, per run?

A carrier that holds fewer values than the variable has is the wrong carrier, and no amount
of repairing it makes it right: a boolean holds two. A carrier sitting above the level the
variable varies at forces duplication; below it, repetition. Name the variable and its level
and stop there. That is the whole finding, and the fix follows from it.

The tell that this question was skipped is a proposal that reads as a list of repairs to
something that already exists. The length of that list is proportional to the wrong carrier's
accidental complexity, not to the problem.

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

## 4. What a citation owes

A proposal that cites a rule in its own favour makes two claims, and the second goes
unchecked.

**A rule is cited with its condition.** Read the rule's own wording and ask whether this case
meets it. A rule permitting a pause *when only a person can answer* has not permitted pausing
on every occasion, and a proposal reaching for it there is borrowing authority the words do
not extend.

**A proposal invoking a property must satisfy it.** Moving toward a property is not having it.
Where a proposal cites a stated property its current state violates, check the *proposed*
state against that same property before crediting it. A property saying a value never reaches
some component is not satisfied by a change that merely makes the value harder to reach,
however much better the new path is.

Both failures survive §2 and §3 untouched, because the reasoning is sound everywhere except
at the citation.

## 5. Four verdicts

Every proposal gets exactly one:

| Verdict | When |
|---|---|
| **keep** | passes §2, §3 and §4 as proposed |
| **reshape → `<the shape>`** | the goal is right, the form is not; name the form it should take, and what it moves toward |
| **drop** | it does not serve the goal, or its cost exceeds what it buys |
| **escalate** | two statements collide and the file does not settle them; §6 |

**Reshape is the common verdict and the reason this skill exists.** A filter that only keeps
or drops does almost nothing, because the right answer is frequently *not in the candidate
set* — it is the option talked itself out of before anything was proposed. The price question
puts that option back on the table, and reshape is where it lands. Between two shapes that
both pass, the one carrying a stated aim further wins.

Five records are the wrong shape, and go back for restatement before their merit is argued:
no beneficiary named ("this is cleaner" names no one); a constraint cited with no price;
internal consistency as the whole argument; a new carrier with no variable named behind it;
and a **keep** that answers none of the §3 questions — approval is a judgment too, and it is
the one that gets waved through.

## 6. When the goal pulls against the constitution

The reshape that carries a stated aim further sometimes reaches the goal less directly than
the proposal as written. The goal is a local instruction you were handed; the constitution is
what the project is for, so **it outranks the goal**. Apply it and cite the line.

Where it is silent there is nothing to outrank with, so **escalate**: state the tension in two
sentences, give both shapes with their price, and recommend one. Deciding it yourself hands
the goal every unranked case, and the constitution then binds nothing.

A ranking statement against an admitting one is always this case. Neither kind outranks the
other, so a collision between them is a finding about one of the two, not a trade to make
here.

## What to return

One record per proposal, in the order given:

```
<proposal>
  goal-fit:    pass | fail — <one line>
  beneficiary: <stakeholder> (paid for by <stakeholder>)
  carrier:     <the variable> has <n> values, varies per <level>   [omit if none added]
  price:       <constraint cited> costs <what changing it takes>   [omit if none cited]
  restriction: <what the product could refuse> removes <the cases>  [omit if none]
  verdict:     keep | reshape → <shape> | drop | escalate
```

Then, separately, **every tension you escalated** — each with its two shapes, their price, and
your recommendation.

Report the records before acting on any of them. A record produced after the plan is already
edited documents a decision instead of exposing it.
