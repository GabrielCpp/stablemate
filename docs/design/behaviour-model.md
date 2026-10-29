# The behaviour model a builder reads before the plan

Disclosure: this note was written after reading the existing system. The conversation that
settled it read the `ostler-okf` skill and its check vocabulary, the `testing-design`,
`test-coverage-analysis` and `decompose` skills, the `state` and `data-state` node types, and
the paddock README. A talk on FlowCheck, a constraint language compiled to static analysis over
a vibe-coded app, started the conversation. Its claims are in section 1b.

## 1. Problem

A builder is handed a description of what to make and a plan for making it. The plan says
what will be built and how. Nothing says what the thing does in every situation: what each
action does to each record in each state, what an observer can see afterwards, what survives a
restart, what happens when two callers race. The builder fills those gaps with whatever its work
happens to do. The result runs without an error and violates the intent somewhere nobody looked.
The person who asked hits it weeks later, as a total that did not change after a banner said it
did.

This is a method problem, not a coder-workflow problem. It holds for an agent building a story,
a person implementing a spec, a team migrating a schema, a writer documenting a surface. Every
one of them works from a description that names the happy path and leaves the matrix of states
and actions to be filled in by whatever gets built. The tests written afterwards share the
builder's blind spot, because the same reading of the description produced both.

Done, as the operator sees it:

- Before the plan, a file exists that a person can read in ten minutes and that answers, for
  every record the work touches, what each action does to it in each state, and what is
  observable afterwards.
- Every cell of that file is decided, or marked open with the question. An empty cell is a
  finding.
- The builder is handed the file. The yardstick that judges the build is derived from it, or
  from an independent one written from the same description.
- The file maps onto whatever the process keeps as its record of behaviour without a
  translation step. For this repo that record is the book; section 4 holds the mapping.

How this repo stands today, as one instance: the book's `verify:` bullets name the observation
that would show a claim false. Doctor refuses a check that passes on the defect it names. The QA
lane runs the book against the running app. But the book is written after the code, surface by
surface, and nothing asks whether the set of facts is complete. A condition no fixture arranges
is a scenario that never runs. The agent that wrote the code and the agent that wrote the book
share the blind spot.

Settled with the operator on 2026-10-28:

- The book stays markdown and stays the source. A logic language was considered and rejected
  for the book itself: the book's readers are a person and an agent operating the app, and prose
  is what they operate from. Logic, where wanted, is a view computed from the book's facts, or
  the Python engine ostler already is.
- The model is not a test matrix. It is a description of the thing being built, written before
  the plan. Test cases are one thing derived from it. The plan is another.
- Everything the earlier list of "defects a model cannot catch" held is in scope. A model does
  not need to name a defect. It needs to demand the observation under which the defect shows.
  Durability, exactly-once effects, identity invariants and reachability are axes of the model,
  not implementation details below it.

## 1b. Claims

From the FlowCheck talk, re-derived rather than taken:

- A silent failure is a write that happens on some paths and not others, or a status that says
  yes while the effect did not happen. Both are observations the model can demand. Neither needs
  static analysis to demand.
- Static analysis proves every path. A scenario runs one path per fixture. The model closes the
  gap by making every (state, action) pair a cell, so the condition no fixture arranges becomes a
  cell the plan cannot skip.

From the repo's own skills:

- `test-coverage-analysis` story mode already derives axes and a decision table, checks it for
  gaps and conflicts, and writes `test-matrix.md`. It runs after the grill and feeds test writing.
  The structure is right. It is filed under testing and runs at the wrong time.
- `decompose` already asks for invariants and for what each concept must never know. Those are
  the identity rules and the boundaries the model's invariant section holds.

## 2. The model on paper

One markdown file per unit of work, `model.md`, beside the description it models. Three
readers: the builder, the author of the yardstick, and whatever checker the process has. So every
line is a fact a cell can hold or an observation a check vocabulary can spell. Prose is for the
collapse rules only. Five sections, each derived from the one above it.

**Records.** One block per record the work touches. Its states, how they are told apart by a
read, whether it is durable, its identity rule.

```markdown
## Record: link
- states: active, expired, disabled
- told apart by: GET /links/{code} → $.state
- durable: yes
- identity: code, unique across all links, generated
```

**Actions.** One block per thing a user or caller can do. The surface that reaches it, its inputs
partitioned into equivalence classes, its actor. An action with no surface is a gap in the model.

```markdown
## Action: create
- reached by: POST /links, "Shorten" button on Home
- inputs: url {valid, no scheme, empty}, expires_at {absent, future, past}
- actor: anyone
```

**Lifecycle matrix.** One per record. Rows are states, with a row for the record not existing.
Columns are actions, with a column for each move no action owns, such as time passing. A cell is
the next state plus its effects, written in the check vocabulary's nouns: created, unchanged,
count, visible, hidden, emitted once. Three markers besides a transition: `refuse <status/title>`,
`no-op`, and `impossible <reason>`. An empty cell is a finding.

```markdown
| link ↓ / action → | create | resolve | disable | on: expires_at passes |
| active   | –  | → active; 302; clicks +1 once | → disabled; code stops resolving | → expired |
| expired  | –  | refuse 410 Gone; clicks unchanged | refuse 409 Already ended | impossible |
| disabled | –  | refuse 404; clicks unchanged | no-op | impossible |
| (none)   | → active; code created; url stored | refuse 404 | refuse 404 | impossible |
```

**Input table.** Only the actions whose outcome varies by input class. One row per class that
behaves differently, the rest collapsed with the rule named.

**Invariants and open cells.** Each invariant names the rows that exercise it. Each open cell is
marked `OPEN` with its question. The file is not done while one remains.

Two choices inside this are deliberate. The matrix is state × action and not a flat list,
because a flat list hides the empty cell, and the empty cell is the point. Effects are nouns from
a check vocabulary and not prose, because one line has to serve the builder as intent, the
yardstick as a check and the process's record of behaviour as a claim it can verify. The method
owes the vocabulary; the process names it. Here it is ostler's.

## 3. Rendering

The table is the source. A diagram is generated from it, never drawn beside it, because a diagram
cannot show an undecided cell. `ostler model dot <model.md>` writes one graph per record: a
transition is a solid edge labelled with the action and its effects, a refusal a red self-loop, a
no-op a grey one, a move no action owns a dashed edge. Open and empty cells are listed under the
graph as a count. Mermaid is a one-line switch in the same generator for a model read in a PR.

## 4. Where it sits

In the method: after the questions about the description are settled and before the plan. The
plan is derived from the model, and the checks that judge the build are derived from the
model's cells, so a cell is a scenario the plan cannot skip. The method skill
`base-library/library/skills/method/behaviour-model/SKILL.md` carries only this much; each
process that adopts it maps the model onto its own record and checker. The book's mapping is a
paragraph of the `ostler-okf` skill.

The mapping for this repo, as one application: the step sits in the coder workflow after the
grill and before the plan. The QA plan's fixtures come from the model's cells. In the book, states
map to `data-state`, transitions to `moves:`, effects to `verify:`, actions to the node that
reaches them. Doctor gains three closure codes over the facts it already walks: a (state, action)
pair with no cell, an action whose effect is missing on a path where the action is allowed, a
state no row reaches or leaves. None of this is built.

## 5. The experiment

Before building the step, measure whether handing a builder the model changes what it leaves out.

Two arms, same inputs otherwise. Arm A gets a product brief and a plan. Arm B gets the brief,
the plan and `model.md`. Both run on Sonnet in a plain `claude -p` session, no stablemate
workflow, same budget. The subject is an expense-splitting API with a settlement lifecycle, so
the matrix has real cells: a settled group refuses new expenses, a removed expense moves the
balances, balances survive a restart.

The model is written once by the operator's session and frozen. The yardstick is a third artifact
by an independent author handed the brief alone, turned into checks that run against each build:
one check per cell, a restart between arranging each state and reading it back, two concurrent
writes on one record. A gap is a cell the build gets wrong, leaves undefined or crashes on.
Headline per run is gaps over cells. The diff between the two models, cell by cell, is reported
first, so the gain the model shows can be separated from two authors agreeing on the same hole.

Prediction, written before any run: arm B closes the cells about terminal states refusing
actions, derived values updated on every path, effects attached to transitions, lifecycle
boundaries, durability and exactly-once. Arm A leaves several of these open. Both arms are
exposed the same to a route written and never registered, which only the composition finds, and
both yardsticks find it. If arm B leaves the terminal-state cells open with the model in hand, the
model has to be enforced by the QA plan rather than read, and the step design changes.

Outcome, 2026-10-28, three runs per arm on Sonnet, 134 checks per run. Arm A left 3 gaps over
402 cells, arm B left 2. Every gap concerned the upper bound of an amount: arm A capped amounts
below the brief's integer range, arm B answered 500 above 64 bits. Every terminal-state,
derived-value, durability and exactly-once cell passed on all six builds. The prediction failed:
on a seven-story greenfield API with a written contract, the builder closes the matrix from the
brief and plan alone, and reading the model changed neither gaps, cost nor turns. The gaps were
found by the independent yardstick, a model compiled into checks. The one input class the frozen
model lacked (beyond 64 bits) is the one arm B crashed on, with the matching invariant written a
few lines above it. Two conclusions for the step. The model earns its place as the source of
checks, not as reading for the builder. A model with "Open cells: none" is a claim; the
yardstick author named 18 open cells from the same brief, and those 18 are exactly where the six
builds disagree with each other, so the closure checks must count unnamed input classes, not
only empty cells. A larger or legacy subject may still show a reading effect; this one does not.

## 6. Assumptions

- Assumption: a Sonnet builder reads a decision table and acts on it. Decided: the model is handed
  over as a file, not enforced. Basis: none yet, this is what the experiment measures. If wrong:
  section 4, the model feeds the QA plan directly and the builder sees only the plan.
- Assumption: three runs per arm separate signal from Sonnet's variance on a task of this size.
  Decided: three each. Basis: the ticket-desk benchmark's spread across runs. If wrong: more runs,
  same design.
- Assumption: a model written from the story by a fresh agent is complete enough to judge a
  build. Decided: an independent yardstick author. Basis: `test-coverage-analysis` story mode
  produces such tables today. If wrong: section 4, the grill precedes the model, which is where
  story mode sits now.
