---
name: brainstorm
description: "Generating a wide field of distinct options for a problem before any of them is judged: ground in what the repository already holds, diverge by changing the axis instead of refining one idea, then converge to a ranked shortlist of 3 to 6 with each option's main tradeoff. Load when a problem has no plan yet, when the first idea is about to become the plan, when asked for options, alternatives or ideas, or when another skill needs a field of candidates. For stress-testing a plan that already exists, load grill."
argument-hint: "[the problem, question or space to generate options for]"
tags: [brainstorm]
---

# Brainstorm

Generate options for this, and settle none of them:

$ARGUMENTS

[[grill]] narrows a plan that exists. This skill widens a space that has no plan yet.
Nothing here is a decision until I pick one.

## Ground before diverging

Before generating anything, look at what the repo already knows. An option that already
exists is not an idea, and neither is one a written constraint rules out.

- **Prior art in the tree.** Existing skills, commands, modules or docs that cover part of
  this space. Search for them.
- **A model of the domain, where the repo keeps one.** A knowledge graph, an index or a
  glossary. What the domain already models is not a fresh idea.
- **The record of what was tried, where one exists.** An option that repeats a failed
  attempt says what changed since.
- **The repo's own rules.** `AGENTS.md` and the skills that apply to the area. A written
  constraint narrows the space. Note it, and generate nothing it rules out.

Do this yourself. A fact you can look up is not a question for me.

## Diverge

Produce as many **distinct** options as the problem supports. A rewording or a small
variation of one idea is the same option. The first two or three are what anyone would
think of first. They are the floor. Go past them by changing the axis: a different
mechanism, a different scope, a different owner of the complexity, or the opposite of the
obvious default. Refining one idea twice adds nothing to the field.

Hold judgement until the converge step. Judging while generating settles on the obvious
option, because it arrives with its argument already attached.

Name each option in a line or two, and develop none yet. A bad or half-broken option
belongs in the list when it shows a part of the space the others miss. The converge step
cuts it.

## Converge

Group the near-duplicates. Drop each option another one beats on every axis. Present a
**ranked shortlist of 3 to 6**:

```
**<option name>**: <one line on what it is>
   <one line on the main tradeoff, and who or what it suits>
```

Rank by fit to the stated problem. Familiarity earns no rank, so the obvious option goes
first only when it fits best.

Then stop and wait. I pick one, ask for two to be developed further, or send you back to
diverge from a direction that looked promising. A pick starts a decision. Hand the chosen
option to [[grill]] to work out its shape.

When another skill or an unattended agent called this one, nobody is there to pick. Return
the shortlist and the full list to the caller, and let the caller continue by its own
rules.

## Done

The session ends when I pick a direction or say stop. Divergence has no natural end, so
nothing else ends it. A brainstorm answers "what could this be". Confirm with me before
building a chosen option.
