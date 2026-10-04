# What this toolchain is being built toward

stablemate is tooling for long-running agentic loops. Agent work that runs for days
with nobody watching, and has to survive everything that happens in between. Every aim
below is downstream of that, and an aim that would be obviously right for a tool a
person sits in front of is often wrong here.

Two kinds of statement live here, and they work differently.

The **aims** rank. Given two ways to do something that both work, they decide which one
this project takes. They describe no code and could be written into an empty repository.

The **product bars** admit. Each package states one property its output must have, and
that property is what rejects an addition to it. Unlike the aims, they name things that
exist.

`/vet-proposal` reads both. A proposal is kept, reshaped toward one of these, or dropped.

An aim that cannot separate two real options is not doing any work. A bar that cannot
reject anything is a purpose wearing a bar's clothes. Neither belongs here.

## The aims, ranked

Lower number wins. The order is a default and not a proof: the first obligation is to find
the option that serves both aims, because most conflicts are a failure of imagination
rather than a real tie. Where the order is asserted but not trusted, it is named at the
bottom, and `/vet-proposal` escalates those instead of reading the number.

### 1. Everything it claims, it can show

What this toolchain asserts, it can be asked to demonstrate, and is asked. Evidence is
produced as the work happens. It is not reconstructed afterwards, and not taken on the
word of whatever did the work.

*Chooses:* observing the behaviour over inferring it from a clean exit. Parking on missing
evidence over passing without it.

### 2. The judgment comes from somewhere the work did not

What checks the work is assembled from inputs the work did not produce. Independence lives
in the inputs, not in the good intentions of the judge.

*Chooses:* a fresh context with different inputs over a cheaper self-check. Three narrower
rooms over one well-informed one.

### 3. Every capability is covered in the book

A capability that ships uncovered is a capability nobody can operate from the book, and
the book is this toolchain's operational reference. Ostler's bar below says what covered
means.

*Chooses:* covering a capability in the book over shipping it uncovered. A check that can
tell success from failure over one that observes a clean exit. An operational answer the
book can give over one that needs the source.

### 4. Every finding gets an answer

A finding is cleared, or it is classified and carried explicitly. Nothing accumulates
unexplained, and nothing is made to stop appearing.

*Chooses:* adjudicating a stubborn finding over waiving it. Parking for an operator over
narrowing the check until it passes.

### 5. What it produces belongs to the user

The artifacts are files in the user's own repository, intelligible with every stablemate
package uninstalled. What the toolchain knows, it writes down where they can read it.

*Chooses:* a plain format over a tool-owned store. A file they already know how to read
over one only we can parse.

### 6. Surfaces are chosen for the person who meets them

Every name, path, identifier and layout a person reads or types is decided deliberately,
for them, with a reason that can be stated. None of it falls out of how the code happens
to be arranged. Working is not a reason for a form.

*Chooses:* the surface a person would pick, and pays whatever that costs behind it. A
stated reason for a form over a form that merely works.

### 7. It belongs to whoever installs it

The toolchain runs in repositories that are not this one, on stacks that are not ours,
driving whichever agent CLI the user already pays for. It works with nothing configured.

*Chooses:* the general mechanism over the one that fits here. A default that is safe
everywhere over one that is optimal here.

### 8. It runs without anyone watching, and asks upward when it must

Work survives crashes, caps and days. Attendance is a pyramid. A node does one narrow
task, and a blocked node asks the level above it. That level is an agent before it is a
person. Each level reasons about what the level below could not see, then sends the fix
down as a narrower task than its own. A person stands at the top and is asked only what
only a person can answer, such as a secret's value or what the product should do. It
parks and waits for them rather than assuming they are present.

*Chooses:* asking the attendant over parking for a person. Diagnosing before dispatching
over fixing in place. A gate over a prompt. Resuming where it stopped over starting
again. Sleeping until a window reopens over dying inside it.

The level above is a seat inside the run, and it is the widest one. It sees everything
the level below produced at once: every failure of a lap, the logs, and what the
toolchain sent. It keeps its findings from one lap to the next. It may name a cause
outside the work it supervises, such as the toolchain, a fixture or the environment. It
reads the evidence before the first repair is dispatched. The narrow nodes below it do
the bulk labor. The state machine holds only what must not bend: the gates, the
evidence, the budget and the checkpoint. The widest seat gets the strongest model the
user has, and the narrow seats may run on a cheaper one.

*Also chooses:* one seat that sees the whole lap over a rule that sees one check.
Naming the cause before the first repair over inferring it from repairs that failed.

### 9. A workflow records a process that already worked

A state machine encodes a guess about the shape of a problem. The guess is only safe
once the problem has been solved. A process is automated after an attended session has
finished it at least twice on a real target of the intended size. The transcripts of
those sessions are the workflow's specification. They name its seats, what each seat
must see, and what each may touch.

*Chooses:* finishing the task attended over automating it first. A node added because a
session needed that step over a node added because the design predicted it. Shrinking
the target until an attended session finishes over growing the machinery around a run
that does not.

## The product bars

One per package. This file is where they are read side by side, which is how a package
with no usable bar becomes visible.

**core** is the shared foundation every product builds on.
*Bar:* it depends on nothing else in the workspace.
*Rejects:* anything two products happen to share. Needing a sibling is what disqualifies
it, so the name stops being a position and starts being a constraint.

**base-library** ships the skills and policies stablemate comes with.
*Bar:* a fresh clone works with nothing added, and every shipped policy is either right
for anyone or overridable without forking.
*Rejects:* a lesson from one repository promoted to shared policy. That is our preferences
wearing a library's name, and the user who disagrees has no move.

**farrier** installs skills, prompts, instruction files and hooks across repositories.
*Bar:* the agent environment reproduces. A second clone gets the same one.
*Rejects:* configuration that works only on the machine it was authored on. Nothing there
looks wrong on that machine, which is why it needs a bar and not attention.

**saddlebag** stores secrets and fills them in at the target, across every environment
from local to a production agent account.
*Bar:* the agent never sees the value.
*Rejects:* every path where a secret becomes readable by the agent. A debug print, an
error message, a log line, a retry that echoes the request.

**workhorse** is the toolbox for building autonomous workflows that survive week-long
uninterrupted work.
*Bar:* a run survives error, network flakiness and interruption, and the primitives stay
elegant enough to build on.
*Rejects:* a change that makes a run faster by making it more fragile. Robustness outranks
throughput whenever the two trade.

**workflows** is the out-of-the-box development workflow: story authoring, dev, review, QA.
*Bar:* it executes daily development work without supervision.
*Rejects:* a fix that requires a person to notice something. If the recovery depends on
someone watching, the workflow has not recovered. It also rejects a workflow, or a new
stage of one, for a process no attended session has finished (aim 9).

**ostler** organises documentation across a repository and manages the okf books.
*Bar:* a book true, complete, sufficient and intelligible enough that running it tests the
product, and an agent holding nothing but the book can operate the app and explain why it
behaves as it does. The four properties are defined in the `ostler-okf` skill.
*Rejects:* buying one property with another. Completeness bought by adding a flag nobody
can read costs intelligibility, and the book has not moved forward.

**groom** is the dashboard a person supervises the flow of work from, and the telemetry
store an agent diagnoses bottlenecks out of. One real-time store, two renderings.
*Bar:* everything the dashboard shows is answerable from the store afterwards.
*Rejects:* a value the view computes and does not persist. That is precisely the one the
diagnosing agent cannot get back.

**paddock** is the testing ground for replaying a workflow, or a section of one, to measure
time and accuracy.
*Bar:* a replay reproduces the original run.
*Rejects:* a simplified replay that returns a faster number. That is a different run, so
the number measures nothing.

## Who these are for

`/vet-proposal` requires a proposal's beneficiary to be named from this list:

- **the developer building software with stablemate**, who reads the plan, answers the
  gates, and lives with every name and surface
- **the operator of an unattended run**, the same person hours later, working out what a
  run did and why it stopped
- **the adopter in another repository**, installing into a codebase and a stack that are
  not this one

Plus two that are always available and always a finding: **the codebase's internal
consistency** and **the implementer's convenience**. Naming either is honest, not
forbidden. It says a cost has been moved onto one of the three people above.

## What this file does not rank

It does not settle 1 against 8, or 5 against 7. Those conflicts are real and unresolved
here.

That is deliberate. `/vet-proposal` escalates an unranked conflict rather than resolving
it, because a tie broken quietly is how an unstated aim gets decided by whichever agent
happened to be running. A conflict that recurs earns a ranking here, and a habit does not.

Nothing ranks an aim against a product bar. An aim that a bar contradicts is a finding
about one of them, not a trade to make on the spot.

## One choice this file makes

**Inline prompting, against a node id derived from the path stem.** Proposed: the prompt
written where it is used. Objected to because an existing site derives the node id from
the file's path stem. The objection was true and pointed at real code, and aim 6 still
decides against it. An identifier a person types is chosen for them, not computed from how
files are arranged, and the cost behind that surface is ours. What the objection owed was
the price of changing the resolver, a number to weigh. Not a reason to stop.
