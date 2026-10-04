# A run that notices its repairs stopped working

> **Disclosure.** I read the existing solution before this design started. That covers the
> okf-book workflow and its repair loop, the ostler compiler and its failure attribution,
> groom's alerts, and `okf-book-convergence.md`. I also wrote parts of them, and I answered
> the API book's gates during the run this note is about. Each decision that reached me
> through them is a claim in section 1b.

## 1. Problem

**Who feels it.** The operator who leaves a book run unattended. The API book of the
`acme` repo ran 99 hours. About 87 of them went to some 360 repair turns of about ten
minutes each. The same pages were rewritten 25 to 56 times. About 150 of its last 400
failures came from a sign-in token the test compiler dropped, which no page edit could
change. The run kept reporting progress, because its total failure count still fell
slowly. The run did stop at gates. Each gate blamed the pages, so the answer was "keep
repairing".

**Done looks like this.**

- No failure reaches a writer more than 3 times after the writer changed the section it
  sits in. Today one page reached its writer 56 times.
- A failure whose page edits never change the request the check sends is held after the
  second such edit. On the API book that means within the first repair round, a few hours
  in, not never.
- Each held failure reaches whoever answers the gate with the evidence that names its
  side. The evidence says what the page said and what the check sent. It says whether the
  request changed and what the app answered. Many failures with one cause arrive as one
  item.
- The rest of the book keeps converging while those failures are held. Nobody has to be
  watching.

**Out of scope.**

- The compiler defect itself, fixed in `b6e3af3c`.
- Model cost and provider quotas.
- The lap-level judgement of whether the book as a whole improves. That belongs to
  `okf-book-convergence.md`, and this note adds a finer signal beside it.
- How an attendant agent is launched or kept alive.

## 1b. Claims

1. Detection could be a new skill. (operator)
2. Detection could be a loop. (operator)
3. Detection could reuse an existing skill. (operator)
4. Stop a page after 5 rewrites that leave the same failure, and ask. (my reply to the
   operator)
5. Groom's `churn` alert and `groom wait` are the channel to the attendant. (groom)
6. A lap that does not lower the book's failure count is the stall signal. (workflow)
7. A 401 on a check that sent no credential is the book's fault. (ostler attribution)

## 2. Parts and concepts

### Level 1: parts

1. **Attempt memory.** It owns the history of each failure: every repair that touched its
   section, and what the next check saw. It never knows why a failure happens. It hands the
   history to Judging.
2. **Effect test.** It owns one question: did this edit change what the check sends or
   asserts? It never knows the app's reply. It hands its answer to Attempt memory.
3. **Judging.** It owns the verdict that a failure is churning. It never knows who will fix
   it. It hands churning failures to Naming.
4. **Naming.** It owns the side a churning failure points at: the book, the toolchain that
   turns pages into requests, the app or its environment. It never knows how that side gets
   fixed. It hands named failures to Holding.
5. **Holding.** It owns which failures writers may still receive. It never knows the cause.
   It hands each hold to Telling.
6. **Telling.** It owns what the gate answerer receives, and when. It never knows what the
   answerer does with it.

**Flow.** It runs at two moments.

- **After a repair turn.** Effect test compares each touched section's compiled checks
  before and after the edit. Attempt memory records an attempt for each failure in a
  changed section.
- **After any check of those failures**, whether in the writer's own run or in a lap.
  Attempt memory records what the check saw. Judging reads the history. A churning failure
  goes to Naming, then to Holding, then to Telling. Writers stop receiving it. The run goes
  on with the rest.

In one paragraph: the run remembers what each fix attempt changed and whether the failure
moved. When a page keeps being rewritten and the failure stays put, the run stops sending
it to the writer. It works out from the evidence whether the page, the test tooling, or the
app is the likely culprit. Then it tells whoever answers its questions, at once, and gets
on with everything else.

### Level 2: concepts

**Attempt memory**

| Concept | Owns | Never knows |
|---|---|---|
| Failure key | The identity of a failure across edits: page, section and the expected-versus-observed outcome | Claim numbering, which shifts when a writer inserts a claim (A5) |
| Attempt | One repair that changed the section, with the Effect test's answer | The failure's cause |
| Observation | One check's outcome for a failure key, and when it ran | Which repair preceded it |
| History | The ordered attempts and observations of one key | Judging's thresholds |

**Effect test**

| Concept | Owns | Never knows |
|---|---|---|
| Compiled check | The request and the assertions one section compiles to, as text | The app |
| Edit effect | Whether a section's compiled checks differ before and after one edit | Whether the failure persisted |

**Judging**

| Concept | Owns | Never knows |
|---|---|---|
| Dead-edit rule | A key whose section changed twice while its compiled checks stayed the same is churning | Causes |
| Same-failure rule | A key that saw the same outcome after 3 attempts is churning | Causes |

**Naming**

| Concept | Owns | Never knows |
|---|---|---|
| Contrast table | Rows mapping a history's shape to a side, first match wins | Holding |
| Shared cause | Grouping named failures that share a side and an observed outcome | Individual pages' text |

The first rows of the contrast table:

| History shape | Side |
|---|---|
| Section changed, compiled checks unchanged, and the page arranges what the request lacks | toolchain |
| Section changed, compiled checks unchanged | toolchain or grammar misuse |
| Request changed every attempt, observed outcome unchanged | app or environment, or the claim is wrong |
| Many keys on many pages share one observed outcome | one shared cause, named by the largest group |
| None of the above | book |

**Holding**

| Concept | Owns | Never knows |
|---|---|---|
| Hold | The set of failure keys writers no longer receive | Why each is held |
| Release | When a hold lifts: an answer to the gate, or a change to the toolchain's version | What changed in the toolchain |

**Telling**

| Concept | Owns | Never knows |
|---|---|---|
| Finding | One item per shared cause, with its side, its count, one sample's history and the command that reruns its checks | The answerer's identity |
| Notice | Publishing a finding the moment it exists, on the run's existing channels | Whether anyone listens |

## 3. Invariants

1. A failure reaches a writer at most 3 times after its section changed with the same
   outcome. Owner: Hold. Upheld by: Judging.
2. An attempt counts only when the repair changed the section the failure sits in. Owner:
   Attempt.
3. Every held key appears in exactly one finding. Owner: Finding.
4. A held key is released only by a gate answer or by a toolchain version change. Owner:
   Release.
5. A held key never ends the run as passed or as book debt. It ends as a finding. Owner:
   Finding.

## 4. Forces and patterns

### Forces

1. **Nobody is guaranteed to watch.** Detection and the stop-loss must live in the run.
2. **A repair turn is expensive.** It takes about 10 minutes and about 5M tokens, so
   detection must fire within 2 or 3 turns of a page, not after a lap of about 2.4 hours.
3. **The causes of churn vary and grow.** Compiler gaps, app quirks, missing services and
   wrong claims all churn.
4. **The answerer is an agent or a person.** The evidence must be plain text in a channel
   both already read.
5. **Claim numbers shift under edits.** History cannot be keyed by position.
6. **The rules must be testable without the app.** The verdict and the effect test run on
   recorded history.
7. **A toolchain fix lands mid-run.** Held failures must retry after a reload that changes
   the toolchain.

### Between parts

- **One append-only history, read by the rules** (forces 1 and 6). Attempt memory writes.
  Judging, Naming and Telling only read. A replayed history reproduces every verdict.

### Inside a part

- **Contrast table** as an ordered rule table (force 3). A new cause adds a row.
- **Failure key** as a value type over page, section and outcome (force 5).
- **Release** keyed on the toolchain's code digest (force 7).
- Every other concept is a plain function or a plain value.

### Claims

1. **New skill.** Rejected by force 1. A skill runs only when an agent runs it.
2. **Loop.** Rejected by force 1. A loop is an attendant, which the run cannot count on.
3. **Existing skill.** Rejected for detection by force 1. `diagnosing-bugs` and
   `root-cause` stay useful to whoever answers a finding.
4. **Stop a page after 5 same-failure rewrites.** Re-derived from force 2 as 3 attempts per
   failure, and 2 for a dead edit (A3).
5. **Groom's channel.** Kept only as Notice's optional second channel (force 4). It
   detects nothing (force 1).
6. **Lap-level stall.** Kept, unchanged. It misses a book whose total falls while some
   failures churn, which is the case here.
7. **No credential sent means the book's fault.** Rejected by the contrast table's first
   row. The page may have arranged one that the compiler dropped.

### Open lookups

- L1: Can one section's compiled checks be isolated from the compiled plan? Effect test
  waits on it.
- L2: Does the writer's in-turn check run record per-check outcomes the run can keep?
  Observation's timing waits on it.
- L3: Where does the run choose which failures a repair batch receives? Hold waits on it.
- L4: How does the gate list blockers, and can one be recorded mid-run? Telling waits on it.

### SOLID

Each Owns cell reads without "and". A new cause adds one row to the contrast table. A new
churn rule adds one concept in Judging and changes nothing else. Holding never reads
causes, and Telling never reads rules.

## 5. Mapping onto the existing system

### Revision log

None yet.

### Parts

| Part | Verdict | Where |
|---|---|---|
| Attempt memory | **New** | `okf_book/main/nodes/`, one module beside `progress_ledger.py`, persisted in the records dir like `progress.json` |
| Effect test | **New** | uses ostler's compile. L1 resolved below |
| Judging | **New** | beside the history. `progress_ledger.py` owns the lap rule, a different concern |
| Naming | **Reshape** | `ostler/ostler/qa/attribution.py:121` |
| Holding | **Reshape** | `okf_book/main/flow.py:273-282` |
| Telling | **Reshape** | `okf_book/main/flow.py:284-309` |

### Findings

- **The run keeps no per-failure history.** The checkpoint's `run_failures` holds the
  current lap only. `progress.json` holds one count per cause per lap. The API run's 41
  laps show the book total fall from 1202 to 400. It sat flat twice, at 1202 and at 1012,
  and those stalls fired. Nothing records that one check failed the same way across 50
  edits.
- **Attribution blames the book for a dropped credential.** The rule at
  `attribution.py:121` returns the book's cause when a 401 check sent no credential. The
  rule cannot see whether the page arranged one. The compiler dropped exactly that kind
  of credential. So every stall blocker went to the book side (`flow.py:287-290`), and the
  gate answer sent it back to the writers. The design is right and the code is wrong: a
  rule that sees one lap cannot separate "never arranged" from "arranged and dropped".
- **Every lap's failures go back to the writers.** `flow.py:273-282` routes all failures
  to the next repair. No subset is ever held back. Holding is the missing filter.
- **Blockers reach a person only at the end of the run.** `flow.py:298-309` opens the gate
  after the last surface. A one-surface run with churning failures reaches it only when
  every lap stalls. With Holding in place, the rest converges and the gate comes sooner.
- **Groom watches node repeats, not failure repeats.** Its `CHURN` rule fires on one node
  repeating with one label signature (`groom/groom/alerts.py:265-272`). Every repair turn
  carries a new label, so it never fires. `churn` is also missing from groom wait's
  default events (`groom/groom/attention.py:14`). Groom belongs to another session, so
  slice 4 asks for this rather than editing it.
- **The writer runs its own pages' checks inside a turn** (`writer_commands.py:18`). This
  is L2: observations can come every turn rather than every lap, if the run keeps them.
- **The compiled plan marks each claim's block** with its page and claim id, and each
  check carries `covers`. This is L1: a section's compiled checks are the blocks whose
  ids name that section.

### Claims against the existing system

The existing system follows claims 5, 6 and 7. The design keeps 6, demotes 5 to a second
channel and reverses 7.

## 6. Slices

1. **A dead edit is held and named.**
   - Touches: Effect test, Attempt memory, the dead-edit rule, the first contrast row,
     Hold and Finding.
   - Done when: a test replays a book whose token sits under a `when:` line, against the
     compiler before `b6e3af3c`. After two repair turns that change the section, the
     failure leaves the writers' batches. A blocker on the toolchain side records the
     section's text and the unchanged request.
2. **A same-failure churn is held.**
   - Touches: Observation and the same-failure rule.
   - Done when: a failure that saw the same outcome after 3 attempts that changed its
     request is held, with the app named as the likely side.
3. **Shared causes group into one finding.**
   - Done when: 40 held keys on 20 pages that share one outcome and one side produce one
     finding with the count 40.
4. **Release and notice.**
   - Done when: a `reload --core` that changes the toolchain digest returns held keys to
     the writers. Each new finding also emits the run signal groom can turn into an alert.
     The groom side is handed to its owner.

## 7. Assumptions

1. **A5. A failure keeps its identity across edits when it is keyed by page, section and
   outcome.**
   - Decided: the key ignores claim numbers.
   - Basis: claim numbers are positions, and writers insert claims.
   - If wrong: Failure key and invariant 2. A section split by a writer would start a
     fresh history, which costs at most 3 more turns.
2. **A1. Compiling the touched pages after a turn costs well under a turn's ten minutes.**
   - Decided: Effect test runs after every repair turn.
   - Basis: none. The whole API book compiled in one tool call, untimed.
   - If wrong: Effect test runs on the turn's pages only, or once per round.
3. **A3. Thresholds of 2 dead edits and 3 same-outcome attempts.**
   - Decided: the rules use them as constants.
   - Basis: pages were rewritten 25 to 56 times. Three attempts cap a page's waste near 30
     minutes. The exact numbers are a guess.
   - If wrong: Judging's two rules. A threshold too low holds failures a writer would have
     fixed. The finding's rerun command recovers those.
4. **A6. In-turn check runs give an observation per turn.**
   - Decided: Observation records the writer's own runs as well as laps.
   - Basis: `writer_commands.py:18`.
   - If wrong: verdicts arrive per lap, about 2.4 hours apart, and slice 1's done-when
     needs two laps.
5. **A4. A held failure may wait until the end-of-run gate when nobody listens.**
   - Decided: no mid-run gate. Holding stops the waste, and Notice tells any listener.
   - Basis: the operator said an attendant may or may not run.
   - If wrong: Telling opens a gate mid-run, which halts the rest of the book.
