---
name: whole-first
description: "Screening an idea against the whole it joins before building it: the false good idea that no person needs, and the siloed idea that is right but stops at the piece where it was found. Three questions in a fixed order (who needs it and which line of the purpose says so, where it sits in a whole drawn before the piece, who judges it from outside), and five reasons that never count: a count of today's instances, an artifact that exists, the mechanism at hand, a check that passes, the builder's convenience. Load when designing a story, a screen, a mockup, a feature or a rule that joins a larger product or format, when proposing a follow-up or an improvement nobody asked for, when an idea's reason is something found in the repository, or when a piece works on its own and nobody has traced how it connects. For vetting a format carrier in detail, load vet-proposal. For a change's design end to end, load decompose."
tags: [standards, review, process]
---

# Whole first

An idea can fail in two ways that every local check passes.

- **The false good idea.** It works, and nobody the product serves needs it. Its reason points
  at an artifact or an internal property. Files of some format exist, so the idea ports them. A
  value could overflow in theory, so the idea guards it.
- **The siloed idea.** It is right, and it stops at the edge of the piece where it was found. A
  rule covers the one kind that showed the gap. A page works and no other page links to it. A
  change meets its target and moves something nobody measured.

Both come from one move. The idea rests on the nearest fact in view, and nobody holds it
against the whole it joins. Each step of the argument checks out, so rereading the argument
finds nothing. The questions below need answers the local evidence cannot supply.

## Five reasons that never count

An idea's reason is often one of these. None of them names a person, and none of them answers
the questions below:

1. **A count of today's instances.** "Only one case uses it." Today's items show what was
   built, not what the purpose asks for.
2. **An artifact that exists.** A file, a table, a format or old code found in the repository.
   Its presence says something was made once. It does not say anyone needs it now.
3. **The mechanism at hand.** What the chosen tool can or cannot reach. A mechanism delivers a
   need. It does not define one.
4. **A check that passes.** A green check shows the property it tests. A property nobody tests
   can break with every check green.
5. **The builder's convenience or the code's consistency.** Both are real costs. Neither is a
   person the product serves.

Such a fact can be evidence once the idea has a reason. It is never the reason.

## 1. Who needs it, and which line of the purpose says so?

Name the person, and what they experience with the idea and without it. Then cite the line of
the project's purpose that makes their experience matter. The purpose is what the project wrote
about what it is for and where it is heading. Read it before reading the idea. [[vet-proposal]]
says where to find it and how its statements rank.

An idea with no person behind it is dropped, however cheap it is. Cheapness is how such ideas
pile up. An idea whose person is real but whose need the purpose does not mention goes to the
owner of the purpose as a question. Nobody builds it on a guess.

An improvement found while doing other work is the same case. Name its person and its line
before it takes time from the work it was found in. If it names neither, record it and leave
it.

## 2. Where does it sit in the whole?

Draw the whole before designing the piece. The whole is whatever the piece joins:

- in a product, the journeys a person takes through it, from the way in to the way out,
- in a format or a language, every kind of item it has, including kinds with no example today,
- in a running system, every receiver of what the change moves, measured before the change.

Keep the drawing at the level of the whole. A page of a product is one box. A rule of a format
is one row. Draw it from the project's own description of itself where one exists, and from the
person's account where none does. Then place the piece in it and answer four things:

- **What comes in.** Where a person or an input arrives from. A piece nothing reaches is an
  open loop.
- **What goes out.** Who or what uses the piece's output next. An output nobody reads is an
  open loop.
- **What else it reaches.** For a rule, every kind where its reason holds. An exclusion cites
  the purpose, never one of the five reasons above.
- **What it takes away.** Every receiver whose share moves, with its value before and after.
  [[decompose]] keeps these as rows that every slice re-measures.

A piece that answers all four from the drawing is designed. A piece that answers them only from
inside its own boundary is not.

## 3. Who judges it?

The one who built the idea does not judge it. The argument that produced it answers every
question asked inside its frame, questions 1 and 2 included. Hand the judgement to a reader with
fresh context: a new agent started from a written brief, never a fork of the designer. A person
who has not followed the work counts too.

The brief carries three things:

- the project's purpose, quoted, including where it is heading,
- the drawing of the whole from question 2, or the project's own description of itself,
- the idea as it would ship: the design, the mockup, the rule or the built result.

It carries none of the reasoning, the measurements or the history behind the idea. A judge
handed the argument checks the argument. For something a person perceives, such as a screen,
the judge looks at the rendered result. The code does not show what a person sees.

The judge argues for the people the purpose names, not for the idea. It returns keep, reshape
or drop for each idea, with the person and the line each verdict rests on. The designer does
not overrule it. A disagreement goes to the owner of the purpose as one question, with both
shapes and their cost.

## Order

Questions 1 and 2 come before the design. Question 3 comes after the design and before
anything is built. Asked after building, each question meets a cost already spent, and that
cost argues for keeping the idea.

## Smells

- An idea's reason is a file, a count, a passing check or a tool's reach.
- A rule, a page or a step was designed for the one case that showed the need.
- A piece works on its own, and nobody can say where a person comes from or goes next.
- A change states only its own target as done.
- The designer graded the design.
- A follow-up nobody asked for runs before the work it was found in.
