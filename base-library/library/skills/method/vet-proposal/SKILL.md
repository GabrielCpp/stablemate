---
name: vet-proposal
description: "Judging whether a proposed change deserves to exist, when it is already defensible on its own terms: goal-fit and design-fit asked as separate passes, a beneficiary named, a new carrier traced back to the variable it stands for, and a cited constraint priced instead of treated as a veto. Load when extending a plan to reach a goal, filtering proposed improvements, deciding what an agent may add on its own, about to reject a proposal by citing something the code already does, or about to add a flag, field, key, kind or state to a format. Reads the project's constitution if it has one, and escalates a conflict it does not rank. For judging whether a fix reaches a defect's origin, load root-cause."
tags: [standards, review]
---

# Vet a proposal

Catch the change that is **defensible from inside the diff and wrong from outside it**. Such a
change is built on the nearest fact someone could cite, and every step of its argument checks
out. The judgement on the table was about the *product*, and the argument never reached it.

## What you are vetting

The proposals are whatever is on the table to be added, kept or dropped. The request names
them, or the plan file, the diff or the candidate list does. Read them and **write out the
set** before vetting. A pass with no stated inputs grades whatever the previous reasoning left
lying around.

**Take the situation as evidence, not as analysis.** Whoever hands you a blocked item has been
reading code, so their summary is in the code's vocabulary. Ask for three things pasted
verbatim: the item's identifier, the item as it stands now, and whatever reported it blocked.
Their account of what it means is the thing under review. It is not an input to the review.

**What arrives here.** Adding a fact to an existing structure is content, and content does not
need this skill. Adding a *carrier* is shape, and shape comes here first. A carrier is a flag,
field, key, kind, state, enum member or new type. A carrier is how a format acquires the thing
nobody can read two months later.

## 1. Read the constitution, if there is one

`{{ template.constitution_path | default("docs/CONSTITUTION.md") }}` is where a project may
state what it is being built **toward**, who it is for, and how to settle two options that
both work. It describes no existing code. That makes it the one input here you cannot
reconstruct by reading the repository. Read it before looking at the proposals.

Projects write these files differently, so take the file's structure from the file. Two kinds
of statement turn up, and they behave differently under conflict:

- A statement that **ranks** yields to one the file places above it.
- A statement that **admits** names a property something must have. It does not yield. It
  refuses, or it is satisfied.

The wording of a statement says which kind it is. Most files hold only the first kind. Where a
file does not tell the two apart, treat every statement as ranking.

With no such file, run the rest in reduced form. Ask the questions of section 3, and send
every tension of section 6 to the operator, since nothing here outranks the goal. A codebase
records what was built and says nothing of what it was for. Take the aims from the operator.

## 2. Goal-fit, closed before section 3 opens

Answer per proposal, in one line: does it move the stated goal, and is it in scope?

**Scope is the half that fails.** The proposals exist *because* of the goal, so the first half
mostly confirms itself. The second half catches the improvement that is good and unrelated.
That improvement is a `drop`, and nothing else in this skill catches it. A well-shaped change
that serves a different goal passes section 3 cleanly.

Write the answer down before opening section 3. Asked together, "serves the goal and fits the
design" gets answered by the half that is already true. The design half then stops rejecting
anything.

## 3. Design-fit

Does the *shape* of this change belong in the product? A proposal often passes section 2 and
fails here, because it reaches the goal through a surface nobody would choose. Ask four
questions. Asserting that the change is reasonable answers none of them.

### Who benefits, and who pays?

Name the beneficiary. Take it from the stakeholders the constitution names, or from the people
this product has when it names none. Two more beneficiaries exist in every project: **the
codebase's internal consistency** and **the implementer's convenience**. The second one is
yours: fewer call sites to touch. Both are legitimate answers, and both are **findings**,
because each is a cost someone else absorbs. When the beneficiary is one of the two and the
payer is a person the product serves, reshape the proposal or drop it.

### What is the carrier standing for?

This question fires on every proposal that adds a flag, field, key, kind, state or enum
member. Answer three things before judging the carrier at all:

> Which variable does it stand for? How many values does that variable have? At what level
> does it vary: per item, per file, per run?

A carrier that holds fewer values than the variable has is the wrong carrier. A boolean holds
two, and no repair makes it hold a third. A carrier above the level the variable varies at
forces duplication. A carrier below that level forces repetition. Name the variable and its
level, and stop there. That is the whole finding, and the fix follows from it.

A proposal that reads as a list of repairs to something that already exists skipped this
question. The length of that list measures the accidental complexity of the wrong carrier. It
does not measure the problem.

### If the constraint were not there, what would you propose?

Ask this wherever someone cited an existing fact against a simpler or better option:

> Without that constraint, what is the proposal? And what would removing the constraint
> cost: which files, how many call sites, what breaks?

This is the load-bearing question. Ask it even with no constitution. A cited constraint is a
**price**, not a veto. Unpriced, it ends the discussion. Priced, it is a number the operator
can weigh. "We can't, because X" ends a conversation that "we can, for the cost of X" would
have started.

### What would a restriction remove?

This question mirrors the one above. It fires wherever a proposal handles cases instead of
choosing one:

> Which input could the product refuse, and how many of these cases disappear when it does?

Handling every nested path, every flag combination and every config shape is *handling*.
Requiring the command to run from one known place is *choosing*. The cases an open interface
admits multiply with each other, and someone tests, documents and carries each one for good.
The restriction costs one habit, once. A constraint on a *user* is a legitimate design output.
The constitution tells you whether that user can be asked.

## 4. What a citation owes

A proposal that cites a rule in its own favour makes two claims, and the second one goes
unchecked.

**A rule is cited with its condition.** Read the rule's own wording, and ask whether this case
meets it. A rule that permits a pause *when only a person can answer* does not permit a pause
on every occasion. A proposal that reaches for it there borrows authority the words do not
extend.

**A proposal that invokes a property must satisfy it.** Moving toward a property is not having
it. Where a proposal cites a stated property that the current state violates, check the
*proposed* state against that same property before crediting the proposal. Take a property
that says a value never reaches some component. A change that makes the value harder to reach
does not satisfy it, however much better the new path is.

Both failures pass sections 2 and 3 untouched, because the reasoning is sound everywhere
except at the citation.

## 5. Four verdicts

Every proposal gets exactly one:

| Verdict | When |
|---|---|
| **keep** | It passes sections 2, 3 and 4 as proposed. |
| **reshape → `<the shape>`** | The goal is right and the form is wrong. Name the form it should take, and what that form moves toward. |
| **drop** | It does not serve the goal, or it costs more than it buys. |
| **escalate** | Two statements collide and the file does not settle them. See section 6. |

**Reshape is the common verdict, and the reason this skill exists.** A filter that only keeps
or drops does almost nothing, because the right answer is often *not in the candidate set*. It
is the option someone argued themselves out of before anything was proposed. The price
question puts that option back on the table, and reshape is where it lands. Between two shapes
that both pass, the one that carries a stated aim further wins.

Five kinds of record are malformed. Send each back for restatement before arguing its merit:

- a record that names no beneficiary ("this is cleaner" names no one),
- a constraint cited with no price,
- internal consistency as the whole argument,
- a new carrier with no variable named behind it,
- a **keep** that answers none of the section 3 questions. Approval is a judgement too, and it
  is the one that gets waved through.

## 6. When the goal pulls against the constitution

The reshape that carries a stated aim further sometimes reaches the goal less directly than
the proposal as written. The goal is a local instruction someone handed you. The constitution
is what the project is for, so **it outranks the goal**. Apply it and cite the line.

Where the constitution is silent, nothing outranks the goal, so **escalate**. State the
tension in two sentences, give both shapes with their price, and recommend one. Deciding it
yourself hands the goal every unranked case, and the constitution then binds nothing.

A ranking statement against an admitting one is always this case. Neither kind outranks the
other. A collision between them is a finding about one of the two statements. It is not a
trade to make here.

## What to return

One record per proposal, in the order given:

```
<proposal>
  goal-fit:    pass | fail: <one line>
  beneficiary: <stakeholder> (paid for by <stakeholder>)
  carrier:     <the variable> has <n> values, varies per <level>   [omit if none added]
  price:       <constraint cited> costs <what changing it takes>   [omit if none cited]
  restriction: <what the product could refuse> removes <the cases>  [omit if none]
  verdict:     keep | reshape → <shape> | drop | escalate
```

Then list, separately, **every tension you escalated**, each with its two shapes, their price
and your recommendation.

Report the records before acting on any of them. A record written after the plan is edited
documents a decision. It no longer exposes one.
