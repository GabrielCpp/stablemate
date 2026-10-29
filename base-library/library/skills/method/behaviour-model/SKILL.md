---
name: behaviour-model
description: "Writing the behaviour model of a unit of work before its plan: one file beside the description that names every record the work touches, every action that reaches one, and a state × action matrix whose every cell is a next state with its observable effects, a refusal, a no-op or an impossibility, so the condition no fixture arranges becomes a cell the plan cannot skip. The model is the source of the checks that judge the build, written by an author who did not write the plan, and an empty or unnamed cell is a finding. Load after the questions about a description are settled and before its plan is written, when a build passed its tests and still violated the intent somewhere nobody looked, when deriving the checks or the fixtures that judge a build, or when asked what a thing does in every situation. For the questions themselves, load grill; for the design the model constrains, load decompose."
tags: [planning, testing]
---

# The behaviour model

A builder is handed a description of what to make and a plan for making it. The plan says what
will be built and how. Nothing says what the thing does in every situation: what each action
does to each record in each state, what an observer sees afterwards, what survives a restart,
what happens when two callers race. The builder fills those gaps with whatever its work happens
to do. The result runs without an error and violates the intent somewhere nobody looked. The
tests written afterwards share the builder's blind spot, because the same reading of the
description produced both.

The **model** is the file that closes the gaps before the plan exists. It holds, for every
record the work touches, what each action does to it in each state and what is observable
afterwards. Every cell is decided or marked open with its question. The plan is derived from it.
The checks that judge the build are derived from it. A cell is a scenario the plan cannot skip.

This is a method, not a process. It holds for an agent building a slice of a product, a person
implementing a spec, a team migrating a schema, a writer documenting a surface. Each process
that adopts it maps the model onto its own record of behaviour and its own checker. This skill
owes the shape and the vocabulary's slots; the process names the words.

## Where it sits

After the questions about the description are settled, which is where [[grill]] ends, and
before the plan. A design written with [[decompose]] names the concepts and what each must
never know; the model names what each concept does when acted on. Write the design first when
the work adds a concept, the model first when the work changes what existing records do, and
let each correct the other.

The model is not a test matrix. It is a description of the thing being built. Test cases are
one thing derived from it. The plan is another. A rendered diagram is a third.

## The file

One markdown file per unit of work, `model.md`, beside the description it models. Three readers:
the builder, the author of the yardstick that judges the build, and whatever checker the
process has. So every line is a fact a cell can hold or an observation a check can spell. Prose
is for the collapse rules only. Five sections, each derived from the one above it.

### Records

One block per record the work touches. Its states, how a read tells them apart, whether it is
durable, its identity rule.

```markdown
## Record: link
- states: active, expired, disabled
- told apart by: GET /links/{code} → $.state
- durable: yes
- identity: code, unique across all links, generated
```

A record with no "told apart by" line has states nobody can observe, and a state nobody can
observe is a cell nobody can check. Find the read, or merge the states.

### Actions

One block per thing a user or caller can do. The surface that reaches it, its inputs partitioned
into equivalence classes, its actor. An action with no surface is a gap in the model, since
nothing in the running system can perform it.

```markdown
## Action: create
- reached by: POST /links, "Shorten" button on Home
- inputs: url {valid, no scheme, empty}, expires_at {absent, future, past}
- actor: anyone
```

Partition every input by the behaviour it produces, and name the class at each bound the
description states or implies: the empty value, the longest value, the largest number, the
value just past each. An input class the model leaves unnamed is where builds disagree with
each other.

### Lifecycle matrix

One per record. Rows are the states, with a row for the record not existing. Columns are the
actions, with a column for each move no action owns, such as time passing or a dependency
disappearing. A cell is the next state plus its effects, written in the check vocabulary's
nouns: created, unchanged, count, visible, hidden, emitted once. Three markers besides a
transition:

| Marker | Means |
| --- | --- |
| `refuse <status or title>` | the action is turned away, and what the caller sees |
| `no-op` | the action is accepted and changes nothing observable |
| `impossible <reason>` | the pair cannot occur, and why |

An empty cell is a finding.

```markdown
| link ↓ / action → | create | resolve | disable | on: expires_at passes |
| active   | –  | → active; 302; clicks +1 once | → disabled; code stops resolving | → expired |
| expired  | –  | refuse 410 Gone; clicks unchanged | refuse 409 Already ended | impossible |
| disabled | –  | refuse 404; clicks unchanged | no-op | impossible |
| (none)   | → active; code created; url stored | refuse 404 | refuse 404 | impossible |
```

The matrix is state × action and not a flat list, because a flat list hides the empty cell, and
the empty cell is the point. Effects are nouns from a check vocabulary and not prose, because
one line has to serve the builder as intent, the yardstick as a check and the process's record
of behaviour as a claim it can verify.

### Input table

Only the actions whose outcome varies by input class. One row per class that behaves
differently, the rest collapsed with the rule named.

### Invariants and open cells

Each invariant names the rows that exercise it. Durability, exactly-once effects, identity and
reachability are invariants, and each one demands a cell that observes it: a read after a
restart, a count after two concurrent writes on one record, a state some row reaches and some
row leaves. Each open cell is marked `OPEN` with its question. The file is not done while one
remains, and "Open cells: none" is a claim the yardstick author tests.

## Axes the description leaves out

A description names the happy path. The model earns its place on the axes the description
leaves to the builder, so walk each one across the matrix before calling a row done:

- **Terminal states.** Every state the record cannot leave has a row, and every action on that
  row is a refusal, a no-op or an impossibility. A terminal row with a transition in it is a
  question for the description's author.
- **Derived values.** Every value computed from others changes on every path that changes its
  inputs, so each such path's cell names the derived value among its effects.
- **Effects attached to transitions.** A write that happens on some paths and not others, or a
  status that says yes while the effect did not happen, is the silent failure. Each cell names
  its effects, so a path with the status and without the effect is a cell the check catches.
- **Durability.** For every durable record, one check arranges a state, restarts the system,
  and reads the state back.
- **Exactly once.** For every effect marked once, one check sends the action twice, or from two
  callers at once, and counts.
- **Reachability.** Every state has a row that reaches it and, unless terminal, a row that leaves
  it. A state nothing reaches is dead; a state nothing leaves is terminal and says so.

## Three authors, one description

The model does its work as the source of checks, not as reading for the builder. A builder with
a written description and a plan closes most of the matrix unaided; the cells it leaves open are
the ones the model's author also left open when both read the same description. So the model
and the yardstick have different authors:

- **The modeller** writes `model.md` from the description, before the plan, and the plan is
  derived from it.
- **The yardstick author** is handed the description alone, writes a second model, and turns it
  into checks that run against the build: one check per cell, a restart between arranging each
  durable state and reading it back, two concurrent writes on one record.
- **The builder** is handed the plan, with or without the model. A process that hands the model
  over does so as a file, never as a step the builder has to acknowledge.

Report the diff between the two models, cell by cell, before any build result, so a gain the
model shows can be told from two authors agreeing on the same hole. The cells where the two
models disagree are where the builds will disagree with each other.

## Rendering

The table is the source. A diagram is generated from it, never drawn beside it, because a drawn
diagram cannot show an undecided cell. One graph per record: a transition is a solid edge
labelled with the action and its effects, a refusal a self-loop in a warning colour, a no-op a
grey one, a move no action owns a dashed edge. Open and empty cells are listed under the graph
as a count. A process that keeps a renderer wires it to this table.

## Deriving the plan and the checks

The plan takes its slices from the matrix: the first slice reaches the record's first state
from `(none)` and reads it back, and each later slice fills a column or a row, which is the
walking skeleton [[vertical-slicing]] asks for. A slice whose cells are all open is not ready
to plan.

The checks take their shape from [[testing-design]]: each one names the cell it catches wrong,
goes red on a build that gets the cell wrong, arranges the state from the producer rather than
restating it, and asserts the effect rather than the status. One check per cell is the floor,
and a cell with an effect marked once or durable owes a second.

A gap is a cell the build gets wrong, leaves undefined or crashes on. The headline is gaps over
cells, and the first gaps to read are the ones on input classes the model never named.

## Completion criterion

The model is done when every one of these holds:

- Every record has a `told apart by` read and a lifecycle matrix with a `(none)` row.
- Every action has a surface and partitioned inputs with a class at each bound.
- Every cell is a transition with named effects, `refuse`, `no-op` or `impossible`. No cell is
  empty and no cell is `OPEN`.
- Every invariant names the rows that exercise it, and durability, exactly-once and
  reachability each have theirs.
- A reader who has not seen the description can say, from the file alone, what each action does
  to each record in each state, in ten minutes.
