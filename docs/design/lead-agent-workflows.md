# One dev owner per story, judged from outside

**Disclosure.** I read the existing solution before this note was written. That
covers the coder main, dev and review flows, ostler's review settlement, the engine's
session, recovery and worklist code, the constitution's aims 2, 8 and 9, and the workflow
package's `AGENTS.md`. Every design decision I saw there is a claim in section 1b.
Section 4 re-derives or rejects each one. The coder workflow is the worked example.
The same shape is meant to carry to the other workflows later.

## 1. Problem

**Who feels this.** An operator hands the coding workflow an epic and walks away. Today a
story passes through a dozen narrow agent turns, and each one starts cold and rebuilds
what the last one knew. A reviewer and a fixer pass findings back and forth until a
budget runs out. The operator cannot tell at launch how many stories the run will do,
because the run picks the next story from disk after each one ends.

**Done looks like this.**

- The operator picks the work at launch: every queued epic, one epic, or one story. The
  run reports "3 of 7" from its first minute. A follow-up the dev owner files shows at once,
  as "3 of 8". The run ends when every item on its list is done.
- One list shows what the run has left: the stories, and each story's open findings. The
  operator, the dashboard and the next turn all read that list. A run killed mid-story
  resumes on the item it was on, in the same conversation.
- One conversation carries each story from plan to green. A story starts a fresh context
  only for a judge that must not share the work's view: one review, and QA. That is 3
  fresh contexts per story, down from one per turn.
- A review produces findings once. The dev owner answers every finding in the same
  conversation. No second reviewer turn runs because the first fix pass was incomplete.
- An operator's answer lands in the conversation that asked, and the dev owner goes on from
  where it stopped.
- No turn is killed while it is making progress. No single command runs for more than
  25 minutes.
- A Dev owner whose conversation was compacted still knows its story, its open findings, its
  follow-ups and every operator answer.

**Out of scope.**

- How QA builds and runs its checks against the book.
- How the book gets written after a story changes.
- The inside of the ship lane's CI and merge turns, past requirement 36.
- The defect backlog that outlives a run, and the lane that drains it.
- The rule that the auto-resolver applies only written decisions. This note keeps it.
- The other workflows. They follow once the coder pilot has run twice attended (aim 9).

## 1b. Claims

From the existing coder workflow and engine:

1. The run picks the next epic, then the next story, from disk after each story ends.
   (coder main flow, `select_epic` and `select_story`)
2. Each lane (dev, review, docs, qa, fix) is a separate sub-workflow the main flow hands
   off to. (coder main flow)
3. Implementation runs one service layer at a time, each layer in a fresh implementer
   session. (dev flow, `implement`)
4. A story's primary turns share one session chain across lanes, recycled after 8 turns.
   (`shared/conversation.py`; `MAX_SESSION_TURNS` in `dev/nodes.py:39` and
   `review/flow.py:50`)
5. Review is two turns: a medium-power code-review pass, then a high-power verdict
   against the story. Findings split by confidence into must-fix and advisory.
   (review flow, `start` and `review`)
6. An apply turn in the implementer's chain fixes the findings. Ostler settles each
   finding from a JSON resolution with artifact and assertion checks. Three reworks, then
   the operator gate. (review flow, `apply` and `_guard`; ostler `settle_review`)
7. Every operator gate first goes through a resolver that may answer only from a written
   decision. (`workflows/AGENTS.md`)
8. Tests judge against intent, review judges against standards, and QA judges against
   the book with the code out of the room. (constitution aim 2)
9. One wide owner seat on the strongest model sits above narrow workers. The state machine
   holds the gates, the evidence, the budget and the checkpoint. (constitution aim 8)
10. A turn's budget is pacing advice. The kill is silence past a bound. One shell command
    is capped per agent profile. (engine `ladder.py`, `process.py`, claude backend)
11. A turn that keeps failing is reframed into a fresh session. (engine `ladder.py`)

From the user, in this conversation:

12. One strong owner agent per flow, which spawns its own subagents.
13. When the dev owner needs operator help, it stops, asks, and resumes from the same session.
14. Pack the stories into the run, and finish when they are done.
15. No ping-pong between reviewer and fixer.
16. A subagent does the review, and the main agent sorts and fixes.
17. Each review is parseable markdown that ostler checks.
18. Sessions must be resumable.
19. No timeout on agent work. No single 1-hour tool call.

Agreed in this conversation:

20. The state machine launches the reviewer with fixed inputs, and freezes its findings
    on disk before the dev owner sees them.
21. The dev owner may decline a finding with a reason. It may not drop one.

From the user, added after the first draft:

22. The worklist is the cross-step todo list that dictates work.

From the engine's worklist, read for claim 22:

23. One worklist holds items of many kinds in one store. A claim takes active items
    first, so a resumed run re-takes what it held. A drain takes one chunk per state
    visit and settles each claimed item to done once its handler returns. (engine
    `worklist.py`, `self.pipeline`)

From the user, added with the launch selection:

24. The dev owner can add follow-up work to the worklist.
25. The operator selects every epic, one epic or one story at launch, through the
    workflow's params. Every epic pushes each epic's stories, in order.

From the existing coder workflow, read for claim 25:

26. The coder takes a mode, epic or story. Epic mode works the whole epic queue front to
    back. No param selects a single epic. (coder main flow params and `start`)
27. A story that cannot run sets its whole epic aside for the run, and the run moves to
    the next epic. (coder main flow, `select_story` and `flag_epic_blocked`)

From the user, added after claim 27:

28. A run may not continue past a failed story. Failing is not acceptable, because a
    story is presumed feasible.

From the user, added after the first review of this note:

29. Where the engine lacks support the design needs, the engine gains it.
30. Compaction of a long Dev owner conversation is expected and necessary.

From the existing coder workflow, found by that review:

31. A QA lane that ends inconclusive gives up and fails the run. (coder main flow,
    `give_up`, failure class `qa-give-up`)

From the user, added after the first review:

32. A 25-minute command cap is realistic for test suites.
33. One harness does the review, the triage and the fixes in one turn, prompted to
    give each task a subagent of the right strength.

From the user, added after the owner collapse:

34. Every lane has its own single owner agent. The build lane is called dev, and its
    owner is the Dev owner. QA, docs, the backlog drain and the ship lane each get one,
    and none of them is the Dev owner. Each owner gives triage, fixes and checks to
    subagents.

From the user, added after the main-loop compression:

35. The main loop is a straight line: dev, docs, QA, commit, then the PR and the ship
    lane. Only two detours leave it: replan and refix. A docs lane that cannot document
    a story replans its epic. Work left uncommitted after QA goes back to the Dev owner.
36. The ship lane owns red CI and the merge, conflict resolution included. The main
    loop keeps no docs gate and no merge states of its own.

## 2. Parts and concepts

### Level 1: parts

| Part | Owns | Never knows | Hands to |
|---|---|---|---|
| **Worklist** | the work this run has left, at every grain, and where each item stands | how an item is done or judged | open items to Custody; progress to the operator |
| **Dev owner** | one story's code change and every decision in it | what a judge thinks until the judge is done | a readiness claim to Custody; answers to Sign-off; follow-ups to the Worklist |
| **Judgment** | findings about a story, from inputs the work did not produce | the dev owner's conversation and reasoning | findings to the Worklist, as items |
| **Sign-off** | whether each answer to a finding holds | how a finding was fixed beyond its evidence | each finding's new status to the Worklist |
| **Operator desk** | questions, and the answers that come back | what the asker will do with an answer | the answer to the conversation that asked |
| **Custody** | the run surviving crashes, which turn opens next, and no turn running unbounded | what any turn decided | the next turn to start or resume |

In plain words: the operator picks what to build: everything queued, one epic, or one
story. Everything the run still owes sits on one todo list: the stories, the follow-up
work found along the way, and every defect a reviewer has written down. One senior
engineer takes each story and directs helpers until it is done. When the engineer spots
work outside the story, it adds that work to the list instead of doing it on the side.
Outside
reviewers who never talk to that engineer pin what is wrong to the list. The engineer
answers every item, and a clerk checks each answer and crosses the item off or sends it
back. Questions nobody can answer from the written rules go to the operator, and the
answer comes back to the engineer who asked. A supervisor reads the list to decide who
works next, keeps the record so work survives a crash, and stops anyone who has gone
silent.

**Flow.**

1. At launch, Selection turns the operator's choice into story items. Every epic files
   each queued epic's open stories, epic by epic. One epic files that epic's open
   stories. One story files that story alone. Order fixes the sequence once.
2. Custody's Route takes the first pending story in Order, and opens the Dev owner with a
   Brief and the Resume note.
3. The Dev owner plans, builds through helpers, runs the tests, and files a readiness claim.
   Work it finds outside the story goes onto the list as a follow-up, filed right after
   the story.
4. Custody checks the claim's evidence (the tests ran green), then launches a Judge with
   fixed inputs. Each finding the Judge writes becomes a finding item under the story.
   From then on only its status changes.
5. Route resumes the same Dev owner conversation with the story's open finding items. The
   Dev owner answers each one: fixed with evidence, or declined with a reason.
6. Sign-off checks the answers and sets each finding item settled, declined or open.
   Route resumes the Dev owner on what is still open. No second review runs.
7. Steps 4 to 6 repeat for QA, the second Judge.
8. A blocked Dev owner asks the Operator desk. The desk answers from a written rule, or holds
   the question for a person, and the whole run waits. Either answer resumes the same
   Dev owner conversation on the same story. A story the Lap budget runs out on goes the same
   way.
9. The story item becomes done when its claim held, every Judge on its route ran, and
   none of its finding items is open. No other way out exists. A story is presumed
   feasible, so the run never steps past one that is not done.
10. Route takes the next pending item. A follow-up comes first, worked in its parent's
    Dev owner conversation and judged like a story. When an epic's last item settles, the
    epic's closing steps run. The run ends when no pending item remains.

Custody acts at every turn boundary, and Route reads the Worklist each time. Judgment
acts once per lap, and a lap starts only when a later judge sends the story back.

### Level 2: concepts

**Worklist**

| Concept | Owns | Never knows |
|---|---|---|
| Item | one piece of work that outlives the turn that found it: id, kind, epic, story, content, status | how it will be worked |
| Kind | which concepts may file and move the items of one sort, as one access rule | what any item of that sort says |
| Selection | the operator's launch choice: every epic, one epic, or one story | which stories the choice resolves to |
| Launch set | the story ids the Selection resolved to, fixed in the checkpoint | any story's content |
| Order | the sequence items run in: epics in queue order, stories by dependency inside each epic, a follow-up right after its parent | why a dependency exists |
| Standing | a story or follow-up item's status: pending, active, done | why the Dev owner is stuck |
| Amendment | an operator-approved change to the launch set, the only way it changes mid-run | how the replacement stories were planned |

Three kinds exist in this note.

| Kind | Filed by | Moved by |
|---|---|---|
| story | Launch set; Amendment | Standing |
| follow-up | the Dev owner, through Custody | Standing |
| finding | a Judge, through Custody | Settlement |

Progress, the "3 of 7" line, is a plain function over Standing. It counts stories and
follow-ups together. A step inside one Dev owner turn is not an item. The Dev owner's own todo list
stays in its conversation, because it never crosses a turn boundary.

**Dev owner**

| Concept | Owns | Never knows |
|---|---|---|
| Dev owner conversation | one resumable session that carries a story's decisions from plan to green | any Judge's context |
| Brief | the opening message: story, specs, and what earlier runs left | how those inputs were produced |
| Resume note | the block every Dev owner prompt opens with, rendered from disk: the current item, its open finding items, the follow-ups filed, the answer log and the plan file | what the Dev owner did with it last time |
| Helper | bulk work the Dev owner delegates inside one of its turns | the run's checkpoint |
| Readiness claim | the Dev owner's statement that the story is ready, with the commands it ran | the Judges' verdicts |
| Follow-up | work the Dev owner found outside its story's scope, with a parent story and a reason | when or by whom it will be worked |

**Judgment**

| Concept | Owns | Never knows |
|---|---|---|
| Judge (role) | producing findings about one story from a fixed input set | which variant it is talking to; the Dev owner conversation |
| Standards review (variant) | findings about the diff against the coding standards and the story | the book; QA's results |
| Behaviour check (variant) | findings about the running product against the book, with code out of the room | the code |
| Judge inputs | the fixed set one Judge sees, assembled before launch | the Dev owner's notes and reasoning |
| Finding | one observed defect: id, place, severity, evidence | how it will be fixed |

Finding is a shared value type. Judgment writes it, the Worklist holds it as an item's
content, and the Dev owner and Sign-off read it.

**Sign-off**

| Concept | Owns | Never knows |
|---|---|---|
| Answer | the Dev owner's reply to one finding item: fixed with evidence, or declined with a reason | the Judge's reasoning beyond the finding |
| Evidence check | whether one Answer's cited evidence holds | the Worklist |
| Settlement | each finding item's new status, from its Answer and its evidence check | who wrote the findings or the answers |

Answer is a shared value type. The Dev owner writes it, and Sign-off reads it.

**Operator desk**

| Concept | Owns | Never knows |
|---|---|---|
| Question | what blocks the asker, and what it already tried | where the answer will come from |
| Ruling | an answer quoted from a written decision, with its citation | anyone's unwritten preference |
| Escalation | a question with no written answer, held for a person while the run waits | the asker's conversation |
| Delivery | putting the answer into the conversation that asked, and onto the run's answer log | the answer's content |

**Custody**

| Concept | Owns | Never knows |
|---|---|---|
| Checkpoint | the durable record of where the run is | what any turn decided |
| Route | the next turn to open, with the items it carries, read from the Worklist | what an item says beyond its kind, story and status |
| Session handle | which resumable conversation belongs to which story, recorded as the turn starts, with the one working directory it runs in | the conversation's content |
| Liveness | cutting a turn that has said nothing past a bound | how long the turn has run in total |
| Command cap | the longest one tool call may run | which command it is |
| Lap budget | how many laps a story may take before it goes to the Operator desk, counted on the story's item | what each lap changed |
| Long job | a measurement that runs detached and reports back | the turn that started it |

## 3. Invariants

1. **The launch set changes only by an Amendment.** Owner: Launch set. Upheld by
   Amendment and the Operator desk.
2. **A story or follow-up item is done only when its readiness claim held, every Judge
   on its route ran, and none of its finding items is open.** Owner: Standing, the one
   concept that sees the whole item. Upheld by Settlement and the Readiness claim.
3. **Every finding item has exactly one Answer before its lap ends.** Owner: Settlement.
4. **An item's content never changes after it is filed. Only its status changes.** Owner:
   Item. It detects an edit by digest and fails. This covers a Judge's findings once
   the Judge ends.
5. **A Judge never sees the Dev owner conversation, and the Dev owner never edits a Judge's
   inputs.** Owner: Judge inputs.
6. **An answer reaches the conversation that asked.** Owner: Delivery.
7. **A Dev owner conversation is resumed, never replaced, unless the harness cannot resume
   it or compaction can no longer shrink it.** A replacement is logged, and it starts
   from a Brief rebuilt from disk with the Resume note. A cut or a crash mid-turn
   resumes the same conversation, because its handle is recorded as the turn starts.
   Owner: Session handle.
8. **No single tool call outlives the liveness bound.** Owner: Command cap. Upheld by
   Liveness.
9. **The resolver answers only with a citation.** Owner: Ruling.
10. **A declined finding carries a reason a person can read, and it shows in the story's
    report.** Owner: Settlement.
11. **No turn opens on work the Worklist does not list.** Each turn's opening names the
    items it works on. Owner: Route.
12. **An item is filed and moved only by the concepts its Kind names.** The Dev owner files
    follow-ups and never settles a finding. A Judge never settles a story. Owner: Kind.
13. **During a run, a story's status on disk follows its item, never the reverse.**
    Owner: Standing.
14. **A follow-up names its parent story and a reason, and files no follow-up of its
    own.** Work a follow-up's Dev owner finds goes to the defect backlog instead. Owner:
    Follow-up. (A11)
15. **Route opens an item only when every item before it in Order is done.** A stuck
    story holds the run at the Operator desk. It never sets the story, its dependents or
    its epic aside. Owner: Route. Upheld by Order, whose dependency sort puts every
    dependency first (A12).
16. **The Selection resolves exactly once, at launch.** A resumed run reads the Launch
    set from the checkpoint and never re-reads the queue. A launch story whose
    dependency lies outside the launch set and is not done fails the launch, before
    any turn runs, with that dependency named. Owner: Launch set. (A12)
17. **Nothing a Dev owner needs after a compaction lives only in its conversation.** The
    current item, its open finding items, its follow-ups, every operator answer and the
    plan are on disk, and every Dev owner prompt opens with the Resume note. Owner: Resume
    note. Upheld by Delivery and the Worklist. (claim 30)

## 4. Forces and patterns

### Forces

- **F1. Judgment must come from inputs the work did not produce.** What a Judge sees
  varies independently of what the Dev owner did. (aim 2)
- **F2. The Dev owner's context is expensive to rebuild and worth keeping.** A story's plan,
  its failed attempts and its operator answers all inform the next fix. Compaction will
  drop some of it, so what must survive is kept on disk as well (claim 30).
- **F3. Harnesses differ.** Subagent support, the event stream, the command cap and
  session resume each vary by agent CLI.
- **F4. A crash or a kill must not lose finished work.**
- **F5. The run's extent must be visible at every moment.** The operator fixes it at
  launch at one of three grains: every epic, one epic, or one story. Only an Amendment or
  a Dev owner's follow-up grows it after that.
- **F6. Judges grow over time.** Review and QA exist today. A security or an
  accessibility check is the obvious next one.
- **F7. Settlement must be testable without an agent, and readable by a person.**
- **F8. A Dev owner turn may run for an hour or more.** Progress is visible only as events.
- **F9. Work arrives at several grains, and the grains grow.** Stories come at launch,
  findings come per Judge, and a new Judge brings new findings. Every step, the operator
  and a resumed run must see the same open work. (claim 22)

### Between parts

- **One value handed along (F1).** Judge inputs and Answers are files on disk. No part
  calls into another's conversation.
- **One shared worklist (F9).** Each part files or settles items of its own kinds, and
  Route reads the list to pick the next turn. No part tells another what to do next.
- **A state machine with a checkpoint (F4).** Custody is the machine. The Dev owner and the
  Judges are its agent turns. The Worklist sits beside the checkpoint, and a resumed run
  takes active items first.

### Inside parts

- **Worklist: a plain JSON file in the run, rewritten whole on each change (F7).** No
  second store exists, so no storage port. (A10)
- **Kind: a plain table from kind to the concept that settles it (F9).** A new Judge's
  findings use the existing finding kind.
- **Route: a plain function from the Worklist and the checkpoint to the next turn (F7,
  F9).** A test drives it with no agent.
- **Dev owner conversation: one resumable session per story (F2).** Every Dev owner turn resumes it,
  and none reframes into a fresh one. The one exception is a turn compaction can no
  longer shrink. It restarts from a rebuilt Brief and the Resume note (invariant 7).
- **Resume note: a plain function from the run directory to text (F2, F7).** A test
  renders it with no agent. It names the worklist path, so the Dev owner can re-read the list
  in the middle of a turn.
- **Judge: a role with two variants (F6).** Route chooses the variant at each step of
  the story's route. A third Judge adds one concept and one line in that route.
- **Settlement: a plain function over the Answer file and the evidence checks (F7).** No
  pattern beyond that.
- **Command cap and Liveness: adapters per harness (F3).** Each harness variant translates
  the cap into its own setting.
- **Launch set: a plain value in the checkpoint (F5).** Amendment is an explicit operator
  step, not a re-read of the disk.
- **Selection: a plain function from the launch choice and the queue to the Launch set
  (F5).** The three grains are three values of one input, not three variants. They differ
  only in which epics they read.
- **Follow-up: a field on the Dev owner's turn result (F9).** Custody files each one after the
  turn. The Dev owner never writes the worklist itself (invariant 12).
- **Liveness: a silence bound, not a wall clock (F8).** A Dev owner turn's budget is unbounded.

### Claims

| # | Verdict | Force or reason |
|---|---|---|
| 1 | Rejected | F5 and F9. Stories are items filed once at launch. Order still comes from the dependency graph, read once. |
| 2 | Re-derived for Judges only | F1. Review and QA keep their own contexts. Dev and fix fold into the Dev owner. |
| 3 | Rejected | F2. The Dev owner delegates each layer to a Helper. The per-layer test gate stays as evidence on the Readiness claim. |
| 4 | Re-derived; recycling rejected | F2 keeps one chain per story. Compaction handles overflow instead of a turn count (claim 30, A4). |
| 5 | Reshaped | F1 keeps a fresh Judge. The two turns become one Judge launch, which may spawn its own helpers. Confidence becomes the Finding's severity, and the Dev owner must still answer advisory items. |
| 6 | Reshaped | F7. Settlement stays mechanical. The resolution becomes a markdown Answer list. Reworks happen inside the Dev owner conversation. |
| 7 | Re-derived | The Ruling concept and invariant 9. |
| 8 | Re-derived | F1. Standards review and Behaviour check are the Judge variants. Tests are the Readiness claim's evidence. |
| 9 | Re-derived | The Dev owner is the wide seat. Custody is the machine. |
| 10 | Re-derived | F8. Silence stays the only cut. The Command cap becomes mandatory for Dev owner turns. |
| 11 | Rejected for Dev owner turns, with one exception (R7) | F2. A Dev owner turn runs with no reframe. A parse failure re-asks in the same session. A turn compaction can no longer shrink restarts from a rebuilt Brief and the Resume note (invariant 7). |
| 12 | Narrowed | F1. One Dev owner per story, plus Judges that must not share its view. |
| 13 | Re-derived | Invariant 6 and Delivery. |
| 14 | Re-derived | F5, F9 and the Launch set. |
| 15, 16 | Re-derived | F1 for the fresh Judge. Invariant 3 replaces the second review with a mechanical check. |
| 17 | Re-derived | F7. Markdown, because the same list appears in the story's report. |
| 18 | Re-derived | Invariant 7. |
| 19 | Re-derived | F8 and invariant 8. |
| 20 | Re-derived | Invariants 4 and 5. Freezing is now a property of every item, not of findings alone. |
| 21 | Re-derived | Invariants 3 and 10. |
| 22 | Re-derived | F9. The Worklist part, Route and invariant 11. |
| 23 | Re-derived; settling on return rejected | F9 keeps one store with kinds, and F4 keeps "active first". An item settled because its handler returned breaks invariant 12. |
| 24 | Re-derived, one level deep | F5 and F9. The Follow-up concept and invariant 14. A follow-up of a follow-up would let a run grow without end. |
| 25 | Re-derived | F5. The Selection concept and invariant 16. |
| 26 | Reshaped | F5. The mode goes. The epic and story choices become one Selection with three grains, and one epic becomes selectable. |
| 27 | Rejected (revised, R6) | Claim 28 and invariant 15. Setting an epic aside is a failure the run walks past. A stuck story holds the run at the Operator desk instead. |
| 28 | Re-derived | Invariant 15, and step 9 of the flow. Standing has no parked status. |
| 29 | Re-derived | Each slice in section 6 names the engine work it carries. |
| 30 | Re-derived | F2, the Resume note and invariant 17. |
| 31 | Rejected | Claim 28. An inconclusive QA lane goes to the Operator desk, and the story stays active. |
| 32 | Re-derived | Invariant 8. The Command cap is 1500 s, so the silence bound rises to 1800 s to stay above it. |
| 33 | Re-derived | R9. The judge and answer turns fold into the Dev owner turn, and one `check` state replaces their loops. |

### Open lookups

- **L1.** Does each harness emit stream events while a subagent works? If one does not,
  Liveness cuts a healthy Dev owner. Waiting on it: the silence bound for Dev owner turns.
- **L2.** Does the engine re-ask in the same session when a result fails to parse?
  Waiting on it: whether claim 11's rejection needs engine work.
- **L3.** Does an operator answer already resume the story's conversation? Waiting on
  it: whether Delivery is new.
- **L4.** How many apply laps does a story take today, and how often does review reach
  the operator gate? Waiting on it: the measure that shows the pilot helped.
- **L5.** Does opencode honour a command cap? Waiting on it: the Command cap adapter.
- **L6.** Can the engine's drain leave an item unsettled when its handler does not move
  it? Waiting on it: whether Route can ride the drain without breaking invariant 12.

### SOLID check

- **Single responsibility.** Every Owns reads without "and". Two Level 1 rows carry an
  "and" (Worklist, Custody). Each splits into separate concepts at level 2.
- **Open/closed.** A third Judge is one variant concept and one step in Route. Its
  findings are items of the existing finding kind, so the Worklist and Sign-off do not
  change. A new item kind is one row in the Kind table.
- **Liskov.** Standards review and Behaviour check are each a kind of Judge only.
- **Interface segregation.** Judge declares one thing: inputs in, findings out.
- **Dependency inversion.** Route names the Judge role and the item kinds. Settlement
  never knows which Judge wrote a finding.

## 5. Mapping onto the existing system

### Revision log

- **R1.** Section 4, L2 resolved: the engine already re-asks in the same session on a
  parse failure. Claim 11's rejection needs only `retries=0` on Dev owner turns.
- **R2.** Section 4, L3 resolved: an operator answer already resumes the story chain in
  review. Delivery moves from New to Exists.
- **R3.** Section 4, Command cap: the engine already has a per-profile cap, and the coder
  sets none. Command cap moves from New to Reshape.
- **R4.** Sections 1 to 4 and 6, the worklist: the user named it the cross-step todo list
  that dictates work (claim 22). Commission became the Worklist part, and the Story set
  became the Launch set inside it. Finding moved to Judgment as a value type. Frozen
  findings folded into Item (invariant 4). The Punch list became Sign-off, with Evidence
  check split from Settlement. Custody gained Route. Invariants 11 to 13, F9 and the
  shared-worklist pattern are new.
- **R5.** Sections 1 to 4, 6 and 7, launch and follow-ups: the user allowed the Dev owner to
  add follow-up work (claim 24), and set three launch grains through the params (claim
  25). F5 now asks for a visible extent, not a fixed one. The Worklist gained Selection,
  and the Dev owner gained Follow-up. Kind now governs filing as well as settling. Invariant 2
  covers follow-ups. Invariants 14 to 16, slice 5 and A11 to A12 are new, and QA moved
  to slice 6. Order moved from Exists to Reshape, because ostler hands out one story at a
  time.
- **R6.** Sections 1 to 7, no failed story: the user ruled that a run may not continue
  past a failed story, because a story is presumed feasible (claim 28). Standing lost
  its parked status. Invariant 15 became strict sequence, owned by Route. A stuck story
  and a spent Lap budget both hold the run at the Operator desk. Claim 27 moved from
  Narrowed to Rejected. The skip set and the epic set-aside became waste. A13 is new.
- **R7.** Sections 1 to 7, first review: a fresh reviewer checked the note against the
  code. The user ruled that missing engine support gets built (claim 29), and that
  compaction is expected (claim 30). The Dev owner gained the Resume note, and invariant 17
  is new. Invariant 7 now records the session handle as the turn starts, and restarts
  from a rebuilt Brief when compaction runs out. Claim 11's rejection gained that one
  exception. Invariant 16 fails a launch on an open dependency outside the launch set.
  QA's `give_up` became waste (claim 31). Evidence check moved from Exists to New, and
  Delivery from Exists to Reshape. The command cap is 10 minutes everywhere. Each slice
  now names its engine and ostler work, and slice 4's done-when split in two. Two
  citations were corrected.
- **R8.** Sections 1, 4, 5, 6 and 7, the command cap: the user set it to 25 minutes,
  because test suites run that long (claim 32). A running command emits no stream
  events, so invariant 8 needs the silence bound above the cap. The silence bound rose
  from 900 s to 1800 s. A hung Dev owner is now cut after 30 minutes of silence, not 15.
- **R9.** Sections 2, 5 and 6, one harness: the user ruled that the review, its triage
  and its fixes run inside the Dev owner's one turn, each through a subagent of the right
  strength (claim 33). The judge turn and the answer turn are gone, and so are their
  loops. The Dev owner returns its reviewer's findings verbatim, and the run files them under
  the turn's review prefix. One `check` state then records the plan, runs the gates, and
  has Sign-off settle the answers. Whatever failed goes back to the same session as one
  report, and a repair turn runs no new review. Route no longer drains findings through
  `self.pipeline`. One Lap budget of three repair turns covers the plan, the gates and
  the answers. The user dropped the rule that a helper never edits the work, so a fixer
  seat edits the files the Dev owner assigns it.
- **R10.** Sections 2, 5 and 6, one owner per lane: the user ruled that each lane has
  its own owner agent, and that no owner spans lanes (claim 34). Each lane now has the
  Dev owner's shape: one owner turn, one code `check`, and failures back to the same session
  as one report. Three repair turns are the Lap budget, and a spent budget or a block
  goes to the resolver, then the operator. QA's owner plans, runs, assesses, audits and
  repairs through its subagents. The `check` lints and dry-runs the plan, verifies the
  evidence, and runs the regression suites. A product defect leaves QA as a finding,
  and the main flow files it against the story for the Dev owner. The docs owner writes and
  reviews the book through subagents, and ostler's grounding gate is its `check`. The
  backlog drain gives each item one owner turn that fixes and QAs it, and the repo's
  gates are its `check`. The CI owner diagnoses, fixes and commits, and the push and
  the poll are its `check`. Every per-lane loop of repair turns, audits and triage
  turns is gone.

### Parts

| Part | Verdict | Where, and the mismatch |
|---|---|---|
| Worklist | **Reshape** (revised, R4) | `workhorse/workhorse/worklist.py` has the shape: items of many kinds in one store (15-24, 74-79), a claim that takes active items first (82-102), progress (174-191) and an atomic JSON file (218-231). The coder keeps no worklist on disk. It rebuilds a throwaway item list from ostler's queue at each pick (`coder/shared/queue.py:110-112`, `:220-229`), and picks the next story from disk after each one (`coder/main/flow.py:148-169`). |
| Dev owner | **Reshape** | The story chain exists (`coder/shared/conversation.py:7-14`). It is split across dev, review apply and fix turns, and reset at each service layer. |
| Judgment | **Reshape** | Review is a separate lane (`coder/review/flow.py:127-186`), but the verdict turn runs in no session and the feeder sits in its own chain. QA exists as a lane. |
| Sign-off | **Reshape** (revised, R4) | `ostler/ostler/edit.py:292-345` settles per finding. It reads JSON, and nothing checks that every reviewer finding has an entry. |
| Operator desk | **Exists** | `coder/shared/resolution.py` and `coder/shared/prompts/resolve-operator.md`. |
| Custody | **Reshape** | The pyflow engine's checkpoint and chains fit. Its silence bound is tied to the turn budget (`workhorse/workhorse/runner/ladder.py:126-130`). No state reads a worklist to pick its successor. |

### Concepts

**Worklist**

- **Item: Reshape (revised, R7).** `WorkItem` (`workhorse/workhorse/worklist.py:15-24`)
  has an id, a kind, a status, an order and a free payload. It has no digest, and
  nothing stops a payload edit, because `save` rewrites every row whole (218-231). The
  engine's `WorkItem` gains a `digest` over the payload alone, so a status or order
  change never trips it, and a `laps` count for the Lap budget. Both go into the engine,
  since any workflow would want them (the litmus test in `workhorse/AGENTS.md`).
- **Kind: Reshape (revised, R4).** `kind` and `_of_kind` exist (74-79). Nothing names
  who may settle a kind, and `mark` and `settle` accept any caller (271-298). The table
  lives in the coder workflow, and the coder's two status writers check it.
- **Selection: Reshape (revised, R5).** The coder takes `mode`, `story` and `epic`
  (`coder/main/flow.py:98-102`). Epic mode always works the whole queue from its front
  (`coder/shared/queue.py:89-130`), and `epic` only fills a label and a fallback
  (`coder/main/flow.py:119`, `:612-617`). The params become two:

  | Params | Files |
  |---|---|
  | none, or `epic=all` | every queued epic's open stories, epic by epic |
  | `epic=<name>` | that epic's open stories |
  | `story=<slug>` | that story alone, with no dependency check, as story mode does today (`coder/main/flow.py:141-144`) |

  `mode` goes. `epic` defaults to `all`. Naming both `story` and an epic other than `all`
  fails at launch with both values in the message, before any turn runs. "Open" means not
  done by ostler's own test (`ostler/ostler/select.py:100-103`).
- **Launch set: New (was Story set).** Resolved once at `start` (`coder/main/flow.py:138`)
  from the Selection, stored in the checkpoint and filed as story items, each carrying its
  epic.
- **Order: Reshape (revised, R5).** Epic order exists: `todo()` returns the queue
  front-first (`ostler/ostler/api.py:283-285`). Story order does not reach the coder. Ostler's
  API hands out one next story at a time (`ostler/ostler/api.py:272`), and its dependency
  sort, `dag_order` (`ostler/ostler/select.py:63`), stays internal. Ostler gains one API
  call that returns an epic's open stories in dependency order. The coder stores each
  position as the item's `order`. The engine's `order` is an int, so a follow-up filed
  right after its parent would renumber every later item. It becomes a float, and a
  follow-up takes a value between its parent and the next item.
- **Standing: Reshape (revised, R7).** The story's status bullet holds it today. The
  design holds it as the story item's status, with a `Scheme` (`worklist.py:55-63`)
  naming pending, active and done, and no blocked status. The finding kind's `Scheme`
  counts settled and declined as done, so `Scheme.done` takes a set of statuses. The
  coder writes the story's status bullet from the item when the story ends (invariant
  13). The skip set (`coder/shared/queue.py:240-249`) is dead code: only a test writes
  it (`workflows/tests/coder/test_workflow.py:489`). It, the blocked-epics file and
  `flag_epic_blocked` (`coder/shared/queue.py:30-32`, `133-168`) are waste under claim
  28.
- **Amendment: Reshape.** `replan` (`coder/main/flow.py:288-306`) rewrites the epic, then
  re-selects from disk. The design re-files story items only there, with the operator's
  answer as the trigger.
- **Progress.** The run's labels read `progress` from the last story pick
  (`coder/main/flow.py:117-129`). They read the Worklist's snapshot instead. The
  engine's `counts` covers one kind or every kind, and every kind includes findings. It
  gains a set of kinds, so progress counts stories and follow-ups together.

**Dev owner**

- **Dev owner conversation: Reshape.** `story_chain` exists. Three things break invariant 7:
  `dev implement` resets it at each layer (`coder/dev/flow.py:229-231`), `spend_turn`
  recycles it after 8 turns (`coder/shared/conversation.py:17-25`), and default retries
  reframe it into a fresh session (`workhorse/workhorse/runner/ladder.py:218-230`).
  The engine adds three more gaps:
  - It records the session id only when a turn ends, overflows or spends its output
    budget (`workhorse/workhorse/runner/failure.py:232-267`). A silence cut or a crash
    resumes the session before it, and a first turn restarts blank on a dirty worktree.
    Every backend records the session id when the stream starts.
  - An unresumable session re-sends the same prompt in a fresh session
    (`ladder.py:248-262`). `agent()` gains a `rebrief` callback that this path calls
    instead.
  - When compaction attempts run out, the ladder falls back to reframe
    (`ladder.py:286-293`). A Dev owner turn calls `rebrief` there too.
  Claude keys sessions by working directory, so every Dev owner turn of a story runs in one
  fixed directory.
- **Resume note: New (R7).** Nothing renders the run's state into a prompt. After a
  compaction the ladder re-sends the turn's own prompt (`ladder.py:269-285`), so the
  note survives only if the prompt carries it. Claude's own compaction inside a long
  turn re-sends nothing, which is why the note names the worklist path.
- **Brief: Exists.** The plan prompt and its args (`coder/dev/flow.py:73-91`).
- **Helper: New.** No coder prompt asks the Dev owner to delegate. It lands in the Dev owner's
  prompts under `coder/dev owner/prompts/`, not in machine code.
- **Readiness claim: Reshape.** The per-layer gates (`coder/dev/flow.py:243`) run after
  each implement turn. The design runs them once after the Dev owner's claim.
- **Follow-up: New (revised, R5).** The nearest thing today is a defect filed onto the
  backlog (`coder/shared/paths.py:60-62`), which no later step of the same run reads. The
  Dev owner's turn result gains a list of follow-ups, and a coder node files each one with
  its parent's epic and an `order` between the parent and the next item.

**Judgment**

- **Judge role: New** as a name. Both lanes already follow it in shape.
- **Standards review: Reshape.** Two turns (`coder/review/flow.py:133`, `:164`) become one
  launch. The verdict's `approved` status no longer routes. Settlement routes instead.
- **Behaviour check: Exists.** The QA lane, unchanged by this note.
- **Judge inputs: Exists.** Review gets story, diff and repos as args, and starts from a
  reset chain (`coder/review/flow.py:131-147`).
- **Finding: Exists.** `ReviewFinding` with confidence. It becomes a finding item's
  content. Today findings pass as prompt text (`findings_block`,
  `coder/review/flow.py:64`), and nothing is written to disk before the fixer sees them.

**Sign-off**

- **Answer: Reshape, with ostler work (revised, R7).** `review-resolution.json`
  (`coder/shared/review.py:15`). It becomes a markdown list, one entry per finding item
  id. No parser for that list exists, so ostler gains one.
- **Evidence check: New (revised, R7).** `_verify_finding`
  (`ostler/ostler/edit.py:228-254`) checks only spec-dir artifacts and JSON pointers.
  The Dev owner writes those files, so it would author its own evidence. A coder node checks
  what the Dev owner cannot fake: a commit sha, a code path in the diff, or a gate test name
  in the gate's output.
- **Settlement: Reshape (revised, R7).** `settle_review` (`ostler/ostler/edit.py:292`)
  writes a ledger of verified, open and blocked ids (326-332) from the resolution's own
  findings. It must answer for the filed set instead. A coder node reads the ledger and
  sets each finding item's status, and a filed finding with no entry stays open. That
  gap is the one that lets a fixer drop a finding today. Two more mismatches:
  `settle_review` accepts only `addressed` and `blocked` (312-322), and it writes the
  story's status into `story.md` (335-344), which breaks invariant 13. It gains a
  `declined` disposition and a ledger-only mode with no status write. Ostler keeps
  knowing nothing about the worklist.

**Operator desk**

- **Question, Ruling, Escalation: Exists.** `coder/shared/resolution.py`.
- **Delivery: Reshape (revised, R7).** `apply_resolved` resumes the story chain
  (`coder/review/flow.py:281-290`). The answer then lives only in that conversation,
  so a compaction can drop it. Delivery also appends each Question and its answer to an
  answer log in the run directory, which the Resume note renders.

**Custody**

- **Checkpoint: Exists.** `PyflowCheckpoint` (`workhorse/workhorse/records.py:40`),
  read back on resume by `read_resume` (`workhorse/workhorse/pyflow/driver.py:37`).
- **Session handle: Reshape (revised, R7).** The engine resolves a chain's session from
  disk (`workhorse/workhorse/pyflow/engine.py:277-282`). When it records the id is the
  gap, under Dev owner conversation above.
- **Route: New (revised, R4).** Each coder state names its successor, and the review lane
  loops on its own counter (`MAX_REVIEW_REWORKS`, review flow `_guard`). Route rides the
  engine's drain, `self.pipeline` (`workhorse/workhorse/pyflow/workflow.py:246-275`): it
  claims the story's open finding items, runs the Dev owner's answer turn, and comes back into
  the same state. Settlement moves each item. A finding it leaves open is claimable again
  on the next visit, which resumes the Dev owner. That loop is the rework lap, and the Lap
  budget bounds it. Two engine gaps stand in the way of invariant 15 and the Lap
  budget:
  - The claim skips an item whose status is blocked and takes the next one
    (`worklist.py:95-102`), and the drain keeps a blocked verdict from its handler
    (`pyflow/workflow.py:256-274`). The claim gains a strict mode that returns nothing
    while any earlier item is not done.
  - `revisit` re-enters with the same params (`pyflow/engine.py:152-162`), so a lap
    counter kept in params never advances. The count lives on the item as `laps`, and
    the drain increments it.
  Route also replaces the epic boundary: today the run opens an epic's
  pull request when ostler reports no story left (`coder/main/flow.py:165-167`, `:435`).
  Route opens it when the epic's last item settles done. A story that cannot run sets its
  whole epic aside today (`coder/main/flow.py:168`), and the run moves to the next epic.
  That breaks claim 28, and `workflows/AGENTS.md` already forbids a run that gives up.
  Under invariant 15 the run waits at the Operator desk instead. QA's `give_up` fails
  the run on an inconclusive lane (`coder/main/flow.py:280-281`, `:308-331`). It goes
  the same way.
- **Liveness: Reshape.** The watchdog cuts on silence (`workhorse/workhorse/runner/process.py:114-152`).
  The silence bound is `max(turn budget, 900 s)` (`ladder.py:126-130`), so it is tied to
  the turn budget. With the default 3600 s budget a quiet turn runs an hour before the
  cut, and an unbounded budget disables the watchdog. The design needs a silence bound
  that a node sets apart from its budget: unbounded budget, 1800 s silence. No caller can
  set one today. `AgentNode` has no silence field (`workhorse/workhorse/runner/spec.py:16-27`),
  so a `silence` parameter threads through `Workflow.agent`, the engine's `agent`,
  `AgentNode` and the ladder's `_render`.
- **Command cap: Reshape (revised, R3).** `AgentProfile.command_timeout_s`
  (`workhorse/workhorse/runner/backends/__init__.py:40-54`) sets it for the claude
  backend only (`claude.py:182-188`), and only for the Bash tool. The coder passes no
  profile. The Dev owner gets one with a 1500 s cap. A Helper's own commands sit under the
  silence bound alone, which is why L1 gates slice 2.
- **Lap budget: Reshape (revised, R7).** `MAX_REVIEW_REWORKS` and the QA caps exist.
  The count moves onto the item, under Route above.
- **Long job: Exists.** `workhorse.job`.

### What the existing system has that the design lacks

- **The docs lane between review and QA.** A concept the design missed: the book must
  match the code before QA reads it. It stays a step in Route, out of scope here.
- **The fix lane draining a backlog across stories.** Out of scope. Items owned by the
  active story go to the Dev owner.
- **The defect backlog** (`coder/shared/paths.py:60-62`,
  `coder/shared/schemas/backlog.py`). A second todo list with its own pick, prune and mark
  scripts. The design keeps it out because it outlives the run. (A9)
- **QA's per-scenario fix list** (`FixWorklist`, `coder/shared/schemas/qa.py:426-435`).
  It lives in state params, so the dashboard cannot see it. Its rework counter resets at
  each pop (`popped`, 433-435). Each failed scenario is a finding the design already has.
  It becomes a finding item from the Behaviour check in slice 6, and the Lap budget
  replaces its counter.
- **The dev plan's block-repair and path-repair worklists** (`coder/dev/nodes.py:48-62`).
  Waste. They are session-chain names with no items, and the Dev owner repairs its own plan in
  its conversation.
- **`poll_feedback`, a human note dropped mid-review.** A concept the design missed. It is
  an Answer source for the Dev owner, and it routes through Delivery.
- **Confidence split into must-fix and advisory.** Waste under invariant 3, since the
  Dev owner answers both. The severity stays on the Finding.
- **The verdict turn's `approved` status.** Waste. A Judge with no findings settles
  trivially.
- **QA's `give_up` and the `qa-give-up` failure.** Waste under claim 28. An inconclusive
  QA lane goes to the Operator desk, and the story stays active.

### Lookups

- L1: unresolved, and slice 2 waits on it. Claude Code writes subagent sidechains to
  disk (`workhorse/workhorse/runner/transcript.py:24`). Whether the stdout stream
  carries them is not visible in this repo. (A1)
- L4: unresolved. Needs a count over recent run records. (A2)
- L5: unresolved. Only the claude backend reads the cap. (A5)
- L6: resolved. The drain settles an item its handler left active to the status the
  caller names (`workhorse/workhorse/pyflow/workflow.py:269-274`), and an item the handler
  moved keeps its status. Route passes `open`, so a finding nobody settled reopens and
  never passes as done. No design change.

## 6. Slices

1. **Review settles in one pass.** Touches Item, Kind, Finding, Answer, Evidence check,
   Settlement, Route and the Standards review. The run gets its worklist file. Stories
   are not items yet, so each finding item carries the id of the story under review.
   The reviewer's findings are filed as finding items with a digest. The apply turn
   writes a markdown Answer list. Settlement sets each item's status from ostler's
   ledger, and a filed finding with no answer stays open. `apply_resolved` stops
   returning to the review's `start` (`coder/review/flow.py:308`), so an operator
   answer leads to settlement, not to a second review. Dev and QA stay as they are.
   - Engine: `WorkItem` gains `digest` and `laps`. `Scheme.done` takes a set of
     statuses. The drain increments `laps`.
   - Ostler: a parser for the markdown Answer list. `settle_review` gains a `declined`
     disposition and a ledger-only mode.
   **Done when** one real story runs through review with every finding item settled or
   declined and no second reviewer turn, and tests show a dropped finding staying open,
   an edited finding failing its digest, and evidence the Dev owner wrote itself failing the
   Evidence check.
2. **The Dev owner owns dev.** Touches Dev owner conversation, Resume note, Helper, Readiness
   claim, Delivery, Command cap and Liveness. It starts once L1 is answered. One Dev owner
   turn plans and builds every layer with helpers, with `retries=0`, an unbounded
   budget, an 1800 s silence bound and a 1500 s command cap, in one fixed working
   directory. Every Dev owner prompt opens with the Resume note, and every operator answer
   goes onto the answer log. The gates run once on the claim.
   - Engine: every backend records the session id when the stream starts. `agent()`
     gains a `rebrief` callback, called when a session cannot resume and when
     compaction runs out. A `silence` parameter threads from `Workflow.agent` to the
     ladder.
   **Done when** one real story goes from plan to green in one conversation, and the
   run log shows no reframe and no layer reset. A test kills a first Dev owner turn mid-stream
   and shows the resume taking the same session id. A test forces compaction to run
   out and shows the restarted turn's prompt carrying the Resume note with an earlier
   operator answer.
3. **Review answers go to the Dev owner.** Needs slice 2. Touches Delivery, Route and the
   Dev owner conversation. Route resumes the slice 2 Dev owner on the open finding items, in
   place of slice 1's apply turn. **Done when** the review's Answer list is written by
   the same session id that planned the story.
4. **The run knows its stories.** Touches Selection, Launch set, Order, Standing,
   Amendment and Route. The `mode` param goes, and `epic` and `story` select the grain.
   Stories become items on the same worklist, and finding items hang off them. QA's
   `give_up`, the skip set and the epic set-aside go, and a stuck story goes to the
   operator gate.
   - Engine: the claim gains a strict mode. `counts` takes a set of kinds.
   - Ostler: one call returns an epic's open stories in dependency order.
   **Done when**, for the launch, three launches on one repository show their full
   count from the first state, read from the worklist: `epic=all` counts every queued
   epic's open stories, `epic=<name>` counts that epic's, and `story=<slug>` shows
   "0 of 1". Each run ends after its last item without reading the queue again. A run
   killed mid-story resumes on that story. A launch with an open dependency outside its
   launch set fails before any turn runs.
   **Done when**, for a stuck story, a test drives a Dev owner that gives up and a QA lane
   that ends inconclusive. Each holds the run at the operator gate, no later story
   starts while it waits, and the answer resumes the same Dev owner on that story.
5. **The Dev owner files follow-ups.** Touches Follow-up, Kind, Order and Route.
   - Engine: `order` becomes a float.
   **Done when** a follow-up filed mid-story turns "1 of 3" into "1 of 4" at once, runs
   right after its parent in the parent's Dev owner conversation, and passes the same
   Judges. No other item's `order` changes. A test shows a follow-up's own follow-up
   landing on the defect backlog instead of the worklist.
6. **QA answers go to the Dev owner.** Touches Behaviour check as a second Judge variant.
   Failed scenarios are filed as finding items. **Done when** a QA finding item is
   answered in the Dev owner conversation and settled by the same Settlement.

Slices 1 and 2 each need an attended run on a real story twice before they become
workflow code (aim 9). The attended run is the first step of each slice. (A3)

## 7. Assumptions

**A1.** *Assumption:* Claude Code emits stream events to stdout while a subagent works.
*Decided:* Dev owner turns rely on silence alone, with an 1800 s bound. *Basis:* none in this
repo. Sidechains are written to disk (`runner/transcript.py:24`), which suggests the
events exist. *If wrong:* Liveness needs a second signal, such as transcript file growth.
Re-derive F8, Liveness and slice 2.

**A2.** *Assumption:* Review ping-pong costs enough to show in one story. *Decided:*
slice 1 goes first. *Basis:* the user's report. No run record was counted. *If wrong:*
slice 2 goes first, and slice 1's done-when needs a baseline count of apply laps.

**A3.** *Assumption:* An attended session can carry a real story from plan to green in
one conversation. *Decided:* slice 2 starts attended. *Basis:* aim 9, and the user's
experience with dev owner agents. *If wrong:* the Dev owner conversation cannot hold a whole
story, and claim 3 (per-layer sessions) returns. Re-derive F2 and the Dev owner part.

**A4.** *Assumption:* Compaction plus the Resume note keeps a long Dev owner conversation
useful, so recycling after 8 turns is unnecessary. *Decided:* drop `spend_turn`
recycling for Dev owner turns. Compaction is the expected path (claim 30), and everything the
Dev owner must keep is on disk (invariant 17). *Basis:* the engine compacts on overflow
(`ladder.py:269`). How much a compacted Dev owner forgets beyond the Resume note is not
measured. *If wrong:* the Dev owner repeats work it already did after a compaction, and the
Resume note grows to carry what each lap changed. Re-derive the Resume note.

**A5.** *Assumption:* The pilot runs on the claude backend. *Decided:* the Command cap
adapter exists for claude only. *Basis:* `claude.py:182-188` is the only reader of the
cap. *If wrong:* opencode needs its own adapter before slice 2. Re-derive the Command cap.

**A6.** *Assumption:* A resumed Dev owner conversation costs less than the narrow turns it
replaces. *Decided:* one conversation per story. *Basis:* prompt caching on resume, and
2.7M context per repair turn measured on another workflow. *If wrong:* a cost cap per
story joins the Lap budget. Re-derive F2.

**A7.** *Assumption:* Stories selected at launch stay valid for the run, apart from an
operator-approved replan. *Decided:* the Launch set is fixed in the checkpoint. *Basis:*
the user's idea 2. *If wrong:* the Worklist re-reads the disk on a trigger. Re-derive F5
and invariants 1 and 16.

**A8.** *Assumption:* A fix pass needs no second review, because tests and QA run after
it. *Decided:* one review per lap. *Basis:* claims 15 and 16. *If wrong:* a fix pass
that adds defects slips past review. A narrow re-review of the fix diff joins the
Standards review. Re-derive invariant 3 and slice 1.

**A9.** *Assumption:* One worklist per run is enough. A story's status and the defect
backlog are the only state that must outlive a run, and both stay in the docs tree.
*Decided:* the worklist file lives in the run directory, and the story's status bullet is
written from its item when the story ends (invariant 13). *Basis:* the backlog already
outlives runs (`coder/shared/paths.py:60-62`). *If wrong:* two runs on one repository
need to see each other's open work, and the Worklist moves into the docs tree. Re-derive
Standing, invariant 13 and A7.

**A10.** *Assumption:* A run's worklist stays small enough to rewrite whole on each
change. *Decided:* a plain JSON file with no storage port. *Basis:* tens of stories with
tens of findings each. The engine's JSON store writes atomically
(`workhorse/workhorse/worklist.py:218-231`), and the author survey already runs on it
(`author/shared/survey/units.py:43`). *If wrong:* item writes need an append log.
Re-derive the Worklist pattern.

**A11.** *Assumption:* A Dev owner files a few follow-ups per story, and they need no
follow-ups of their own. *Decided:* follow-ups go one level deep, and deeper work goes to
the defect backlog. Nothing caps the count per story. *Basis:* none. No run has filed a
follow-up yet. *If wrong:* a run grows faster than it finishes, and a follow-up budget
per epic joins the Lap budget. Re-derive invariant 14 and slice 5.

**A12.** *Assumption:* "In order" means the epic queue front-first, then each epic's
stories by dependency. *Decided:* Order sorts that way once, at launch. *Basis:* the run
works the queue front-first today (`coder/shared/queue.py:89-130`), and ostler's
`dag_order` already sorts an epic's stories (`ostler/ostler/select.py:63`). `dag_order`
drops a dependency outside the epic (74-75), so the launch checks those itself
(invariant 16). *If wrong:* stories often depend on a later epic's stories, launches
fail often, and Order needs a sort across epics. Re-derive Order and invariants 15 and
16.

**A13.** *Assumption:* Every selected story is feasible, and an operator answer is
enough to unblock any Dev owner. *Decided:* the run has no failed state for a story. A story
the docs stamp blocked from an earlier run is selected like any open one. *Basis:* the
user's ruling (claim 28), and `workflows/AGENTS.md`, which already forbids a run that
gives up. *If wrong:* one infeasible story holds the whole run at the gate until the
operator rewrites it through Amendment. Re-derive Amendment and invariant 15.
