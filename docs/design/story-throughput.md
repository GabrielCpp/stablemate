# A story coded in hours, not days

> **Disclosure.** I read the existing solution before this design started. That covers the
> coder workflow's main, dev and QA flows, its commit check, its follow-up filing, the QA
> evidence gate, the QA agent's prompt, and the live run of the `acme` epic this note
> measures. I also answered that run's gates. Each decision that reached me through them is
> a claim in section 1b.

## 1. Problem

**Who feels it.** The operator who hands an epic to the coding workflow and waits for its
stories. On the `acme` epic, story 2 took 26 hours and story 3 more than 12. At that pace
the 11 stories left need about 6 days. The operator's verdict: "a 3.4H QA loop and 4k per
story is unreasonable cost for the gain."

The dollars are smaller than the dashboard shows. The dashboard sums each session's
running total once per report, so it counts the same spend many times. It shows $1425 for
the run. The per-session deltas add up to about $239, about $95 a story (A4). The hours are
real, and they are the problem.

The time does not go into checking the product. The QA phase spent 22.8 hours over 26
turns. Running scenarios took 3.5 of them. The rest went into an agent that plans its own
tests, writes scenario code and fixtures, runs scenarios one by one until they pass, and
sends auditors on the strongest model to refute its own verdict. Another 6.6 hours passed
with the run dead and nobody told (A6). Of the 26 turns, 13 reported the same single
product defect, which the builder never saw because it read the wrong work list. Most of
the other 13 had already passed and were sent back by a gate or by the commit check.

**Done looks like this.**

- A story goes from start to commit in at most 4 hours of wall time, measured on the next
  story of the live epic. Today: 12 to 26 hours.
- A story costs at most $100 by per-session deltas, and the dashboard shows that same
  figure. Today: about $95, shown as about $570.
- A story that passes has every acceptance criterion proven on the committed revision, by a
  scenario, a repo test or a static rule.
- A defect an end user would meet turns a check red before commit, including one nobody
  wrote a criterion for.
- A defect found after its story committed counts as an escape against that story's
  claims and walk. Escapes are on record per story, and the target is 0.
- A product defect reaches the builder on the next lap after it is found. Today one defect
  was found 13 times.
- A defect that comes back in a new form is recognised as the same cause.
- An edit after a pass reruns only the proof it can change. A one-line metadata edit
  reruns nothing.

**Out of scope.**

- The dashboard server itself: a second process, and its rewrite.
- The model choice per seat beyond the power each seat asks for.
- Writing the book for a repo that has none. The proof here runs on books that exist.
- Book runs' own repair loop, covered by `okf-repair-churn.md`.
- Naming the mobile app's controls. It changes the adopter's app, so it ships as a story in
  the `mobile-app` repo. Only the reach baseline stays here, in Proof.
- Chores: the two parked aliases, the `arrange:` wording, the mobile repo's empty prompts
  glob, the library listing merging same-name entries. Each lands as its own commit.
- The book-writing method itself. Assumption 1 tests whether the book catches what an end
  user meets. A miss opens its own note on the book method before slice 1 starts.

## 1b. Claims

1. "Fix the commit bounce so a metadata-only change skips the QA rerun." (step-back report)
2. A path rule decides whether a bounced commit reruns QA: product paths rerun, story
   metadata does not. (my own unreviewed edits in a scratch worktree)
3. "I suspect the routing decision could be ask to an agent without tool at power low."
   (the operator)
4. "Qa technically do not even need an agent as scenarios get compiled and run by
   themself." (the operator)
5. "The dev and review steps did a bad job at finding issues. Maybe some method skills
   could them help them." (the operator)
6. "Add the 'unreachable' outcome to the evidence gate." (step-back report)
7. "Dedupe follow-ups by title at filing; attach the orphaned findings to an item."
   (step-back report)
8. "Block on `groom wait --until blocked` per run instead of 30-minute feed monitors."
   (step-back report)
9. "Label the 80 controls in the app's TestId helper." (step-back report)
10. The QA agent writes and repairs its own plan, and a fresh auditor on the strongest
    model tries to refute it each turn. (the QA prompt)

## 1c. The whole

The purpose this serves is `docs/CONSTITUTION.md`. Aim 1: everything it claims, it can
show. Aim 2: the judgment comes from somewhere the work did not. Aim 3: every capability is
covered by a check that can tell success from failure. Aim 4: every finding gets an answer.
Aim 8: a lap that leaves the gates where they were asks upward. Aim 9: a workflow records a
process that already worked. The workflows bar: it executes daily development work without
supervision, and it rejects a fix that needs a person to notice something. The people are
the operator of an unattended run and the end user of the product it builds.

A story's journey, one box per phase:

```
story ──> write claims ──> build ──> document ──> prove ──> user walk ──> commit ──> next story
                             ^           ^          │  │                    │
                             │           │          │  └─ gate invalid ─> prove
                             │           │          └──── red ─────────> build | book owner | upward
                             └───────────┴──────────────── dirty tree ──> scope
                                                 findings ──> fix lane ──> build
                                       any phase ──> gate ──> operator ──> same phase
                                       run dies  ──> operator ──> resume
```

Every arrow that points back is a **return edge**. The recorded epic lost laps on three of
them, and a replay of the recorded laps (A5) shows two shapes, not one.

| Return edge | Defect | Laps lost | Inputs moved | Shape |
|---|---|---|---|---|
| red → build | Builder read an empty work list | 11 | no, same tree and same findings | unmoved lap |
| gate invalid → prove | No unreachable outcome, and the stack wiped twice | about 4 | yes, the failing set shrank 10, 2, 0 | wrong owner |
| dirty tree → build | Metadata edit sent the story back | 1 full lap | no product file | wrong owner |

An **unmoved lap** runs on the inputs of the last lap and cannot change the outcome. A
**wrong owner** lap goes to a phase that cannot fix the cause: a builder handed a book or
stack defect, or a full rerun handed a metadata edit. Fixing each defect on its own edge is
the siloed fix. Two whole-level rules cover every edge at once:

- Invariant 9: a lap whose inputs match the last lap does not run, and the second lap that
  leaves the outcome where it was asks upward.
- Invariant 11: every return edge routes by the side the cause sits on, and only a product
  cause reaches the builder.

A third rule catches the defect that comes back in a new form: invariant 5 keys a finding
on the assumption it broke, not on its wording.

## 2. Parts and concepts

### Level 1: parts

1. **Proof.** Owns what a story must prove and the run that proves it: the claims, the
   compiled scenarios, the scope of a run, the walk an outsider takes as a user, and the
   verdict. Never knows how the code was written or who reads the verdict. Hands a verdict
   to Building and to Findings.
2. **Judgment.** Owns cheap decisions that need reading but no action: are these two
   findings the same cause, which item owns this finding, which side a red scenario sits
   on. Never knows the run, the files on disk or the workflow's routes. Hands an answer to
   whoever asked.
3. **Building.** Owns turning acceptance criteria into code and checking it before
   handoff. Never knows how the proof is compiled, and never edits the book or the
   scenarios. Hands a revision to Proof and receives findings from Findings.
4. **Findings.** Owns each defect from first report to close: its cause, its owner, its
   delivery to the builder, and whether it escaped the story that shipped it. Never knows how a defect was found. Hands open findings to
   Building and settled ones to the operator's view.
5. **Attendance.** Owns what the operator sees and is asked: gates, standing, stalls,
   liveness of a run, and spend per story. Never knows a story's content. Hands gates to
   the operator and answers back to the run.

**Flow.** Before the build, Proof writes the story's claims from the story and the book.
Building hands a revision to Proof. Proof scopes the claims the revision can change and
runs their compiled scenarios. A red scenario goes to Judgment for its side. A product side
becomes a finding and goes back to Building. A book side goes upward with its evidence. A
stack side goes to the stack step, and upward if it repeats. On green, an outsider walks the
story as a user, and each defect the walk meets becomes a claim and a red. Findings asks
Judgment whether a new defect is a cause it already holds. Attendance watches every moment
and spends nothing unless a gate opens or the run stops.

Test of the split. Someone who has not seen the code writes down what the user must see.
A builder writes the code. A test run proves it, and only what changed gets retested. An
outsider tries the feature as a user would. A cheap reader settles small questions. A
ledger keeps each cause once and makes sure the builder sees it. Someone watches the clock,
the bill and whether the run is still alive. A different code base with a different test
runner fits this split as well.

### Level 2: concepts

**Proof**

| Concept | Owns | Never knows |
|---|---|---|
| Claim author | Writing the story's new claims from the story's intent and the book, before the build | The diff and the code (aim 2) |
| Coverage map | Which claim, repo test or static rule stands for each acceptance criterion | How each is run |
| Proof scope | The claims a change can affect | Why the change was made (Building) |
| Scenario | A compiled, runnable check of one claim | Who wrote the claim |
| Proof run | Running a set of scenarios against the stack once | Which set, and why |
| User walk | One outsider's pass over the running story as its user, with the story and the book only | The diff, the code and the claims' scenarios |
| Verdict | Per criterion: proved, failed or unreachable, with the evidence | What happens next (Findings) |

The Reach baseline, the count of claims a check cannot address on a device, is a field of
the Verdict.

**Judgment**

| Concept | Owns | Never knows |
|---|---|---|
| Question | A closed question with its inputs inlined and its allowed answers | Who asked |
| Judge (role) | Answering a question from its inputs alone | The variants behind it |
| Rule judge (variant) | Answering by a fixed rule over the inputs | Model calls |
| Reading judge (variant) | Answering with one model call, no tools, no files | Any input not inlined |

**Building**

| Concept | Owns | Never knows |
|---|---|---|
| Acceptance walk | Tying each criterion to the code that meets it before handoff | The proof's scenarios |
| Self-check | Running the repo's own tests and the scoped proof before handoff | The final verdict |
| Revision | The committed state handed to Proof | How it was reviewed |

**Findings**

| Concept | Owns | Never knows |
|---|---|---|
| Finding | One defect: the assumption it broke, where, and the evidence | Which lap found it |
| Cause identity | Deciding a new report breaks an assumption a finding already holds | How the report was produced (asks Judgment) |
| Ownership | Attaching each finding to the one item that must fix it | The item's code |
| Delivery | Putting every open finding the builder owns into the builder's next brief | The brief's other content |
| Escape record | Counting a defect found after its owning story committed against that story's claims and walk | Who found it: a later story, the operator or a user |

**Attendance**

| Concept | Owns | Never knows |
|---|---|---|
| Gate notice | Telling the operator a gate opened, at once, on record when the push fails | The answer |
| Standing | What the run is doing now, true even during a silent step | The step's content |
| Stall rule | Asking upward when a lap on a return edge runs on unmoved inputs or leaves the outcome where it was | What the phase does, and normal repetition such as one gate per service |
| Liveness | Telling the operator a run stopped beating, and ending a call silent past its budget | Why it stopped |
| Spend ledger | Hours and dollars per story and per phase, from per-session deltas | Which phase is wasteful |
| Attendant rules | What an agent attendant may never do: skip hooks, push, branch, enforced by a hook | The fix it is making |

Shared value types: a Finding crosses Proof, Findings and Building as one value. A Question
and its answer cross Judgment and its askers as one value. The Verdict's three outcomes are
a value type Findings and Attendance read. A side (product, book, stack) is a value type
Judgment answers and every return edge reads.

## 3. Invariants

1. **A passed story has every acceptance criterion proven on its committed revision.**
   Owner: Verdict. Upheld by Coverage map and Proof scope. A criterion with no claim, no
   repo test and no static rule in the map fails the verdict.
2. **Only a change confined to an explicit list of inert paths skips the rerun.** Owner:
   Proof scope. A change to a cited file reruns the claims that cite it. Any other change
   reruns the story's whole proof. A lockfile, a fixture, a migration or a config is never
   inert.
3. **A Reading judge may only add work, never remove it.** Owner: Proof scope for scope,
   Verdict for sides. A wrong answer then costs a rerun or an ask upward, never a missed
   proof.
4. **An unreachable outcome never passes.** Owner: Verdict. It parks the story for the
   operator with its reason and the evidence the build did not produce.
5. **A cause appears once in the ledger, however many runs report it and in whatever
   words.** Owner: Cause identity. A finding closes only when a claim that catches the
   whole class sits in the book.
6. **Every open finding has exactly one owning item, and that item's next builder brief
   lists it.** Owner: Delivery. Upheld by Ownership. One owner per cause, not per symptom.
7. **A run that stops beating reaches the operator within 5 minutes, and no model call
   outlives its silence budget.** Owner: Liveness. A killed call resumes from its
   checkpoint.
8. **Every story's hours and dollars are on record when it closes, and the view shows the
   recorded figure.** Owner: Spend ledger.
9. **No lap on a return edge runs on inputs identical to the last lap, and the second lap
   that leaves the outcome where it was asks upward.** Owner: Stall rule. Inputs are the
   digests of what the phase reads: the revision's scoped files, the open findings in the
   brief, the claims in scope. Upheld by Proof scope and Delivery, which produce those
   inputs. A red on the stack side asks upward. It is not refused as a lap with identical
   inputs.
10. **What judges a story is written from inputs the story's build did not produce, and
    stays so to the end of the story.** Owner: Coverage map. The criteria come from the
    story, the claims from the Claim author. The proving run reads the book as it stood
    when the story started, plus the Claim author's claims. A book change during a story
    parks upward.
11. **A red reaches the builder only on the product side.** Owner: Verdict. Product is the
    default side. The book side needs evidence the build did not produce: the claim
    contradicts a story criterion, or it already failed on the base revision. The stack
    side goes to the stack step once, then upward.
12. **A claim the story adds counts only when it runs red on the base revision and green on
    the head.** Owner: Verdict. A claim green on both proves nothing about the story.
13. **Every defect found after its story committed is recorded as an escape against the
    story whose pages it sits on, and the second escape on one story's pages asks upward
    for a review of the book method.** Owner: Escape record. Upheld by Cause identity,
    which places the defect, and by Ownership. The escape closes only with the claim that
    would have caught it (invariant 5).

## 4. Forces and patterns

**Forces**

- F1. The proof must stay as strict as today while costing a fraction. Scenario runs are
  15% of QA wall time, so the agent is the cost, not the checks.
- F2. Most changes after a pass touch a few files, and the book's citations already name
  which claims read which files. They cite 89% of the product files this epic changed.
- F3. Some changes touch files no claim cites: fixtures, a migration, a makefile. A
  skipped rerun on one of them changes behaviour unproven.
- F4. The questions that need reading are small, closed and frequent: same cause or not,
  which item owns it, which side a failure sits on. A tool-using agent at high power is
  priced for open work.
- F5. The judge must be swapped in a test for a fixed rule, so routing tests need no model.
- F6. The defect that cost 11 laps was never shown to the builder. Delivery is the lever.
  Builder skill comes second.
- F7. Some acceptance criteria no book claim can observe: work kept off the main thread,
  no new database object. In this epic 14 of 139.
- F8. The operator answers gates by hand and pays per hour of stall.
- F9. A book written from the code passes the code's own defects. Only claims written from
  the story's intent, and a walk by someone who never saw the code, see what the user sees.

**Between parts:** one value handed along. Revision to Proof, Verdict to Findings, Finding
to Building. Judgment is a port that Proof and Findings call (F5).

**Inside the parts**

- Claim author: one seat per story before the build, with the story and the book (F9). Its
  claims state what the user sees after an action, the error path, and what must not
  happen.
- Coverage map: a value written by the Claim author and checked by a rule (F7). A criterion
  no claim can observe maps to a named repo test or a static rule over the diff.
- Proof scope: a plain function from the change, the citation index and the inert list to a
  set of claims (F2, F3). It asks no judge.
- Judge: a role with two variants, Rule judge and Reading judge (F4, F5). The workflow
  picks the variant per question where it assembles itself. Tests pick the Rule judge. The
  Reading judge runs at low effort on the middle model tier with no tools, the inputs
  inlined in its prompt, and a typed answer (A3).
- Proof run, Scenario, Verdict: plain functions over what the compiler produces (F1). No
  agent runs on a green proof. On a red one, the Judge names the side. The stack step is a
  plain function, and only a stack that stays red goes upward.
- User walk: one seat per story after a green proof, on the running stack, at medium power
  (F9). It ends the story or files findings. Each finding carries the claim that would
  have caught it.
- Acceptance walk: a method skill on the builder (F6, claim 5). It costs one section of
  the builder's turn.
- Cause identity and Ownership: Judge questions (F4). Delivery is a plain function.
- Gate notice: a blocking wait per run that returns on a gate, and finds the dashboard
  even when it started after the run (F8).
- Liveness: a beat the dashboard checks, and a deadline on each model call (F8).

**Claims**

- Claim 1: re-derived from F2 and F3. The scope is computed, and only an inert path skips.
- Claim 2: rejected as the decision. A list of product paths rots and cannot place a new
  file. It survives inverted, as the inert list.
- Claim 3: re-derived from F4. The Reading judge answers cause identity, ownership and
  failure side. It does not decide scope, because F3 makes every uncited file a rerun.
- Claim 4: re-derived from F1. QA becomes a compiled proof run. An agent appears only to
  write claims before the build and to walk the story after it.
- Claim 5: kept, behind F6. Delivery first, because the measured waste is a wiring defect.
  The acceptance walk is the cheap method skill.
- Claim 6: rejected as worded. An unreachable outcome parks, it never passes (invariant 4).
- Claim 7: rejected as worded. A title match misses rewordings and new forms. Cause
  identity keys on the broken assumption.
- Claim 8: rejected. The operator chose the feed monitor. Gate notice keeps the feed and
  adds a wait that returns on a gate.
- Claim 9: moved out of scope, to a story in the `mobile-app` repo.
- Claim 10: rejected. Per-lap self-authoring and self-audit is the cost F1 removes. The
  Claim author and the User walk replace it, once per story each.

**SOLID check.** Each Owns reads without "and". Adding a third judge, say a cached one, adds
one concept and one line where the workflow assembles. The Rule and Reading judges are each
a kind of Judge only. The Judge declares one call: answer this question. Cause identity
and the Verdict name the Judge, never a variant.

**Open lookups**

- L1. Can the compiler build scenarios for the claims a story's pages carry, with no
  hand-written plan? Decides whether Proof run needs new code.
- L2. Do the book's citations carry enough file detail to build the citation index?
  Decides Proof scope's rule.
- L3. Why did the run sit 6.6 hours with nothing happening? Decides Liveness.
- L4. Why does the turn's own cost record disagree with the dashboard? Decides which number
  the $100 target reads.

## 5. Mapping onto the existing system

**Revision log**

- R1. Section 2, Proof: the Coverage map was revised from "new" to "reshape". The context
  packet already lists required obligations (finding M3).
- R2. Section 7: L4 stayed open and became A4. Resolved by R8.
- R3. Section 1c and invariant 11: the replay (A5) found two shapes, not one. The stall
  rule catches the empty work list only. The other two edges lost laps to the wrong owner.
- R4. Section 2, Proof: Claim author and User walk added, invariant 12 added, from the
  judge's finding that a compiled check confirms the book and not the user.
- R5. Invariants 10 and 11: product side is the default, and the proving run reads the book
  as of the story's start, from the judge's finding that a book-side answer turns a product
  defect into a book edit.
- R6. Invariant 2 and Proof scope: an inert list replaces the reading judge on scope, from
  the judge's finding that a skipped rerun on a fixture or a lockfile changes behaviour
  unproven, and from A7 (fixtures and a makefile were the uncited files).
- R7. Invariant 5, Findings: identity keys on the broken assumption, from the judge's
  finding that wording dedupe counts a new form as new.
- R8. Section 1, Spend ledger and invariant 8: the dashboard double counts, from A4.
- R9. Section 1, Liveness and invariant 7: the 6.6 hours were a dead run, from A6.
- R10. Section 2: Device reach dropped as a part, Reach baseline moved into Proof, from
  the judge's finding that naming controls changes the adopter's app.
- R11. Section 4, Judge: the Reading judge runs on the middle tier, from A3. The low tier
  merged distinct defects.
- R12. Section 4, Coverage map: criteria no claim can observe map to a repo test or a static
  rule, from A2.
- R13. Sections 1, 2, 3 and 5b: Escape record and invariant 13 added, from the operator's
  point that a QA team is judged by the defects it lets through. The replay in A1 sees only
  known defects. Escapes measure the unknown ones.

**Proof: reshape.** QA today is one agent turn (`coder-qa`, power high, a 46 KB prompt)
that owns a hand-written `qa_plan.py`. It is routed from `coder/main/flow.py:142`.

- Claim author: **new**. Today the QA agent writes its plan after the build, with the diff
  in view.
- Coverage map: **reshape** (R1). The packet knows obligations but not which criterion each
  one serves.
- Proof scope: **new**, beside the main flow. The citation index reads the page bullets
  that carry each cited file's digest.
- Scenario: **exists** in `ostler/ostler/qa/compile.py:190` (`compile_plan`). The book
  workflow's exercise step already compiles and runs a book with no agent (L1, resolved:
  yes for book claims).
- Proof run: **reshape**. The coder QA runs `ostler qa run` on the agent's plan. The design
  runs the compiled plan for the scope.
- User walk: **new**. Nothing walks a story as its user today.
- Verdict: **reshape**. `kit/qa/evidence.py:88` (`_obligation_problems`) knows passed or
  missing only. Unreachable, side and base-red are new.

**Judgment: new.** `AgentProfile` (`workhorse/workhorse/runner/backends/__init__.py:23`)
takes `tools`, `steps` and `confined`, so a tool-less profile needs no engine change.

**Building: reshape.** Dev runs build, then a check gate per service (`coder/dev/flow.py`).
The acceptance walk is new prompt text. The self-check gains the scoped proof run.

**Findings: reshape.**

- Cause identity: **mismatch M1**. `coder/shared/work.py:69` dedupes by item id only. The
  same defect under a new id is filed fresh: 16 pending follow-ups are 4 defects filed 4
  times. The code is wrong, and the design's identity check goes there.
- Ownership: **mismatch M2**. 4 findings from story 2 belong to no item and sit open.
- Delivery: **exists since `bbabcc8f`**. Dev now reads the run's work list. Before that it
  read an empty one.
- Escape record: **new**. A finding records the item that filed it, never the committed
  story whose pages it sits on, so story 2's empty-state defect found during story 3
  reads as story 3's work.

**Main flow routing: mismatch M4.** `commit` (`coder/main/flow.py:228`) sends any dirty
path back to `dev`, and from there `document` and `qa` run again. The design sends a
dirty tree to Proof scope, and an inert-only change commits.

**Attendance: reshape.**

- Gate notice: the feed monitor exists. It reports on a 30-minute digest, so a gate waited
  50 minutes and another 4.6 hours. The phone push does nothing without a configured
  channel and swallows a failed post. A run probes for the dashboard only at launch.
- Standing: **mismatch**. The settle step emits no events, so status shows a stale step.
- Stall rule: **mismatch**. "Node completed 5× on the same work" fires on dev's
  one-gate-per-service check, and never compares inputs.
- Liveness: **mismatch M5**, revised (R9). The silence budget exists and resets only on a
  stdout line (`workhorse/workhorse/runner/process.py:337`). The 6.6 hours were a dead
  process: QA entered at 05:46 and never finished, and the next entry came at 14:51 on a
  resume. Nothing told the operator the run had stopped, because the dashboard died with it.
- Spend ledger: **mismatch**, revised (R8). The dashboard sums session-cumulative costs, so
  it shows $936 for QA where the per-session deltas give about $122.
- Attendant rules: **new**. The dispatched attendant committed with `--no-verify` and
  pushed a branch.

**What the existing system has that the design lacks.**

- The QA agent's per-turn auditor on the strongest model: waste on compiled scenarios. The
  User walk replaces it once per story.
- The QA agent's stack and setup repair seat: a concept the design missed. It belongs in
  Proof as the step that brings the stack up before a run. The book workflow already does
  this without an agent, so it stays a plain function, and a stack that stays red goes
  upward.
- The dev and document steps rerunning after a commit bounce: waste.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| Operator | A passed story proves every criterion on its revision | the evidence gate | 2 of 2 passed stories | Same gate passes, and no unreachable passes |
| End user | A defect they would meet is caught before commit | the QA agent's own scenarios | 2 known defects caught by QA (empty state, grouped query) | Every known defect turns a check red (A1), and the User walk files any it meets |
| Builder | Each product defect reaches the next brief | the dev prompt's work list (since `bbabcc8f`) | 1 defect found 13 times before it reached dev | Reaches dev on the next lap |
| Builder | Never handed a book or stack defect | nothing | 4 laps on an evidence gate the builder could not fix | 0 such laps |
| Operator | QA-side defects caught before the verdict, such as an undeclared fixture dependency | the per-turn auditor | 2 found in story 3's last pass | The base-red check or the User walk catches the same class |
| Repo | Its test suites pass on the revision | dev's per-service check | web: 1902 tests pass | Unchanged |
| Finished books | 0 doctor errors | the book check | 0 on every finished book | Still 0 after the Claim author's claims land |
| Operator | Time per story | nothing | 12 to 26 h | At most 4 h |
| Operator | Dollars per story | nothing | about $95, shown as about $570 | At most $100, shown as recorded |
| End user | Defects that escape a committed story | nothing | at least 1: story 2's empty state, found during story 3 | 0, and every escape on record |
| Operator | Follow-ups to triage | nothing | 16 pending, 4 distinct | 4 |
| Operator | Minutes a gate waits unseen | nothing | 50 min and 4.6 h | Under 5 min |
| Operator | Minutes a dead run goes unseen | nothing | 6.6 h | Under 5 min |

Time, dollars and follow-up counts have no check today. Invariant 8 (Spend ledger) makes
time and dollars observable. Invariant 5 (Cause identity) owns the follow-up count.
Invariant 11 (Verdict) owns the builder's wrong-owner laps. Invariant 7 (Liveness) owns the
dead run. Invariant 13 (Escape record) owns the escapes.

## 6. Slices

Each done-when re-measures every row of 5b on the next story of the live epic.

0. **Prove the process attended before building it.** Run probe 1 on a stack window: replay
   the known end-user defects at their live revisions. Then run the slice 1 process by
   hand on two real stories (aim 9): the Claim author's claims before the build, the
   compiled run, the side judgment on each red, a User walk, a scoped bounce after a
   metadata edit, and one judged unreachable if a story meets one. Record hours and
   dollars by per-session deltas, and every escape the second story finds in the first. Done when: probe 1 has a result against its threshold,
   and the two stories either meet the section 1 targets or name the assumption that
   failed. A failed assumption re-derives its "If wrong" items before slice 1 starts.
1. **Compiled proof with claims written first.** Claim author, Coverage map, Scenario,
   Proof run, Verdict with sides and base-red, User walk, Reading judge for the side. A
   green run and a clean walk pass with no other agent. Done when: one story passes this
   way in at most 4 h and $100, the evidence gate passes unchanged, and no red reaches the
   builder on the book or stack side.
2. **Scoped re-proof after a bounce.** Proof scope, inert list. A dirty tree at commit goes
   to the scope, not to dev. Done when: a metadata-only edit commits with no scenario run
   and no model call, a cited product edit reruns only its claims, and a fixture edit
   reruns the story's whole proof.
3. **One cause, one owner, delivered.** Cause identity, Ownership, Delivery, Escape
   record. Done when: the 16 pending follow-ups settle to 4, the 4 orphaned findings have
   an owner, a replay of the arithmetic and unary findings, filed in different words on
   different stories, lands on one cause, and that replay records story 2's empty state
   as one escape against story 2.
4. **Builder method.** Acceptance walk, Self-check with the scoped proof. Done when: dev's
   brief carries the walk, and the next story's first proof run has no product finding that
   the walk names.
5. **Liveness and spend.** Liveness, Spend ledger. Done when: a run killed by hand reaches
   the operator within 5 minutes, a silent call ends at its budget and resumes from its
   checkpoint, and the dashboard shows a story's per-session dollars.
6. **Attendance.** Gate notice, Standing, Stall rule, Attendant rules. Done when: a gate
   reaches the operator within 5 minutes with the dashboard started after the run, a failed
   push lands on record, status names the settle step while it runs, dev's per-service
   gates raise no stall, a hook refuses an attendant's `--no-verify` or push, and a replay
   of the recorded empty-work-list loop asks upward at its second lap.

## 7. Assumptions

Each assumption carries a **probe** with a threshold fixed before it ran. Probes 2 to 7 ran
on the epic's recorded data on 2026-10-19. Probe 1 needs a stack and runs in slice 0. The
attended pass of slice 0 is the second probe for every assumption, and the re-measure of
section 5b after each slice is the third.

1. **Assumption:** the book, compiled, catches the defects an end user would meet in this
   epic.
   **Decided:** QA runs compiled scenarios, written first by the Claim author, with a User
   walk after.
   **Basis:** story 3's 32 required obligations included its empty-state criterion. Probe 2
   found four defects in the current reports book: two anchors the stories link to do not
   exist, one claim has no `verify:`, and one claim scopes a button wrong.
   **Probe:** take every product defect the epic found so far: the empty-state controls,
   the grouped-query failure on formula refresh, and the 4 open findings of story 2. For
   each, check out the revision where it was live, compile the claims of the pages it sits
   on, and run them. **Holds when:** every defect turns at least one scenario red, and the
   red scenario's message names what the user would see.
   **Result:** not run. It needs a stack the live run holds.
   **If wrong:** the book strategy changes before slice 1. The miss pattern says how:
   claims about routes and contracts where the user meets states and journeys, missing
   empty and error states, or shallow journeys. That is its own design note for the book
   method, and slice 1 waits on it. Two escapes on one story's pages start the same review
   later, whatever the replay showed (invariant 13).
2. **Assumption:** the acceptance criteria of the remaining stories can be written as book
   claims, and the user-visible ones as claims that read the screen.
   **Decided:** the Coverage map ties criteria to claims. A criterion no claim can observe
   maps to a repo test or a static rule (R12).
   **Probe:** a seat that saw no diff mapped the 139 criteria of the 11 remaining stories.
   **Holds when:** at least 90% map to a claim.
   **Result:** 89.9% counting partials, 84.2% strict. All 98 user-visible criteria map to a
   claim that reads the screen. The 14 that cannot map are internal: work kept off the main
   thread, and no new database object. Most claims need a new fixture, and the error and
   loading states need fixtures that hold a response. Holds once the 14 go to repo tests
   and static rules.
   **If wrong:** slice 1's cost target.
3. **Assumption:** a reading judge with no tools and inlined inputs answers the closed
   questions well enough that its errors cost a rerun or an ask, never a missed defect.
   **Decided:** the Reading judge serves cause identity, ownership and failure side, on the
   middle tier at low effort (R11). Invariants 3 and 11 bound its errors.
   **Probe:** replayed 52 distinct-defect pairs, 54 duplicate pairs and 21 recorded sides.
   **Holds when:** no two distinct defects are merged, at most 1 in 10 duplicates is
   missed, and at most 1 in 10 sides is wrong.
   **Result:** the low tier merged 14 distinct pairs, missed 20% of duplicates and got 19%
   of sides wrong. The middle tier merged none, got 4.8% of sides wrong, and missed 15% of
   duplicates. All 8 of its misses paired an arithmetic finding with a unary one, which the
   record itself treats as two stories. It cost $1.04 for 127 questions. Holds on the middle
   tier. The side set had no regression case.
   **Slice 3:** on a copy of the live work list, the word rule alone settled one story's 16
   pending follow-ups to 4 with no model call. The judge kept rewordings of one finding
   together within a story. It answered `new` for story 2's empty-state finding against
   story 3's follow-up for the same screen, so the defect would have had two owners. The
   question then keyed on criterion numbers and triggers. It now asks whether a person
   would see the same thing go wrong on the same screen, and a replay matched all four
   findings to the follow-up three times out of three. The arithmetic and unary findings
   are not in this work list, so that half of the done-when was not measured.
   **If wrong:** the Judge variants, and slices 1 and 3.
4. **Assumption:** the dashboard's per-node cost is the dollar figure the operator means.
   **Probe:** recompute one turn from its transcripts at list prices, and compare with the
   harness and the dashboard. **Holds when:** two agree within 10%, or the gap is named.
   **Result:** wrong. The harness delta and the dashboard's span delta agree at $10.62 for
   the turn, and the recompute is 15% above them because the harness bills one model below
   the price card. The dashboard's run total sums session-cumulative values: $1425 for the
   run against about $239 in per-session deltas.
   **Decided now:** the $100 target reads per-session deltas, and the Spend ledger fixes the
   view (R8).
   **If wrong:** every dollar row in 5b.
5. **Assumption:** the stall rule's input digests catch every return-edge loop by its
   second lap without stopping a lap that would have moved.
   **Probe:** computed the digests over every recorded return-edge lap.
   **Result:** partly. The empty-work-list loop repeated tree and findings for laps 3 to 6,
   so the rule asks upward at lap 2 and saves 12 turns. The two laps that later passed ran
   only after the operator stepped in and the findings entered the brief, which is what an
   ask upward produces. The evidence-gate loop moved its inputs every lap, so the rule never
   fires there. The commit bounce ran one lap. Hence invariant 11 (R3).
   **If wrong:** invariant 9 and the Stall rule.
6. **Assumption:** the 6.6-hour silence was a hung model call the runner can bound.
   **Probe:** read why the 1800-second budget did not fire.
   **Result:** wrong. The run's events show QA entering at 05:46 with no finish, and a new
   entry at 14:51 on a resume. The process was dead, and the "No response requested."
   message is the CLI resuming its session. The silence budget did not apply.
   **Decided now:** Liveness owns a dead run reaching the operator (R9).
   **If wrong:** Liveness and slice 5.
7. **Assumption:** the book citations' file digests name most files a story changes.
   **Decided:** Proof scope reruns cited claims for cited files, and the whole proof for
   anything else not inert.
   **Probe:** for each product commit in the epic, the share of changed files some claim
   cites. **Holds when:** at least 80%.
   **Result:** holds on production source at 88.7%, with 14 of 18 commits at 80% or better.
   The misses are a test database fixture, a makefile and four JSON fixtures, which is why
   they rerun the whole proof (R6).
   **If wrong:** invariant 2 and slice 2.
8. **Assumption:** a scoped proof run takes minutes.
   **Decided:** the builder's self-check runs it.
   **Basis:** scenario runs in this epic took about 2 minutes each.
   **Probe:** time the probe 1 runs. **Holds when:** a scoped run finishes in 15 minutes.
   **If wrong:** the Self-check and slice 4.
9. **Assumption:** a User walk at medium power fits in the 4-hour and $100 budget.
   **Decided:** one walk per story, after a green proof.
   **Basis:** none.
   **Probe:** time and price the two walks in slice 0. **Holds when:** each takes at most
   30 minutes and $15.
   **If wrong:** the User walk's power, and slice 1.
10. **Assumption:** the live run takes these changes between stories through a core
    reload, and the current story finishes on the old QA.
    **Decided:** slices land one story at a time.
    **Basis:** earlier fixes reached this run that way.
    **Probe:** none needed before slice 1. **If wrong:** slice order.
