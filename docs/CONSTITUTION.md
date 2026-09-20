# What this toolchain is being built toward

The aims stablemate is built to reach, ranked. Nothing here describes the current state of
the code, and none of it is contingent on what has been built — this file could be written
into an empty repository and would say the same thing.

Its job is to **choose**. Given two ways to do something that both work, these decide
which one this project takes. `/vet-proposal` reads it for exactly that: a proposal is
kept, reshaped toward one of these, or dropped.

Each aim carries the fork it resolves. An aim that cannot separate two real options is not
doing any work and does not belong here.

## Ranked

Lower number wins a conflict. The first obligation is to find the option that serves both,
because most conflicts are a failure of imagination rather than a real tie.

### 1. Everything it claims, it can show

What this toolchain asserts, it can be asked to demonstrate — and is asked. Evidence is
produced as the work happens, not reconstructed afterwards or taken on the word of
whatever did the work.

*Chooses:* observing the behaviour over inferring it from a clean exit; parking on missing
evidence over passing without it.

### 2. The judgment comes from somewhere the work did not

What checks the work is assembled from inputs the work did not produce. Independence lives
in the inputs, not in the good intentions of the judge.

*Chooses:* a fresh context with different inputs over a cheaper self-check; three narrower
rooms over one well-informed one.

### 3. The book is the operational reference

Toward a book true, complete, sufficient and intelligible enough that running it tests the
product, and an agent holding nothing but the book can operate the app and explain why it
behaves as it does. The four properties are in the `ostler/okf` skill.

*Chooses:* covering a capability in the book over shipping it uncovered; a check that can
tell success from failure over one that observes a clean exit; an operational answer the
book can give over one that needs the source.

### 4. Every finding gets an answer

A finding is cleared, or it is classified and carried explicitly. Nothing accumulates
unexplained, and nothing is made to stop appearing.

*Chooses:* adjudicating a stubborn finding over waiving it; parking for an operator over
narrowing the check until it passes.

### 5. What it produces belongs to the user

The artifacts are files in the user's own repository, intelligible with every stablemate
package uninstalled. What the toolchain knows, it writes down where they can read it.

*Chooses:* a plain format over a tool-owned store; a file they already know how to read
over one only we can parse.

### 6. Surfaces are chosen for the person who meets them

Every name, path, identifier and layout a person reads or types is decided deliberately,
for them, with a reason that can be stated. None of it falls out of how the code happens
to be arranged.

*Chooses:* the surface a person would pick, and pays whatever that costs behind it; a
stated reason for a form over a form that merely works.

### 7. It belongs to whoever installs it

The toolchain runs in repositories that are not this one, on stacks that are not ours,
driving whichever agent CLI the user already pays for. It works with nothing configured.

*Chooses:* the general mechanism over the one that fits here; a default that is safe
everywhere over one that is optimal here.

### 8. It runs without anyone watching, and asks well when it must

Work survives crashes, caps and days. When only a person can answer, it parks and waits
for them rather than assuming they are present.

*Chooses:* a gate over a prompt; resuming where it stopped over starting again; sleeping
until a window reopens over dying inside it.

## Who these are for

`/vet-proposal` requires a proposal's beneficiary to be named from this list:

- **the developer building software with stablemate** — reads the plan, answers the gates,
  lives with every name and surface
- **the operator of an unattended run** — the same person hours later, working out what a
  run did and why it stopped
- **the adopter in another repository** — installing into a codebase and a stack that are
  not this one

Plus two that are always available and always a finding: **the codebase's internal
consistency** and **the implementer's convenience**. Naming either is honest, not
forbidden — it says a cost has been moved onto one of the three people above.

## What this file does not rank

It does not settle 1 against 8, or 5 against 7. Those conflicts are real and unresolved
here.

That is deliberate. `/vet-proposal` escalates an unranked conflict rather than resolving
it, because a tie broken quietly is how an unstated aim gets decided by whichever agent
happened to be running. A conflict that recurs earns a ranking here — not a habit.

## Two choices this file makes

**Inline prompting, against a node id derived from the path stem.** Proposed: the prompt
written where it is used. Objected to because an existing site derives the node id from the
file's path stem. The objection was true and pointed at real code, and aim 6 still decides
against it: an identifier a person types is chosen for them, not computed from how files
are arranged, and the cost behind that surface is ours. What the objection owed was the
price of changing the resolver — a number to weigh — not a reason to stop.

**A queue that worked and looked wrong.** A view generated functional and oddly shaped,
with nothing to point at as broken. Aim 6 again, by its second clause: the form had no
stated reason, and working is not a reason for a form. Nobody wrote that down because the
work was never framed as a decision about a surface — which is what this file exists to
make unavoidable.
