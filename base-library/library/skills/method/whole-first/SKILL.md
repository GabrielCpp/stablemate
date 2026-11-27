---
name: whole-first
description: "Load before designing a product, milestone, story or screen, when an idea falls into a trap or silo ('nobody writes it today' as the reason, a fix that stops at one piece), or when proposing an unasked improvement."
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
against the person it serves or the whole it joins. Each step of the argument checks out, so
rereading the argument finds nothing. The questions below need answers the local evidence
cannot supply.

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

## 1. Who is the person, and what is their moment?

Picture the person before the idea. The **moment** is the situation they are in when they reach
for the product: what just happened, what they need next, and what else is pulling at them.
The project's purpose may already name them. The purpose is what the project wrote about what
it is for and where it is heading. [[vet-proposal]] says where to find it and how its
statements rank. Read it first.

Write the **frame** when the purpose is silent about the person, or when the request is new: a
product, a milestone, a screen nobody has described.

Dig to the **root need** first. Take the request and ask why the person wants it. Ask why again
of the answer, and keep asking until the next answer leaves what the product can touch, or
repeats a line the purpose already states. It takes three to five rounds. Each link names a
person and a moment, and carries a source tag like a frame line. An answer that names a
quality, such as faster or easier, has not answered why, so ask it again. An answer that
names money or growth has left the product's reach, so step back one link. The last link
inside the product's reach is the root need. Write one chain for each person in Who, because
the one who uses it and the one who pays rarely want it for the same reason.

A bakery's request to take orders online might run: phone orders tie up the counter at the
morning rush, so walk-in customers wait, so regulars leave before they are served. The root
need is a counter that serves the person in front of it. Online ordering is one link, and a
pickup shelf for orders placed the day before sits on the same chain.

The frame grows from the chain. It has five lines:

- **Who.** Every person who meets it, kept apart from the person who asked: the one who uses
  it, the one who receives what it makes, and the one who pays to run it. Their role, and how
  much they carry: teams, tools, records, volume.
- **Moment.** What happens just before they reach for it, how often, on which device, with how
  much time, and who is watching.
- **Today.** What they do now without it, and what that costs them.
- **Done.** What they know or have finished when they leave.
- **Refuses.** What makes them give up on it: setup, a wait, data they doubt, a lost edit.

Done is the root need as the person sees it. Today is how they reach it now. Refuses is
what would break their trust in it. A frame line that traces to no link of the chain
describes another product, so cut it or ask about it.

The frame speaks in the person's words and names no feature or screen. Each line carries its
source: *stated* (the request or the purpose says it), *inferred* (it follows from a stated
line, named), or *guess*. Each line names the design choice it settles. Cut a line that settles
none.

Then walk the moment as a **scenario**. One concrete person, a time of day and a real task, in
six to ten lines from the way in to the way out. Include the moment they are interrupted and
the moment something fails. Run it on the person's real data, never on sample data: the
largest record, the oldest one the tool they use today left behind, one in another language or
format, and one that tool left half finished. Every fact the scenario needs and the frame lacks
is a guess, and joins the frame.

Walk it a second time at the **screen**: the size of the window and what sits beside it, where
the eye and the keyboard focus are after each action, what moves when something changes, and
where each message appears. A design that holds at the task and fails at the screen fails the
person.

**Play it back** to the requester before the design. The chain goes first, because every
other line rests on it. A root need the requester did not state is always a question. A guess
becomes a question, with your recommended answer, when its answers fork the product: two
answers, two different designs.
Every other guess becomes a working assumption, stated in one line. The answered frame and the
scenario land where the purpose lives, the product page or the milestone, so the next reader
finds the person beside the purpose.

Then hold the idea against the frame. Name the person, and what they experience with the idea
and without it, and cite the line of the purpose or the frame that makes it matter. An idea
with no person behind it is dropped, however cheap it is. Cheapness is how such ideas pile up.
An idea whose person is real but whose need neither the purpose nor the frame names goes to
the owner of the purpose as a question. Nobody builds it on a guess.

An improvement found while doing other work is the same case. Name its person and its line
before it takes time from the work it was found in. If it names neither, record it and leave
it.

## 2. Where does it sit in the whole?

Draw the whole before designing the piece. The whole is whatever the piece joins:

- in a product, the journeys a person takes through it, from the way in to the way out, and
  the work around it: the tool, meeting or task they come from and go back to,
- in a format or a language, every kind of item it has, including kinds with no example today,
- in a running system, every receiver of what the change moves, measured before the change.

Keep the drawing at the level of the whole. A page of a product is one box. A rule of a format
is one row. Draw it from the project's own description of itself where one exists, and from the
frame's scenario where none does. Then place the piece in it and answer four things:

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

The brief carries four things:

- the project's purpose, quoted, including where it is heading,
- the frame and the scenario as the requester answered them,
- the drawing of the whole from question 2, or the project's own description of itself,
- the idea as it would ship: the design, the mockup, the rule or the built result.

It carries none of the reasoning, the measurements or the history behind the idea. A judge
handed the argument checks the argument. For something a person perceives, such as a screen,
the judge looks at the rendered result. The code does not show what a person sees.

The judge walks the scenario through the idea, at the task and at the screen, and answers
question 2's four things from the drawing. It traces every journey to a link of the chain. A
journey that serves no link and a link no journey serves are both misses. A guarantee the design states is a claim to walk
with the scenario's real data, never a fact to credit. The judge argues for the people in the
frame, not for the idea. It returns keep, reshape or drop for each idea, with the person and the line each
verdict rests on. The designer does not overrule it. A disagreement goes to the owner of the
purpose as one question, with both shapes and their cost.

## Order

The frame and its playback come first, before any design. Question 2 comes before the design.
Question 3 comes after the design and before anything is built. Asked after building, each
question meets a cost already spent, and that cost argues for keeping the idea.

## Smells

- An idea's reason is a file, a count, a passing check or a tool's reach.
- The person is "the user", with no role, moment or volume.
- The chain ends on a quality or on money, or the frame has a line the chain never reached.
- The frame names a feature, or every line in it is stated.
- The scenario has no time of day, no interruption and no failure.
- The scenario runs on sample data, or never reaches the screen.
- A rule, a page or a step was designed for the one case that showed the need.
- A piece works on its own, and nobody can say where a person comes from or goes next.
- A change states only its own target as done.
- The designer graded the design.
- A follow-up nobody asked for runs before the work it was found in.
