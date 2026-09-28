---
name: decompose
description: "Divide a problem top-down before writing any code: state the problem in domain terms, split it into a few top-level parts, break each part into concepts with what they own and must never know, derive each pattern from a named force, and only then map the design onto the existing system. When the input is an as-built spec or a request to rebuild something, extract the problem from it first and treat its design decisions as claims to re-derive. Produces a design note and stops for approval. Load before a feature, a new step or module, a change that crosses two modules or adds a concept, or whenever asked to think top-down or design before coding. For options on a problem with no plan yet, load brainstorm first. For a repo-wide restructuring, load target-architecture instead."
argument-hint: "[the problem to decompose]"
tags: [design, planning]
---

# Decompose

Design this top-down before touching any code:

$ARGUMENTS

The existing system is the strongest anchor in the room. Read its code, or a document that
describes it, and its shape becomes the solution's shape, whether it fits the problem or
not. This skill fixes the order: the problem, then the parts, then the concepts inside each
part, then the patterns, and only then the existing system.

## The order is the rule

Sections 1 to 4 come from the problem and from facts about the domain. Section 5 is the
first place the existing system may enter.

Before section 5 you may read:

- The problem statement or the request.
- **Domain facts**: how the game, the business, the protocol or the file format works, and
  measurements about it. A domain fact stays true whatever the system looks like.

Before section 5 you may not read anything that describes the **existing solution**. That
covers source files and tests. It also covers any doc whose purpose is the current system:
architecture notes, plans, roadmaps, as-built specs, `AGENTS.md` module lists and memories
about the design. Judge a document by its purpose, not by whether a module name appears in
it. A reference about the domain, such as a file format or the game's rules, may be read
even when it names a module in passing: take the facts and ignore the names. The one
solution document you may read early is the input itself, handled as below. Instructions
already in your context count too: do not name a part or a concept after something they
list. A word the problem or the domain uses is fair even when that context uses it too.
You cannot unsee what loaded on its own. Disclose it at the top of the note and go on.
Do not restart. Any design decision it carried becomes a claim in section 1b.

If you saw the solution before this skill loaded, say so at the top of the note. Then check
each part and concept against the test "would I have named this without having seen the
solution?"

### When the input is a solution

An as-built spec, a design doc or a request like "rebuild X" hands you someone's answer.
Go through it once and sort each statement into one of three kinds: a domain fact, a
requirement, or a design decision. The facts and requirements become section 1: who it
serves, what they get, the guarantees, and the measures of done. Then list each design
decision the document takes as a **claim** in section 1b: an order of stages, an
algorithm, a data structure, a rule.
The design does not inherit a claim. Section 4 either re-derives it from a force or rejects
it, and section 5 checks it against the existing system.

## The note

Write the note to `docs/design/<slug>.md` unless the caller or the repo's `AGENTS.md` names
another home. It has these sections, in this order.

### 1. Problem

- Who feels this, and what do they experience today? One or two sentences in the domain's
  words. No module, class or file names.
- What does done look like to that person? Name something observable, with a number where
  the domain gives one.
- What is out of scope? List the neighbouring problems this note does not solve.

### 1b. Claims

When the input is a solution, or when design decisions reached you through context that
loaded on its own. One line per claim, numbered, in the source's words, with the source
named.

### 2. Parts and concepts

Work in levels. Finish level 1 before you write level 2.

**Level 1: parts.** Split the whole problem into 3 to 7 parts. A part is a large
responsibility a domain expert would recognise without seeing any code. For a compiler, the
parts are reading the source, checking its meaning and emitting the target. For each part,
state what it owns, what it never knows, and what it hands to which other part. Then write
the flow between the parts in a few lines. A part is a responsibility, not a stage. When a
part acts at more than one moment, the flow names each moment.

Test the split before going on:

- You can explain it to the user in one paragraph with no technical vocabulary.
- Two different code bases could both fit it.
- No part is named after a stage, module or step of an existing implementation.

**Level 2: concepts.** Break each part into its concepts, one table per part:

| Concept | Owns | Never knows |
|---|---|---|

- **Owns** is one responsibility. A responsibility that needs "and" is two concepts.
- **Never knows** is the boundary. It names the neighbouring concept or part whose details
  stay out.
- A concept is a noun from the domain. `Manager`, `Helper`, `Utils`, `Handler` and
  `Processor` are not concepts. They are the absence of one.
- Each concept belongs to one part. A concept two parts need is one of three things: a
  shared value type, a read-only reference every part consults such as a catalog, or a
  sign the level 1 split is wrong. Say which.
- A part with more than 7 concepts is two parts. Go back to level 1.
- Stop breaking down when a concept holds one responsibility. Go to a level 3 only inside a
  concept that still needs "and".

### 3. Invariants

Rules that stay true whatever the implementation. Each names the **one** concept that owns
it: the one that detects a breach and fails. Other concepts may uphold it during
construction, and the invariant lists them. An invariant with two owners will drift between
them. An invariant with no owner is a wish. An invariant about the finished whole
belongs to the part that can see the finished whole.

### 4. Forces and patterns

First list the **forces**: what varies, what varies independently of what, what must be
swapped in a test, what grows over time, what must stay cheap. Then pick patterns at two
altitudes, and cite the force behind each one:

- **Between parts**: how the parts connect. Examples are a sequence of stages, ports and
  adapters, one value handed along, or events.
- **Inside a part**: a pattern per concept.

Rules for both:

- No force, no pattern. A concept with no variation is a plain function or a plain value
  type, and that is the right answer more often than not.
- One pattern per force. Two patterns answering the same force is a sign one of them is
  decoration.
- [references/forces.md](references/forces.md) maps common forces to candidate patterns.
  It is a starting list, not a menu to fill.
- Each claim from section 1b is either re-derived here from a force, or listed as rejected
  with the reason.
- Open lookups go here: each is a fact you need from the existing system, and the decision
  that waits on it. A lookup may need a run or a measurement, not only a read.

### 5. Mapping onto the existing system

Now read the code and the documents that describe it. Map each part first, then each
concept inside it. Give one verdict per item:

- **Exists**: where it lives, and confirmation that its owns and never-knows match.
- **Reshape**: where it lives, and the mismatch.
- **New**: where it will live, following the repo's placement rules.

Then list what the existing system has that the design lacks. Each item is either waste or a
concept the design missed. Say which, and fix the design if it is the second.

A mismatch is a finding. Cite the file and line that shows it. Decide which side is wrong,
the design or the code, and say why. Never bend a concept to fit the file it lands in
without saying so. For each claim from section 1b, say whether the existing system follows
it and whether the design does. When the mapping shows the repo's structure is wrong beyond
this problem, park it under section 7 and point at `target-architecture`.

Resolve the open lookups from section 4 here. When a lookup or a mismatch changes a part, a
concept or a pattern, go back and change it in its own section. Do not patch the design in
section 5. Open section 5 with a short revision log instead: one line per change, naming the
section and item that changed and the finding that changed it. The changed item keeps its
earlier verdict and marks it revised, with a pointer to its log line.

### 6. Slices

Order the work as vertical slices, following `vertical-slicing`. The first slice is the
thinnest path that makes the section 1 outcome observable. Each slice names the parts and
concepts it touches and its done-when.

### 7. Open decisions

Numbered. Each gives the question, the options, your recommendation and its one-line
reason. Parked findings from section 5 go here too.

## Stop

Present the note and stop. Write no code and edit no source file until I approve it. If
plan mode is on, the note is the plan. When the caller is another agent, return the note's
path, the level 1 parts and section 7, plus anything else the caller asked for.

When I push back on a part or a concept, change its section and re-derive what hangs off
it: its concepts, its invariants, its pattern, its mapping. A change patched only into the
mapping leaves the design and the code disagreeing on paper before a line is written.

## Smells that the order slipped

- Level 1 has more than 7 parts, or a part carries the name of an existing stage or module.
- The concepts mirror the existing modules one to one.
- Section 2 names a file, a class or a function.
- A claim from section 1b shows up in the design with no force behind it.
- A pattern is justified by elegance, consistency or "future flexibility" instead of a
  force present today.
- Section 5 has no mismatch at all on a problem that crosses two modules.
- The slices are layers ("models first, then the step, then the CLI") instead of paths.
