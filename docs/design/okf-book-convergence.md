# Why an OKF book run does not converge

> **Disclosure.** I read the existing solution before this design started. That covers the
> ostler QA harness and compiler, the okf-book workflow with its flow, nodes and repair
> prompt, the ostler-okf grammar references, and my memory index about this work. I also
> wrote parts of it. Each design decision it carried is a claim in section 1b, and
> sections 2 to 4 re-derive or reject each one.

## 1. Problem

**Who feels it.** The operator who asks for a verified book of a service's HTTP API. They
watch the run for days and get no book. Over four days, 18 runs spent about 1.3 billion
tokens. Only the smallest book, 6 scenarios, ever passed. The api book of the `acme` client
repo has run 21.7 hours and 15 full laps in its latest run. It still fails 1837 of 2671
checks, in 12 of 14 scenarios. Three repair rounds moved the count from 1876 to 1887 to
1837, so repairs do not move it.

Whoever attends the run reads the app's log to find each cause, because the run does not
name it.
The causes they found were outside the pages:

- A fixture's seed revoked the tokens another fixture minted.
- The stack has no payment provider key, so every billing route answers 500.
- A sign-in fixture uses an admin with no account row, so every route that loads the
  caller's account refuses it.
- Routes carry placeholder ids, so they answer 404 where the claim expects 200.

The run sent each of these to a page writer as "expected 200, observed 401". A page
writer cannot fix a missing key or a revoked token. Each defect also surfaced only after a
full lap, about 1.4 hours.

**Done looks like this.** For the api book, within 3 laps of a run:

- every check passes, or carries a verdict naming a cause outside the book. The attendant
  receives each such cause once, with the number of checks it blocks, not once per check.
  A person hears only of a cause no agent can settle, such as a missing payment key.
- a defect shared by many checks, such as a broken sign-in or a missing service, surfaces
  within 10 minutes of the run's start.
- the count of failures the book causes falls every lap, or the run asks the attendant why.

**The attendant** is the agent one level above the run, such as the one groom launches on
a gate. It diagnoses what the run could not see, then sends a narrower task down or fixes
the tool. It asks a person only what only a person can answer (aim 8).

**Out of scope.**

- Model cost, provider quotas and transient provider drops.
- The writer's shell refusing a command's spelling.
- Warning noise in the static check.
- Books of the cli and screen surfaces. They inherit whatever this design settles.
- Claims about state changes the harness cannot observe (the `needs-snapshot` gap).
- Names of flow pages.

## 1b. Claims

These decisions reached me through the existing solution, its prompts and my own gate
answers.

1. A book runs as scenarios grouped by page. One api scenario holds 2656 checks. (run
   output)
2. A fixture's arrangement runs inside every scenario that names it, against one stack
   seeded once. (harness, run log: 216 to 242 revoked tokens)
3. The whole book runs before any repair, and a lap's failures are repaired in batches of
   pages. (workflow)
4. A failed check reaches a writer as "label: expected X, observed Y". (workflow)
5. Every failure of a run is a blocker on the book side. (workflow's blocker record)
6. The operator's answer to a gate reaches every repair turn that follows, as prose.
   (repair prompt)
7. A request in an arrangement carries an expected status, and a mismatch stops the
   journey. (harness)
8. A check that needs a before and after snapshot is gapped and restated on the response.
   (repair prompt)
9. A writer checks their own pages with a command that runs those pages' scenarios, and
   each call brings the app up in about a minute. (repair prompt)
10. A route that fails because a service is missing gets a claim restated to the 500 it
    returns. (my gate answer to run 17)

## 2. Parts and concepts

### Level 1: parts

1. **Authoring.** The book says what the app does, one claim at a time, in the grammar.
   It owns claims and the preconditions each claim names. It never knows the state of the
   running app. It acts at two moments: writing the book, and repairing pages a finding
   names. It hands claims to Arranging and Observing.
2. **Arranging.** Bringing the app into the state a claim presupposes: users, their
   credentials, the records a route needs. It owns that state and who shares it. It never
   knows what a claim asserts. It hands bound values (a token, an id) to Observing.
3. **Environment.** The stack the app runs in and the outside services it can reach. It
   owns what is present: a payment key, object storage, the database. It never knows the
   book. It hands its inventory to Judging.
4. **Observing.** Sending a request, recording the reply, comparing it to the claim. It
   owns evidence. It never knows why a comparison failed. It hands evidence to Judging.
5. **Judging.** Turning evidence into a verdict and a cause. It owns the answer to "whose
   fault is this". It never knows who will fix it or how. It hands causes to Routing.
6. **Routing.** Sending each cause to the level that can fix it. A page's writer fixes a
   cause in its page or its arrangement. Every other cause goes up to the attendant, which
   asks a person only what no agent can answer (revised, R2, R4). It owns what each level
   receives. It never decides a cause. It hands findings to Authoring and to the attendant.
7. **Converging.** Deciding what runs next and when to ask for help. It owns the order of
   probes, the record of progress per lap, and escalation. It never reads a single check.

**Flow.** Converging starts a lap. Environment reports its inventory. Arranging builds
each precondition once and probes that it holds. Converging runs a cheap probe of one
claim per route shape, then the full book. Observing records evidence for every claim.
Judging attributes every failure, and groups those with one cause. Routing sends book and
arrangement causes to the writers of the pages they name. It sends every other signature
up to the attendant as one finding each. The attendant answers by naming the signatures
it settles and the page each one goes to, or by fixing the tool and reloading the run.
Authoring repairs. Converging compares the lap to the last one and either starts the next
lap or asks the attendant.

In one paragraph: the book is checked against a live app. Before checking, someone has to
set the app up, and the app depends on outside services. When a check fails, somebody has
to decide whether the book, the setup, the services or the app is wrong, and tell whoever
can fix it. An agent answers first, and a person only when no agent can. Someone also has to notice early when a whole class of checks is
failing for one reason, and notice when fixes stop helping.

### Level 2: concepts

**Authoring**

| Concept | Owns | Never knows |
|---|---|---|
| Claim | one statement of app behaviour and the check that would fail without it | how the request is sent |
| Precondition | the name of a state or an outside capability a claim needs, and what it promises (revised, R3) | the steps that build or probe it |
| Grammar | the rules of what a page may say (read-only reference every part consults) | any one book |
| Static check | what cannot run, found before a run: an undeclared precondition, an id with no source, a need with no declaration | the app's replies |
| Writer turn | a bounded edit to the pages one finding names | findings addressed to anyone else |

**Arranging**

| Concept | Owns | Never knows |
|---|---|---|
| Arrangement | the steps that make one precondition true | the claims that use it |
| Identity | one principal's credentials and their lifetime within a lap | other identities |
| Binding | a value a claim needs, taken from what an arrangement created | the route grammar |
| Scope | which claims share one arrangement's state, so a failure spoils only its scope | the checks inside a claim |
| Arrangement probe | whether a built precondition keeps its promise, such as a token that signs in | the claims waiting on it |

**Environment**

| Concept | Owns | Never knows |
|---|---|---|
| Stack | bringing the app and its services up once and keeping them up | the book |
| Capability inventory | the capability preconditions whose probe held in this stack (revised, R3) | the claims that need them |
| Environment gap | a needed capability the stack lacks (shared value type) | who will supply it |

**Observing**

| Concept | Owns | Never knows |
|---|---|---|
| Exchange | the request sent and the reply received, with tokens masked | the claim's intent |
| Check | one comparison of an expected value to an observed one | the cause of a mismatch |
| Unreached record | each check a stopped journey did not reach, and the step that stopped it | why the step failed |
| App trace | what the app logged while it served one exchange | the verdict |

**Judging**

| Concept | Owns | Never knows |
|---|---|---|
| Verdict | pass, fail, unreached or gapped (shared value type) | the party |
| Cause | the kind of defect: book, arrangement, environment, app, tool, or unattributed when no rule matched (shared value type, revised, R4) | the fix |
| Attribution | the rules that turn evidence and the inventory into a cause | who receives it |
| Signature | the grouping of failures that share one cause, with a count and a sample | any single check's text |

**Routing**

| Concept | Owns | Never knows |
|---|---|---|
| Party | the level that receives a kind of cause: a page's writer, the attendant or a person (revised, R4) | how the cause was found |
| Finding | one signature addressed to one party, with its evidence sample | the other parties' findings |
| Escalation | one question to the level above, holding the findings the level below could not settle, each with its cause, the pages it lives in and its rerun (revised, R4, R6) | how the level above settles them |
| Rerun | the command that runs again only the checks one finding names (R6) | who runs it |
| Book snapshot | each claim's expected outcome as the book stated it when an escalation opened (R6) | the setup a claim needs |
| Turn budget | what one writer turn may read and spend | the findings' content |

**Converging**

| Concept | Owns | Never knows |
|---|---|---|
| Probe order | what runs first: arrangements, then one claim per route shape, then the book | the verdicts' causes |
| Lap | one pass of every claim in the book | how a claim is checked |
| Progress ledger | per lap, the failures by cause and by party | single checks |
| Stall rule | when progress has stopped and the attendant must be asked (revised, R4) | the fix |

Shared across parts: Verdict, Cause and Environment gap are value types. Grammar is a
read-only reference. No concept belongs to two parts.

## 3. Invariants

1. **Every claim ends a lap with a verdict.** A check never disappears because its journey
   stopped. Owner: Progress ledger, the one concept that sees the whole lap. Upheld by
   Unreached record.
2. **A failure reaches a page's writer only when its cause is that page or its
   arrangement.** An unattributed failure goes up, never down (revised, R4). Owner:
   Finding. Upheld by Attribution and Party.
3. **One arrangement never invalidates another's identity within a lap.** Owner: Identity,
   which detects a credential that worked and then stopped, and fails the arrangement.
   Upheld by Scope.
4. **A claim whose needed capability is absent is gapped, never failed.** Owner:
   Attribution. Upheld by Precondition and Capability inventory (revised, R3).
5. **A cause shared by many checks is reported once, with its count.** Owner: Signature.
6. **Every failed exchange carries the app's reply, with every token masked.** Owner:
   Exchange.
7. **Every precondition a claim names is declared, and every id a route needs has a
   binding, before the run starts.** Owner: Static check.
8. **The count of book-caused failures falls every lap, or the attendant is asked.**
   Owner: Stall rule. Upheld by Progress ledger (revised, R4).
9. **An answer reaches only the writers of the pages its signatures name, until the next
   escalation.** Owner: Escalation (revised, R4).
10. **A person is asked only what no agent can answer.** Owner: Escalation, which carries
    the attendant's reason for asking. Upheld by Party (R4).
11. **An escalation's finding closes only when its rerun passes, never on an answer's
    word.** Owner: Escalation. Upheld by Rerun (R6).
12. **A claim's expected outcome changes only through its page's writer.** An edit from
    the level above that changes one goes back to that writer as a finding. Owner: Book
    snapshot (R6).

## 4. Forces and patterns

### Forces

- **F1. A full lap is expensive.** 2671 checks take about 1.4 hours, and the latest run
  needed 15 laps. A shared defect must surface without a full lap.
- **F2. Causes vary by who can fix them.** A page's writer, the attendant and a person fix
  different things. The kinds of cause grow
  independently of the book.
- **F3. Many checks share one cause.** One failed seed took about 830 checks with it. A
  placeholder id fails 50 to 83 checks per endpoint.
- **F4. The environment varies per machine, independently of the book.** One stack has
  a payment key and another does not.
- **F5. Arrangements share mutable state in one live app.** Reseeding revoked 216 to 242
  tokens in a lap.
- **F6. Tests must swap the app, the writer and the stack.**
- **F7. The book grows.** The api book has 2671 checks, and three more surfaces follow.
  A failure's reach must stay bounded as it grows.
- **F8. A writer turn is expensive.** One turn costs 0.35 to 6.8 million tokens. It must
  carry only what the writer can fix.

### Between parts

- **One lap record handed along** (F1, F7). Environment, Arranging, Observing and Judging
  each add to one record of the lap. Converging reads it whole. Routing reads its
  signatures.
- **Ports for the app, the writer and the stack** (F6). Each is an adapter behind a narrow
  interface, so a test runs a lap against a fake server and a fake writer.

### Inside a part

- **Attribution: an ordered rule list, first match wins** (F2). Each rule reads the
  exchange, the arrangement's probe and the inventory, and names a cause. A new kind of
  cause is a new rule. A failure no rule matches is unattributed, never the book's by
  default. The attendant adds a rule when an unattributed cause recurs (revised, R4).
- **Signature: group by key** (F3). The key is the cause, the precondition, the status and
  the route shape.
- **Party: a table from cause to level** (F2). Book and arrangement causes go to the
  page's writer. Every other cause goes to the attendant. Plain data (revised, R4).
- **Escalation: each level asks the one above** (F8). A writer turn carries only what its
  page can fix, so a cause it cannot fix goes up rather than into its prompt (revised,
  R4).
- **Arrangement: built once per lap, reused by every claim in its scope** (F5, F1). This is
  a fixture scoped to the lap, as a test framework scopes one to a session. Its facts,
  such as a token or an id, pass to later scenarios through the lap record, because each
  scenario runs apart from the others (revised, R1).
- **Identity: one per arrangement, never shared** (F5). An arrangement that needs a user
  creates its own.
- **Probe order: staged gates** (F1). Arrangements first, then one claim per route shape,
  then the book. A stage that fails stops the next and raises its findings.
- **Capability inventory: a capability is a precondition whose arrangement is a probe**
  (F4). The book names the probe, such as "the payment provider answers". The inventory is
  the probes that held. No second declaration exists beside the precondition (revised,
  R3).
- **Stall rule: compare two ledger entries** (F8). A plain function.
- Verdict, Cause, Environment gap, Exchange, Check, Binding, Turn budget: plain values or
  functions. No force varies them.

### Claims

| Claim | Outcome | Force |
|---|---|---|
| 1. Scenarios grouped by page | Rejected. Scope follows the precondition, so one failed arrangement spoils only its claims. | F7, F3 |
| 2. Arrangement runs in every scenario that names it | Rejected. Built once per lap, with its own identity. | F5, F1 |
| 3. Whole book before any repair | Rejected as the only order. Staged probes come first. | F1 |
| 4. Failure as "expected X, observed Y" | Kept, extended with the reply, the cause and the signature. | F2, F3 |
| 5. Every failure is book-side | Rejected. | F2, F8 |
| 6. Operator answer reaches every repair turn | Rejected. An answer names signatures, and each reaches only its page's writer (invariant 9, revised, R4). | F8 |
| 7. Arrangement request stops the journey on mismatch | Re-derived, with unreached checks recorded (invariant 1). | F3 |
| 8. Snapshot claims gapped | Kept as the gapped verdict. Out of scope otherwise. | none new |
| 9. Writer's check brings the app up per call | Rejected. The stack stays up. | F1, F8 |
| 10. Restate a claim to a missing service's 500 | Rejected. The claim is gapped instead (invariant 4). | F4 |

### Open lookups

- **L1.** How scenarios are grouped, and why one holds 2656 checks. Decides the Scope
  reshape.
- **L2.** How often an arrangement runs per lap, and what isolates arrangements. Decides
  Arrangement and Identity.
- **L3.** What a stopped journey records for the checks after it. Decides Unreached record.
- **L4.** Whether anything attributes a cause or picks a party today. Decides Attribution.
- **L5.** Whether the loop measures progress or bounds laps. Decides Stall rule.
- **L6.** Whether the grammar can state a capability need or a gap. Decides how a
  claim names a capability.
- **L7.** How a route's id is filled, and whether a reply's value can bind it. Decides
  Binding.
- **L8.** How a token reaches a request, and whether anything re-mints one. Decides
  Identity.
- **L9.** What the writer's check runs and whether it reuses the stack. Decides Stack.
- **L10.** Which of invariant 7's checks exist before a run. Decides Static check.

## 5. Mapping onto the existing system

### Revision log

- **R1.** §4, Arrangement pattern. Each scenario runs in its own harness process
  (`ostler/ostler/qa/harness/ostler_qa.py:2054-2057`). A precondition built once per lap
  must hand its facts to later scenarios through the lap record, not through memory.
- **R2.** §2, Routing. The app's owner is a party. The existing blocker record already
  names one (`workflows/src/workhorse_workflows/okf_book/shared/blockers.py:25`).
- **R3.** §2, Authoring and Environment. Capability need folds into Precondition. A
  fixture already declares the secrets it needs. When one is missing, the harness tags the
  fault `environment` (`ostler_qa.py:980-987`). A capability is therefore a precondition
  whose arrangement probes the service. The inventory is the set of probes that held. A
  second declaration beside the precondition would be two owners for one fact.
- **R4.** §1, §2 Routing and Judging, §3, §4, §6. Amended aim 8 makes attendance a
  pyramid: a blocked level asks an agent above it before a person. The note sent every
  cause outside the book to "the operator" and cited aim 8, without meeting its condition
  that a person is asked only what only a person can answer. Party becomes a level: a
  page's writer, the attendant or a person. `Side` (`blockers.py:20-26`) mixes the cause
  with the party, so the design splits them. Operator question becomes Escalation, whose
  answer names the signatures it settles, so each writer reads only its own (aim 2, three
  narrower rooms). A failure no rule matches is unattributed and goes up, never to the
  book by default.
- **R5.** §6, slice 1. Building Attribution refined its rules. A fault on a fixture page
  that is not `environment` is the arrangement's. A request that could not connect is the
  environment's. A 401 or 403 on a claim that expects success is the arrangement's when a
  fixture issued the credential it sent, the book's when it sent none, and unattributed
  otherwise. The harness matches the credential to its fixture by value and records only
  the page. A Signature is keyed by cause, precondition page, reply status and route
  shape, the method with the first path segment. Cause has no tool member, because no rule
  can tell ostler's own defect from evidence yet. Slice 1 extends the blocker's `Side`
  with environment and unattributed instead of splitting cause from party, which waits on
  Escalation. The done-when is measured on the next run's output, since run 17's output
  predates the exchange evidence the rules read.
- **R6.** §2 Routing, §3, §6, §7 A10. An attendant does not always run, and when one
  does, nothing fixes how it works. Any agent may answer a gate, so the rules for settling
  it live in the run and the gate, never in one attendant's prompt. Escalation's answer
  stops being a list of settled signatures. Each finding carries its Rerun instead, and
  the run reruns it on answer and closes what passes (invariant 11). An answering agent
  may edit the book. A Book snapshot taken when the gate opens lets the run send a changed
  expected outcome back to its page's writer (invariant 12). Run 17 showed why: its stall
  folded the super-admin seed's HTTP 400 into one workflow blocker, so the gate named no
  page and no command.

### Parts

| Part | Verdict | Where | Finding |
|---|---|---|---|
| Authoring | Exists | the ostler-okf grammar, the write and repair turns | The writer receives every failure, whatever its cause. That is Routing's mismatch, not Authoring's. |
| Arranging | Reshape | harness fixtures, `ostler_qa.py:963-977` | Arrangements run again in every scenario and share one app with no isolation (`v2.py:84-119`). |
| Environment | Reshape | `ostler/ostler/qa/stack.py` | The stack starts and is adopted when it already serves (`stack.py:426-436`). Nothing records which outside capabilities it has. |
| Observing | Exists | harness and driver | The reply is recorded since `ostler_qa_responses.py:56` and `ostler_qa.py:1044`. Checks after an abort are lost (see Unreached record). |
| Judging | Reshape | `main/flow.py:208`, `ostler_qa.py:854-859` | The flow calls every failure book-side unless the stack is down. The harness tags a fixture fault `defect` or `environment`, but nothing reads the tag (`drivers.py:353-393` has no branch for it). |
| Routing | Reshape | `shared/scenarios.py:115-142`, `main/flow.py:223-237` | Each failure becomes a problem on each page it touches. The gate asks once per lap, about every blocker. |
| Converging | Reshape | `main/flow.py:145`, `:185-188`, `:245-252` | Laps run with no cap and no comparison between them. The only early probe is a writer running a fixture page. |

### Concepts

**Authoring**

| Concept | Verdict | Where and finding |
|---|---|---|
| Claim | Exists | endpoint claims compiled by `compile_http.py:361-393`, one `qa.claim` each |
| Precondition | Reshape (revised, R3) | a `fixture` page. Its `secrets:` names an outside need (`node-types/fixture.md:26`), but only a harness env var, never a capability of the app's stack. |
| Grammar | Exists | `base-library/library/skills/ostler-okf/` |
| Static check | Exists, partly | Undeclared fixture: `doctor.py:552`. An id with no binding: `compile_http.py:300-303`. No check knows a route needs a credential, so the 656 checks sent with no header were caught only by a run. The design does not add one (A7). |
| Writer turn | Exists | `repair_batches.py:131`, `main/prompts/repair-pages.md` |

**Arranging**

| Concept | Verdict | Where and finding |
|---|---|---|
| Arrangement | Reshape | runs at the top of every scenario that names it (`plan_source.py:146-158`), memoized within the scenario only (`ostler_qa.py:963-968`). The design builds it once per lap (R1). |
| Identity | Reshape | a token resolves per request from the fixture's facts (`ostler_qa.py:794-832`). Nothing notices a revoked token or re-mints one. |
| Binding | Reshape | captures exist (`captures.py:20-44`). A journey binds `{name}` on its own (`compile_http.py:520-530`), but an endpoint claim keeps the literal `{id}` and still sends the request (`compile_http.py:300-303`). That is the 186 checks that expected 200 and got 404. |
| Scope | Reshape | one scenario per page for endpoints (`plan_source.py:188-193`). An endpoint claim that fails does not stop its page (`ostler_qa.py:1241-1245`). A failed fixture at the top of a page still fails every claim below it. |
| Arrangement probe | New | today's nearest is the writer's command on a fixture page (`scenarios.py:190-202`), which runs a whole scenario and only when a writer asks. |

**Environment**

| Concept | Verdict | Where and finding |
|---|---|---|
| Stack | Reshape | the writer's check brings the stack up and releases it on every call (`main/nodes/exercise.py:45-58`). The design keeps it up. |
| Capability inventory | New (revised, R3) | lives with the lap record in ostler, from the capability preconditions' probes |
| Environment gap | Exists, unused | the `environment` fault class (`ostler_qa.py:873-895`, `:983`) |

**Observing**

| Concept | Verdict | Where and finding |
|---|---|---|
| Exchange | Exists | `reply_excerpt` masks tokens (`ostler_qa_responses.py:56`), and both status paths keep the reply |
| Check | Exists | `FailedCheck` in `drivers.py`, rendered by `scenarios.py:58` |
| Unreached record | Reshape | an abort adds one sentinel check and drops every check after it (`drivers.py:419-444`). The sentinel is not in `failed_checks` (`v2.py:192-200`). This is why 10 of 12 failing journeys reported a traceback and no check. |
| App trace | New | the app's log is one file per stack, overwritten on the next start. No exchange points into it. |

**Judging**

| Concept | Verdict | Where and finding |
|---|---|---|
| Verdict | Reshape | a scenario carries a status and `aborted`. A check has no unreached or gapped verdict. Gaps exist only as compile gaps (`compile.py:63-94`). |
| Cause | Reshape | two values exist, `defect` and `environment`, for fixtures only |
| Attribution | New | in ostler, beside the driver that reads the harness records, because only ostler sees the exchange, the fault and the binding (A4) |
| Signature | New | in ostler's run summary, so every consumer gets the grouping |

**Routing**

| Concept | Verdict | Where and finding |
|---|---|---|
| Party | Reshape (revised, R2, R4) | `Side` (`blockers.py:20-26`) has book, ostler, app and workflow. It lacks the environment, and it mixes the cause with the party. Cause takes the kinds, and Party keeps only the three levels. |
| Finding | Reshape | one problem line per failed check per page (`scenarios.py:115-142`). The design sends one per signature, and only book causes to a page. |
| Escalation | Reshape (revised, R4) | the gate asks about every blocker as one block of text (`main/flow.py:223-237`). Its answer reaches every repair turn as prose a writer must interpret (`operator_answer.py`, `repair-pages.md:27-34`). groom's attendant can already answer a gate (`groom/groom/attend.py`). The design makes it the gate's first reader and gives its answer a list of signatures. |
| Turn budget | Exists | `turn_budget.py`, writer runs capped at 24 (`writer_commands.py:24`) |

**Converging**

| Concept | Verdict | Where and finding |
|---|---|---|
| Probe order | New | the plan runs API, then CLI, mobile, pages, journeys (`compile.py:447-451`). No stage stops the next. |
| Lap | Exists | `check_book` then `run_book` (`main/flow.py:145`, `:185-188`) |
| Progress ledger | New | `write_run` keeps only the latest run's summary (`main/flow.py:201`) |
| Stall rule | New | after an answer, blocked books route again with no cap (`main/flow.py:245-252`) |

### What the existing system has that the design lacks

- **`known-defect:`** excuses a doctor finding tied to a seed (`bullet-grammar.md:426-445`).
  It covers static findings, not run failures. It is outside this problem, so it is
  neither waste nor a missed concept.
- **Per-scenario daemon restart** (`v2.py:107-108`). It isolates a daemon, not a database.
  It does not answer F5, so the design leaves it alone.
- **Repair rounds capped at 3 within a pass** (`repair_book_flow.py:42`). Part of Turn
  budget.

### Claims against the existing system

| Claim | Existing system | Design |
|---|---|---|
| 1. Scenarios grouped by page | follows (`plan_source.py:188-193`) | keeps it until Scope is needed (A6) |
| 2. Arrangement runs in every scenario | follows (`plan_source.py:146-158`) | rejects |
| 3. Whole book before repair | follows (`main/flow.py:204`) | rejects |
| 4. "expected X, observed Y" | follows (`scenarios.py:58`) | extends |
| 5. Every failure is book-side | follows (`main/flow.py:208`) | rejects |
| 6. Answer reaches every turn | follows (`repair-pages.md:27-34`) | rejects, routes by signature (R4) |
| 7. Arrangement mismatch stops the journey | follows (`drivers.py:419-444`) | keeps, records unreached |
| 8. Snapshot claims gapped | follows (`compile.py:63-94`) | keeps |
| 9. App up per writer call | follows (`exercise.py:45-58`) | rejects |
| 10. Restate to the 500 | my gate answer only | rejects |

### Lookups

L1 to L10 are resolved in the tables above. The scenario that holds 2656 checks is not
attributed to one cause. An endpoint page carries every claim of every endpoint on it
(`compile_http.py:361-387`). That is enough for Scope, so the lookup stays closed (A6).

## 6. Slices

1. **Name the cause of each failure.** Attribution with five rules:
   - a fault the harness tagged `environment` is the environment's;
   - a 401 on a token that answered earlier is the arrangement's;
   - a 404 on a route that still holds `{…}` is the book's;
   - a 5xx is the app's;
   - a reply below 500, on a route whose preconditions held, that differs from its claim
     is the book's.

   A failure no rule matches is unattributed (R4). Signature groups them. Routing sends
   book and arrangement causes to the pages' writers. It sends one finding per other
   signature up to the attendant, with its count.
   Touches: Judging (Cause, Attribution, Signature), Routing (Finding, Party,
   Escalation), Observing (Exchange).
   Done when: replaying run 17's output yields at most 30 signatures, and the four causes
   the attendant found by hand each appear as one signature with a count. The repair batch
   from that output carries none of them, and no unattributed failure.
2. **Record what an abort skipped.** A stopped journey records every check after the step
   that stopped it as unreached, with that step's cause.
   Touches: Observing (Unreached record), Judging (Verdict), Converging (Progress ledger).
   Done when: a run's output holds a verdict for every claim, and each of the 10 aborted
   journeys is one signature.
3. **Probe the preconditions first.** Before the book runs, every precondition builds on
   its own and its promise is probed. A token must answer on a route that needs one. A
   failing probe stops the lap and goes to the writer of its fixture page, with the
   probe's exchange. A probe that still fails after that writer's turn goes up to the
   attendant (R4).
   Touches: Arranging (Arrangement probe, Identity), Converging (Probe order), Routing
   (Escalation).
   Done when: the admin with no account row reaches the fixture's writer within 10
   minutes of a run's start, and the attendant one writer turn later.
4. **Build each precondition once per lap.** Facts pass through the lap record (R1). Each
   precondition that needs a user creates its own.
   Touches: Arranging (Arrangement, Identity, Scope).
   Done when: a lap shows no revoked-token signature, and the seed runs once per
   precondition.
5. **Gap a claim whose capability is absent.** A capability precondition probes the
   service. Its claims get the gapped verdict when the probe fails, and never reach a
   writer.
   Touches: Authoring (Precondition), Environment (Capability inventory, Environment gap),
   Judging (Attribution).
   Done when: billing claims read "gapped: payment provider absent" on a stack with no key,
   and pass on a stack with one. The attendant parks the gap for a person, because only a
   person can supply the key. It is the one cause in this design that reaches a person.
6. **Stop a lap that did not help.** The ledger keeps each lap's counts by cause. The
   attendant is asked when the book's count does not fall. It reshapes the prompt or the
   workflow and reloads the run. A person hears of it only if the attendant leaves the
   escalation open (R4).
   Touches: Converging (Progress ledger, Stall rule), Routing (Escalation).
   Done when: the report shows the trend per lap, and a flat lap raises an escalation to
   the attendant with it.
7. **Keep the stack up for writers.** The writer's check adopts the stack and leaves it
   up. It lands after slice 4. A stack kept up keeps whatever one arrangement did to
   another's identity, and slice 4 is what stops that.
   Touches: Environment (Stack).
   Done when: a writer's second check starts its scenarios in under 10 seconds.
8. **Let any attendant settle a gate.** Each blocker in a gate names its cause, the
   shared pages it lives in, and its Rerun. A stall lists each signature still on the
   writers' side as its own blocker, with the lap trend as its reason. When the gate
   opens, the run takes a Book snapshot. On answer, the run reruns each blocker's checks
   itself. It closes the ones that pass and routes the ones that fail to their writers
   with the new result. It then compares the book with the snapshot and sends each claim
   whose expected outcome changed back to its page's writer as a finding. Fixture,
   precondition and setup edits stay free. A blocker with no checks, such as a failed
   turn or a ceiling, names no Rerun and goes back through its book's route as today.
   Touches: Routing (Escalation, Rerun, Book snapshot, Finding).
   Done when: each blocker in a gate names its cause, the shared pages it lives in, and a
   command that reruns only that blocker's checks. On answer, the run reruns each
   blocker's checks itself, closes the ones that pass and routes the ones that fail to
   their writers with the new result. On answer, the run compares the book with its state
   when the gate opened and sends any change to a claim's expected outcome back to that
   page's writer as a finding, while fixture, precondition and setup edits stay free. The
   rules live in the run and the gate, never in one attendant's prompt, because any agent
   may attend.

## 7. Assumptions

1. **Assumption:** most of run 17's 1837 failures have a cause outside the pages.
   **Decided:** slice 1 goes first. **Basis:** the attendant's diagnosis of run 17 named
   revoked tokens, a missing payment key, an account-less admin and placeholder ids.
   About 500 checks got 401 or 403 and 186 got 404 for a placeholder. Nobody counted
   across the whole output. **If wrong:** §1 done stays. Slice order moves Authoring's
   writer turn ahead of Judging.
2. **Assumption:** rules over status, reply, fixture faults and bindings attribute most
   failures with no model. **Decided:** Attribution is an ordered rule list (§4).
   **Basis:** each of run 17's four causes has a mechanical sign. None measured over the
   whole output. Slice 1's done-when measures it. **If wrong:** §4 Attribution becomes a
   model turn per signature, and F8 weighs on it.
3. **Assumption:** a precondition built once keeps its promise for a lap when no other
   arrangement touches its identity. **Decided:** slice 4 builds once per lap. **Basis:**
   216 to 242 tokens were revoked per lap, all by seeds that ran again in later
   scenarios. **If wrong:** §2 Identity re-mints per scenario, and invariant 3 needs a
   second detector.
4. **Assumption:** Attribution and Signature live in ostler, Routing in the workflow.
   **Decided:** the mapping places them so. **Basis:** only ostler sees the exchange,
   the fault tag and the binding (`ostler_qa.py:854-859`). The workflow owns the party
   (`blockers.py:20-26`). **If wrong:** §5 placement of Attribution, and slice 1's
   touches.
5. **Assumption:** the stack's capability can be probed from the book, with no env var
   read by the workflow. **Decided:** R3, a capability is a precondition. **Basis:** the
   repo's rule that workflows read no env vars. The harness already reads a fixture's
   secret from its own environment (`ostler_qa.py:980-987`). **If wrong:** the operator
   declares capabilities on the stack page, and §2 Capability inventory moves into
   Environment's own data.
6. **Assumption:** per-page scenarios can stay once slices 2 and 4 land. **Decided:**
   Scope is not a slice. **Basis:** an endpoint claim that fails does not stop its page
   (`ostler_qa.py:1241-1245`). **If wrong:** a Scope slice after slice 4, grouping
   scenarios by precondition.
7. **Assumption:** a missing auth header needs no static check once Attribution names
   it. **Decided:** Static check is unchanged. **Basis:** a missing header shows as a 401
   with no token sent, which one rule catches. **If wrong:** a doctor check that reads a
   route's auth from the source.
8. **Assumption:** one claim per route shape is a fair early probe. **Decided:** Probe
   order's middle stage. **Basis:** 50 to 83 failures per endpoint shared one cause.
   **If wrong:** slice 3's probe covers more claims, and costs more time.
9. **Assumption:** the split between ostler (grammar, compiler, harness) and the
   workflow (loop, writers) stays. **Decided:** nothing moves between packages.
   **Basis:** the repo's map. **If wrong:** `target-architecture` owns the change.
10. **Assumption:** an agent reads every escalation before a person does, but nothing
    fixes which agent or how it works (revised, R6). **Decided:** Party's middle level is
    an agent, and Routing sends every cause outside the book to it. The gate carries every
    rule the answer needs, and the run enforces them on answer (slice 8). **Basis:** groom
    launches an attendant on a gate (`groom/groom/attend.py`), but not on every gate, and
    amended aim 8. **If wrong:** every escalation parks for a person, which is how runs
    behave today, so the cost is the time a person takes to answer.
