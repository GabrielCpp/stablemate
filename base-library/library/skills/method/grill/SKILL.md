---
name: grill
description: "Interviewing me about a plan, a design or an idea until its design tree has no unvisited branch: one round of numbered questions per frontier, each with a recommended answer, and every fact looked up instead of asked. Load when asked to grill, stress-test or challenge a plan, when a plan is about to be built with decisions nobody took, or after a brainstorm picked a direction. For options on a problem with no plan yet, load brainstorm."
argument-hint: "[the plan, decision or idea to stress-test]"
tags: [grill]
---

# Grill

Stress-test this until we share one understanding of it. Having enough to start is not the
bar:

$ARGUMENTS

Map it as a **design tree**: every decision branches into the decisions that hang off it. A
decision nobody has taken is a branch nobody has visited. It gets taken later, by you, at implementation time, and nobody notices it was a decision.

## Work the tree in rounds

The **frontier** is every decision whose prerequisites are settled. Those are the questions answerable **now**, with no guess at an answer you have not heard yet.

Ask the **whole frontier in one round**, numbered, each with your recommended answer:

```
❓ **Q1. <question title>**: <the question, and the options when there are distinct ones>

➡️ <your recommendation, and the one-line reason for it>
```

Then stop and wait. Each round of answers reshapes the tree. Settled decisions push the
frontier outward and unblock the questions that depended on them. Recompute the frontier
and ask the next round.

A question whose answer depends on another question still open **in this round** belongs to a *later* round. Asking it now forces a guess at the prerequisite, and the guess is
invisible in the answer you get back.

## Facts are your job, decisions are mine

**Look up every fact yourself.** A frontier question that needs a fact from the environment is a lookup: what the code already does, which command exists, what a config says, how the tree does the same thing elsewhere. Read the file. Run the command. Search the tree.

A running lookup is an unsettled prerequisite. Only the questions downstream of it wait.
Ask the rest of the frontier now, and fold the finding into the next round.

The **decisions** are mine. Put each one to me and wait for the answer.

## Seed the frontier from what is already written down

Before the first round, read what the repo already knows, so I do not recite it:

- **A model of the domain, where the repo keeps one.** A knowledge graph, an index or a
  spec. An entry that exists is a settled decision. A stub, a dangling link or an entry
  nothing reaches is a **frontier item** someone left open.
- **The planning record, where the repo keeps one.** An item no piece of planned work
  covers is a branch already identified and not yet taken.
- **The repo's own rules.** `AGENTS.md`, the skills that apply to the area, and the gates
  the repo runs. A written constraint is not a question. A decision that would break one
  *is* a question, and you raise it as one.

## Done

The session ends when the **frontier is empty**: every branch visited, nothing left
silently assumed. Then summarise the settled tree in one pass, so I see the whole shape at
once.

Start implementing only after I confirm we have reached shared understanding. When I ask
you to start early, name the branches still unvisited first, then do as I asked.

---

*Adapted from [`mattpocock/skills`](https://github.com/mattpocock/skills) (`grilling`),
MIT-licensed.*
