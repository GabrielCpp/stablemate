# A story's QA by the service book

Status: accepted under the operator's standing authority for the service-book goal,
2026-11-10. Built as slice 2b of that goal.

Disclosure: I read the coder flows before writing this note. Each part and concept below
was checked against the question "would I name this without having seen the code".

## 1. Problem

An operator who runs stories unattended pays an agent to act as the test runner. On the
last long run that was about twelve dollars and fifty minutes a story, and it grew with
every lap in which the agent rewrote a check until it agreed with the app. A service that
has an executable book already holds those checks as a model a tool plays. The agent has
nothing to run by hand there.

Done, for the operator: a story that touches a service with an executable book has that
service judged by a run of the book. The seat that brings the book up to the story costs
one turn. The verdict costs no model call. A claim the app does not meet reaches the
developer seat as a finding that names the claim and the observed answer. An environment
that is not healthy reaches the operator and never the developer seat. The book's change
lands with the story.

Out of scope:

- A service with no executable book. Its QA does not change.
- Dropping the compiled scenario plan for a service that has an executable book. Until that
  lands, such a service is judged twice.
- Writing the executable book before the code, at the spec pass.
- A run against a deployed environment.

## 1b. Claims

From the sixteen attended passes this stage records (fifteen on one storied commit with a
planted defect each, one on a whole unfinished story with the installed tool):

1. One seat makes the pass: it reads the story, its plan and its review answers, then the
   diff, and edits only the book.
2. The seat must not read another QA's plan, report or evidence.
3. The base must be green before the seat starts. A red base cost one attended pass 107
   minutes on failures it could not explain.
4. The pass ends in a targeted run of the calls the story touches, not the whole book.
5. A claim the app does not meet stays in the model as the intent, with the app's answer
   declared as a known defect. It is never written into the model as the truth.
6. The run's exit code tells four outcomes apart: agrees, disagrees, misuse, could not
   judge.

## 2. Parts and concepts

**Level 1.**

- **Coverage** owns the answer to "which of this story's services have an executable
  book". It never knows how a book is played. It hands the list to the lane.
- **The book seat** owns the book's change for one story and the list of claims it could
  not make the app meet. It never knows the verdict. It hands the calls it touched and
  its findings to the judgement.
- **The judgement** owns the verdict on the story for those services. It never knows how
  the book was edited. It hands a verdict to the story's flow.
- **The running copy** owns a service running the story's code. It never knows the book.
- **The record** owns landing the book's change beside the story's code.

Flow: coverage answers first. With no covered service the lane is over and says so. The
seat plays the calls it picks once before it edits, to prove the base. It
makes its pass. The judgement selects the plays from the story's diff with
`ostler book affected`, plays only those calls and journeys under a time limit
(`book_play_minutes`) after saying what it will play, and reads the outcome. A story's
QA never plays a whole book. What the selection cannot narrow is listed as owed to a
scheduled whole play that runs outside any story. The
record lands the change when the outcome agrees. A later visit for the same story plays
the calls the first visit recorded, and the seat is called only when that play disagrees.

**Level 2.**

Coverage:

| Concept | Owns | Never knows |
|---|---|---|
| Covered service | one service of the story that has a loadable book | the book's content |

The book seat:

| Concept | Owns | Never knows |
|---|---|---|
| Touched calls | the calls of the service the story's claims bear on | whether they pass |
| Finding | one claim of the story the app does not meet, with the observed answer | who fixes it |

The judgement:

| Concept | Owns | Never knows |
|---|---|---|
| Outcome | what one play of the touched calls said: agrees, disagrees, could not judge | the seat's reasoning |
| Verdict | pass, back to the developer, back to the seat, ask the operator | the book's format |

The running copy and the record each hold one responsibility and need no table.

## 3. Invariants

- I1. A run that could not judge never becomes a finding for the developer. Owner: the
  judgement.
- I2. A story does not pass while the seat reports a finding, even when the run is green.
  A declared defect makes the run green by design. Owner: the judgement.
- I3. The seat's edits stay inside the book. Owner: the record, which lands only paths
  under the book and fails on anything else the seat left.
- I4. The lane ends in a pass, a hand-back or a question. A budget of laps that runs out
  is a question to the operator. Owner: the judgement.

## 4. Forces and patterns

Forces:

- F1. How a service's side of a story is judged varies by service: some have an
  executable book, some have a scenario plan. A story can hold both kinds.
- F2. The existing QA is under redesign on another branch. The lane must not depend on
  its inside.
- F3. The seat's turn is the only model spend, so the plays around it must be plain
  commands.
- F4. A copy of the stack is named by the run. The book must reach that copy without
  naming it.

Patterns:

- Between parts, for F1 and F2: the lane is its own flow with the result type the story's
  flow already reads from QA. The story's flow hands off to it before the existing QA and
  treats a hand-back the same way. Adding the lane is one flow and one branch where the
  story's flow chooses. Each lane is a kind of "story QA", and neither is a kind of the
  other.
- Inside the judgement, for F3: plain functions over the tool's exit code. No pattern.
- For F4: the book names a host as "the run's copy", and the play takes the copy's name
  as an option with the same default the environment commands use.

Claims: 1, 2, 3 and 5 become the seat's prompt. 4 is the judgement's play. 6 is the
outcome.

Rejected: a check that the seat did not delete cells. One attended pass did that before
the format could keep an intent beside a defect. None did after. It comes back if a run
shows it.

SOLID: each concept owns one thing. A third lane is one more flow and one more branch.
The lanes share only the result type. The story's flow reads the result and no lane's
inside.

## 5. Mapping onto the existing system

- Coverage: **new**. A node in the lane's package lists the story's services (the story's
  `services:` frontmatter, as the plan context reads it) that have `services/<name>/service.py`
  under the repo root.
- The book seat: **new**. Role `qa-book` in `coder/shared/roles.py` and one prompt in the
  lane's `prompts/` that holds the whole method, as every coder role's prompt does. It
  names the `ostler-book` skill, and a repo that does not install it gets a seat that
  reports `blocked`. (Revised: the plan first put the method in a library body, which no
  coder role reads.)
- The judgement: **new**. Nodes that run `ostler book check` and `ostler book run --only
  … --copy <lease>` as a child process in the repo root and return the exit code with the
  tail of the output. Verdict routing lives in the lane's flow.
- The running copy: **exists**. `stack_target`, `ensure_stack` and `release_copy` in
  `coder/shared/stack.py`. The lane leases its own copy the way QA does.
- The record: **reshape**. `coder/shared/story_commit.py` lands the markdown book's delta.
  The lane needs the same for paths under `services/<name>`.
- The result: **exists**. `QaFlowResult` and `QaFinding` in `coder/shared/schemas/qa.py`.
- The story's flow: **reshape**. `Coder.qa` in `coder/main/flow.py` hands off to the lane
  first and reuses `_sent_back`.
- The tool: **reshape**. A host written `ostler:` with no name is the run's copy.
  `ostler book run`, `explore` and `walk` take `--copy`.

What the system has that the design lacks: the QA flow's evidence gate, regression suites
and sentinel ids. They belong to the scenario lane and stay there.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| A story with no covered service | the same QA, at the same cost | the coder flow tests | all green | all green, and the lane makes no agent call |
| The developer seat | findings in the shape it already answers | `QaFinding` | one type | the same type |
| The operator | a run that never ends on a spent budget | `make check-no-giveup` | passes | passes |
| A workflow | no read of the environment | `make check-no-env` | passes | passes |

## 6. Slices

1. The tool reaches the run's copy: `ostler:` and `--copy`. Done when a unit test shows
   the address command gets the option's copy and the default follows the lease.
2. The lane with its seat, plays and verdicts, behind coverage. Done when the flow tests
   show: no covered service makes no agent call and passes; a green pass lands the book;
   a finding goes back to the developer; a red play with no finding goes back to the
   seat; a play that could not judge asks the operator. The rows of 5b hold.
3. The story's flow hands off to the lane. Done when the coder flow tests pass and a
   parked run on a real story finishes its QA through both lanes.

## 7. Assumptions

- A1. Code selects the calls the judgement plays. Decided: `ostler book affected` reads the
  story's diff of the app and of the book, and the seat's result no longer carries calls.
  Basis: a seat that narrows its own exam passes a story it never judged. If wrong: the
  seat names the calls again and the judgement refuses an empty list.
- A2. A targeted play takes minutes. Decided: two plays a story, each limited by `book_play_minutes` (15).
  Basis: 3 min 42 s and 4 min 30 s on the attended story. If wrong: the base play goes.
- A3. The executable book lives at `services/<name>` under the repo root. Basis: the tool
  loads it from there today. If wrong: coverage and the record take the root from one
  place.
- A4. A covered service is still judged by the scenario lane until its compiled scenarios
  are dropped. Decided: the lanes run one after the other. Basis: out of scope above. If
  wrong: nothing breaks, the story pays for both.
