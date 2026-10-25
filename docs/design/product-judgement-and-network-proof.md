# Product judgement and network proof

Disclosure: before this note was written, the author read the PM review angles, the story
writer's acceptance-criteria rule, and ostler's browser listeners. Those design decisions are
listed as claims in section 1b, and each part was checked against the test "would I have
named this without having seen the solution?"

## 1. Problem

A developer building with stablemate ships a screen that tells its end users something only QA
needed to know. In Acme, the reports screen showed estimators the line "Formula-derived
values include supported arithmetic expressions calculated on this device". The estimator
cannot act on it. The word "supported" invites them to doubt the totals under it. Legacy
Acme never showed it. The line existed because a story had to prove where the calculation
ran, and the only proof QA could read was text drawn on the screen.

Done looks like this to that developer:

- A story that promises "the calculation runs on the device" is proven by what the device
  sent over the network, in the page and in its service workers. A broken build that asks the
  server for the totals fails QA. Nothing is drawn on screen for the proof.
- The PM reviewer rejects a user-facing element whose only reader is QA or an operator. It
  turns that element into an operator proof. On the four Acme stories that carried the
  note, it raises the finding. On a sample of stories with no such element, it raises none.
- Built stories get a product review against what shipped. A first attended pass over
  Acme's 51 QA-passed stories produces a list of findings the developer can accept or
  reject, each filed as a fixes story.

Out of scope:

- Rewriting the PM's other angles (journey, chrome, transient feedback, grounding, mockup).
- Visual fidelity against legacy screenshots. `acme-visual-fidelity-qa` owns that.
- Automating the post-build review as a workflow stage. Aim 9 holds that back until two
  attended passes have finished (slice 5).
- Recording HAR files or replaying traffic. Observation and blocking cover the problem.

## 1b. Claims

1. "Each acceptance criterion is something the journey actor can see or do." A technical
   enabler "may instead be verified by an operator at the running system boundary, but it must
   name the epic journey step it unlocks." (`author/pm/prompts/angles/story/journey.md:3`,
   `author/story_author/prompts/write-story.md:124-127`)
2. The PM is the only agent reviewer in authoring. (`docs/design/milestone-authoring.md`
   decisions 21-26)
3. The story angles are journey, chrome, transient feedback, grounding and mockup.
   (`author/pm/angles.py:24-26`)
4. QA never fixes the product. (`coder/qa/prompts/qa-story.md:19`)
5. Browser listeners attach to the page. (`ostler/qa/harness/ostler_qa_browser.py:552-559`)
6. "The completed result states that it was calculated on this device and saved for this
   project." (Acme story `view-one-locally-calculated-report`)

## 2. Parts and concepts

### Level 1

1. **The story contract** says what a story promises. It owns the split between what the end
   user meets and what an operator proves. It never knows how QA reads either one. It hands
   both lists to product judgement and to QA.
2. **Product judgement** decides whether each thing the end user meets earns its place. It acts
   at two moments: before the build, on the story and its mockup, and after the build, on the
   shipped screen and the book. It never knows how the coder built the screen. It hands
   verdicts back to the contract writer before the build, and fixes stories to the developer
   after it.
3. **Network observation** records every exchange the device makes while a scenario runs, from
   the page and from its workers. It owns the claim "this was or was not requested during
   this action". It never knows what the exchange means to the product. It hands readings to
   QA's verdict.
4. **Network interception** changes what the device can reach during a scenario: it blocks a
   path, fails it with a status, or cuts the network. It never knows which claim the scenario
   checks. It hands every exchange it touched to observation, marked as intercepted.

Flow: the contract writer splits the promises. Product judgement reads the story before the
build and sends any proof drawn as UI back to the writer. QA proves the operator promises
through observation, under interception where the story needs the server gone. After the
build, product judgement reads the shipped screen and the book, and files fixes stories for
the elements that do not earn their place.

### Level 2

**The story contract**

| Concept | Owns | Never knows |
|---|---|---|
| User outcome | what the end user sees or does after the build | how QA observes it |
| Operator proof | a fact about where or how work runs, checked at the system boundary | any screen element |
| Journey link | the journey step an operator proof unlocks | the proof's mechanism |

**Product judgement**

| Concept | Owns | Never knows |
|---|---|---|
| Element | one thing the end user meets: a line of text, a control, a state | the code that draws it |
| Audience | who acts on the element and what they do with it | the element's implementation |
| Precedent | what legacy shows at the same moment of the same journey | the new code |
| Verdict | keep, move to operator proof, or ask the person | how the verdict gets applied |
| Review packet | the inputs one moment hands the judge | the judge's reasoning |

The questions the judge asks are one read-only reference that both moments consult. The two
moments differ only in their review packet.

**Network observation**

| Concept | Owns | Never knows |
|---|---|---|
| Exchange | one request and its outcome, with its initiator: page or worker | which check reads it |
| Window | the span of one action, closed once the device goes quiet | the exchanges' meaning |
| Network claim | how many exchanges in a window match a path, a method and an initiator | the product behaviour behind the path |

**Network interception**

| Concept | Owns | Never knows |
|---|---|---|
| Interception rule | a path pattern and its effect: block, fail with a status, or offline | the claim under test |
| Interception record | the mark on every exchange a rule touched | the rule's reason |

## 3. Invariants

1. **An operator proof never appears as a user-facing element.** Owner: Verdict. The contract
   writer upholds it while writing. Breach: an element whose audience is QA or an operator.
2. **Every user-facing element names its audience action or its precedent.** Owner: Verdict. An
   element with neither is a finding, not a pass.
3. **Observation sees every exchange the device makes for the app.** Owner: Exchange. Breach: a
   service worker registered in the scenario while capture covered the page alone. The run
   parks rather than passing a zero count it did not observe.
4. **A zero count passes only after the window went quiet.** Owner: Window. A request sent late
   would otherwise escape the claim.
5. **An intercepted exchange is never read as the server's answer.** Owner: Interception record.
6. **The post-build judge never reads the coder's reasoning.** Owner: Review packet (aim 2).

## 4. Forces and patterns

Forces:

- F1. The proof of where work runs varies independently of what the user sees. Today the two
  are coupled: the only readable proof was the screen.
- F2. Exchanges come from more than one initiator: the page, a service worker, later a shared
  worker or a frame. The set grows.
- F3. Product judgement happens at two moments with the same questions and different evidence.
- F4. The judge must come from somewhere the work did not (aim 2).
- F5. A new workflow stage needs two finished attended sessions first (aim 9).
- F6. Interception effects vary: block, fail, offline. Each is small.

Between parts: a sequence. The contract feeds judgement and QA, and QA reads observation. F1
is answered by the split inside the contract. No events or ports are needed, because no part
swaps at run time.

Inside parts:

- Operator proof as its own concept (F1). It gives the writer a place to put a fact that is
  not UI.
- Exchange carries its initiator as a value (F2). One capture point at the browser context
  covers every initiator. A new initiator adds a value, not a listener.
- One question set, two review packets (F3). A moment is a packet builder. The questions do
  not fork.
- Review packet built from inputs the coder did not write (F4): the milestone's purpose,
  legacy evidence, the shipped screen, the story and the book. The dev transcript is excluded.
- Post-build review as an attended procedure first (F5). It is a written brief run by hand,
  and its transcripts become the spec of the seat.
- Interception effect as a plain value (F6). No variant hierarchy until an effect needs its
  own state.

Claims:

1. Kept, and inverted in emphasis. A fact about where or how work runs is an operator proof
   by default. The writer never draws it on screen to make it visible.
2. Kept. The post-build reviewer is the same PM role with a different packet.
3. Kept, with one angle added: audience.
4. Kept. The post-build review files fixes stories and edits nothing.
5. Rejected by F2 and invariant 3. Capture moves to the browser context.
6. Rejected. It is the defect this note answers.

Open lookups:

- L1. Does Playwright 1.61 on Chromium report worker-initiated requests on the browser context,
  and does a context route intercept them? Decides whether part 3 and part 4 work as drawn.
- L2. Does any current QA plan read `response_for(path)` on a path a service worker also
  fetches? Decides whether readers default to page-initiated exchanges.

## 5. Mapping onto the existing system

Revision log:

- Section 7, A1: probed on Playwright 1.61 Chromium. The context sees a service worker's own
  requests and the page does not. A context route intercepts them and a page route does not.
  `networkidle` ignores them, so the harness quiet wait must count them. A1 now has a basis.
- Section 5, Network claim: revised from Reshape to Exists. The book already has
  `emitted(event="METHOD /path", count=N)`, compiled to `requests_to`. `count=0` states a
  request the page must not send. No new check kind is added.
- Section 6, slice 1: the proof is open. The Acme reports page posts the report request on
  every load, and the server answers with a first report that the page replaces with the local
  one. A request count cannot tell a local calculation from a server one on this page.
- Section 6, slices 1 and 5: the developer chose a poisoned answer to close slice 1. The rewrite
  effect of `qa.intercept` moves from slice 5 into slice 1. A flow declares it with an
  `intercept:` bullet, and the run fails when the rule alters nothing. The block effect stays
  in slice 5.

| Item | Verdict | Where, and the mismatch |
|---|---|---|
| Story contract | Reshape | `write-story.md:122-130` allows operator proof only for "a technical-enabler story". A user-facing story that also promises where work runs has no place to put that fact. |
| User outcome | Exists | the same section |
| Operator proof | Reshape | it exists only as the enabler escape. It becomes a named list in the story template. |
| Journey link | Exists | `journey.md:3` |
| Product judgement, before build | Reshape | `author/pm/` runs five angles. None asks who acts on an element. |
| Element, Audience, Precedent | New | a sixth story angle, `author/pm/prompts/angles/story/audience.md`, registered in `angles.py:24-26`. Legacy parity has no PM angle today. It runs only in `parity-survey` mode (`author/main/flow.py:60-65`). |
| Verdict | Exists | the PM review verdict and ledger (`author/pm/prompts/ledger.md`) |
| Product judgement, after build | New | no seat exists. It starts as an attended brief under `docs/design/` and moves into `coder/` only at slice 5. |
| Review packet | New | built by hand in the attended passes |
| Exchange | Reshape | `ostler_qa_browser.py:552-559` listens on the page. Records lack an initiator field. The diagnostics schema `browser-diagnostics/2` gains `initiator`. |
| Window | Exists | `ResponseWindow` at `ostler_qa_browser.py:132` with `quiet()` before every read |
| Network claim | Exists (revised, see log) | `emitted(event="METHOD /path", count=N)` in `checks.py` compiles to `window().requests_to(path, method=...)` at `compile_playwright.py:296-311`. |
| Interception rule | New (revised, see log) | a flow `intercept:` bullet compiles to a context-scoped `qa.intercept(effect, event=...)`. Slice 1 ships the rewrite effect. |
| Interception record | New | an `intercepted` field on the exchange record |

What the system has that the design lacks:

- `console` and `downloads` ride the same window. That is not waste. `emitted` already
  follows their shape.
- The `parity-survey` mode is a precedent source the audience angle can read. It belongs to the
  Precedent concept. The design missed it, and the angle cites it.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| Existing QA plans that read exchanges by path | one page-initiated exchange per matching request | `response_for` raises on ambiguity | not measured (A4) | every Acme and stablemate QA scenario that passed before still passes |
| Readers of `*-diagnostics.json` | schema `browser-diagnostics/2` | schema tests in `ostler/tests` | v2 | v3 adds a field and drops none |
| PM review cost per story | five angles | nothing | not measured (A5) | one more angle adds under 20% to review time |
| Stories that pass PM review | the current pass rate | nothing | not measured (A5) | the audience angle fails no story in a sample of ten known-good ones |

Rows enforced by nothing become invariants or slice checks: the cost row is measured in slice 2.

## 6. Slices

1. **Prove one local calculation from the network.** Capture at the browser context with an
   initiator field. Add the rewrite effect of `qa.intercept`. In Acme, a new Step Detailed
   flow rewrites the server's report answer, `1300` to `4200`, and verifies the first tab still
   reads the device's `1,300.00 $` and shows no `4,200.00 $`. The proof is revised, see the
   log. Done when that flow passes on master and fails on a build patched to show the server's
   first report. Every QA scenario that passed before still passes.
2. **Teach the PM to ask who the element is for.** Add the audience angle and the operator
   proof list in the writer prompt. Done when a PM review of the four stories that carried the
   note raises it on each, and a sample of ten stories with no such element passes. Review time
   per story is measured before and after.
3. **Attended post-build review, first pass.** Run the review by hand over epics 0001 and 0002
   of Acme. The packet holds the milestone purpose, the story, the shipped screen from QA
   evidence, the book page and the legacy screen. Done when each finding is filed as a fixes
   story in epic 0008, or rejected by the developer with a reason.
4. **Attended post-build review, second pass**, over epics 0003 to 0007. Done when its
   transcript and the first one agree on the packet and the questions, or the brief is revised
   until they do.
5. **Network blocking.** Add the block effect of `qa.intercept`. Acme's offline recalculation flow blocks the
   API after load and proves the report still completes. Done when that flow passes and a build
   that needs the server fails it.
6. **Post-build review seat.** Only after slices 3 and 4: a coder stage that runs the brief on
   each QA-passed story. Done when it reproduces the attended findings on epic 0001.

## 7. Assumptions

1. **Assumption:** Playwright 1.61 on Chromium reports service-worker requests on the browser
   context and lets a context route intercept them. **Decided:** one capture point and one
   route point at the context. **Basis:** Playwright's service-worker documentation, Chromium
   only, and a probe on 2026-10-25 confirmed both. **If wrong:** parts 3 and 4, slice 1 and slice 5.
2. **Assumption:** the note exists because the journey rule pushed the writer to make a fact
   visible. **Decided:** the fix targets the writer rule and adds an angle. **Basis:**
   `journey.md:3` and the wording of claim 6. **If wrong:** slice 2 targets the wrong cause.
   Slice 2's replay on the four stories tests it.
3. **Assumption:** Acme QA runs on Chromium. **Decided:** worker capture is Chromium-only.
   **Basis:** none. **If wrong:** invariant 3 parks every run on another engine.
4. **Assumption:** current plans read only page-initiated exchanges. **Decided:** existing
   readers default to `initiator=page`, and `emitted` keeps reading page requests.
   **Basis:** no worker capture exists today. **If wrong:** section 5b row 1.
5. **Assumption:** one more angle costs under 20% of review time. **Decided:** run it on every
   story. **Basis:** none. **If wrong:** run it only on stories with a mockup.
6. **Assumption:** legacy evidence is reachable from a review: `legacy/` in the repo and the
   legacy mirror on port 8081. **Decided:** Precedent reads both. **Basis:** Acme
   `AGENTS.md` and `acme-legacy-visual-capture`. **If wrong:** Precedent falls back to the
   book and the milestone.
