---
name: grill
description: "Interviewing me about a plan, a design or an idea until its design tree has no unvisited branch: one round of numbered questions per frontier, each with a recommended answer, every fact looked up instead of asked, and at the end the settled decisions, rejected alternatives and unresolved objections filed where the repo keeps each. Load when asked to grill, stress-test or challenge a plan, when a plan is about to be built with decisions nobody took, or after a brainstorm picked a direction. For options on a problem with no plan yet, load brainstorm."
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
once, and file the three things the summary would otherwise be the only copy of. A chat
is lost to the next reader. A file is not.

- **A settled decision** goes where the repo keeps its rules. Where the repo keeps a
  book, that is a `rule:` bullet on the concept that covers it, or a new concept when
  none does.
- **A rejected alternative** becomes a decision. Run
  `ostler decisions add <short-kebab-slug> --summary "<the question, in one line>"`. It files
  `decision.md` in a folder named by the slug under the repo's docs home, prints its path, and
  refuses a slug that is already taken. The coder's resolver files the same way, and the dev scope
  reads it before it asks. The reader is the next agent about to propose the same path. Fill the
  four headings in the printed file:

  - `## Question`: the question, as a question.
  - `## Decided`: the path taken, and the alternative it rejects, in one or two sentences.
  - `## Grounded in`: the file and line that decided it, or my answer to Q<n> of this grill.
  - `## Context`: the plan this grill stress-tested, and what was at stake.

- **An unresolved objection** is work nobody has scheduled. File it on the Register:

  ```bash
  ostler backlog add --repo <repo> --area <area> "<the objection in one line>" --body "<what settling it would take>"
  ```

A repo with no docs root yet keeps all three in the summary, and the first story that
creates the docs root files them.

Start implementing only after I confirm we have reached shared understanding. When I ask
you to start early, name the branches still unvisited first, then do as I asked. When the
work changes what a record does under an action, the step after shared understanding is the
[[behaviour-model]], and the plan comes from it.

---

*Adapted from [`mattpocock/skills`](https://github.com/mattpocock/skills) (`grilling`),
MIT-licensed.*
