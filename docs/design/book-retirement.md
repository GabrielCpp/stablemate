# Retire the markdown book: coder and okf-book on the executable book

Status: accepted under the operator's standing authority, 2026-11-11. Not built.

Disclosure: written after reading an inventory of the current workflows and of ostler. Each part was
checked against "would I name this without having seen the code".

## 1. Problem

An operator who runs stories unattended pays twice for every service: an agent keeps a markdown book of
the service current (the spec pass and the document pass), and another agent turns that book into a
scenario plan and acts as the test runner. On the client's formula-editor stories the markdown work
(specify, document) cost $5 to $14 a story and the scenario QA $5 to $12, while the executable book of
the same service judged the story by a run for $1.5 to $7. The operator's rule: the markdown book is
removed from stablemate and the client, replaced by the Python book plus markdown decisions, and the
okf-book and coder workflows use only the new method, before the method is used at work.

Done, for the operator:
- A coder story on a service with a book reads and writes no markdown book page, and passes.
- An okf-book run writes a Python book for a service that has none, and the book plays green.
- No markdown page under `docs/services/` remains in either repo, and nothing in either workflow or in
  ostler reads one.

Out of scope: the author workflow (it writes stories and epics in the artifacts dir, not the book); story
and epic files themselves; the QA harness's video and evidence machinery, which the scenario lane keeps.

## 1b. Claims (from the operator and from today's record)

1. Rationale stays markdown, as decision files beside the Python book, and the story writer and the
   implementer must read them (operator, 2026-11-11).
2. The book restructures itself when a story needs it; the first structure is not a contract (operator).
3. The book must notice where an operation is underspecified against the dimensions of its inputs
   (operator; Track 48).
4. Concurrency bugs are out of the book's reach and stay with the app's own tests (operator).
5. A claim no call or backstage step can observe stays with the scenario lane (Track 44/45 record).

## 2. Parts

Level 1:
- **The story's intent in the book** owns turning a story's claims into book changes before code
  exists. It never knows the implementation. It hands the book delta to the build and the judgement.
- **The build** owns the code. It reads the book delta and the decisions as its spec. It never edits
  the book's claims; a claim it cannot meet is a block.
- **The judgement** owns the verdict: a play of the book on the story's code, and the scenario check
  of what no book can reach. It never knows how the delta was written.
- **Keeping the book current** owns the book's pointers into the code (`source=`, decisions, the index)
  after a change by anyone, a story or a coworker. It never decides a claim.
- **Backfill** owns writing a book for a service that has none. It hands a green book to the other
  parts.
- **Finding things in the book** owns search and reach for agents (which journey, which decision, which
  endpoint). It never edits.

Flow for a story: intent (spec pass) → build → keeping current (the book seat updates `source=` and the
index for what the build changed) → judgement (book play, then the scenario check of the unreached
claims). For a coworker commit: keeping current → judgement of the stale elements. For a new service:
backfill → judgement.

Level 2, the parts that change most:

| Part | Concept | Owns | Never knows |
|---|---|---|---|
| Intent | Book delta | the journeys, cells, rules and fixtures a story adds, written as intent | whether the app meets them yet |
| Intent | Decision | why a behaviour is so, with the story that settled it | the code |
| Judgement | Unreached claim | a claim no call or backstage step can observe, in the story's words | how the book is built |
| Judgement | Scenario check | a hand-written check of an unreached claim, with evidence | the book |
| Keeping current | Stale element | a book element whose cited source changed | who changed it |
| Backfill | Book draft | a new service book and its first green run | the coder lanes |

## 3. Invariants

- I1. A story's claim lives in exactly one place: the book (when a call can observe it) or the scenario
  check (when none can). Owner: the judgement, which defers the book's pages and keeps the unreached
  list.
- I2. The spec pass never runs the app; it ends on `ostler book check`, and new claims are expected red
  until the build. Owner: the intent part.
- I3. A book change that touches a shared part is judged by the whole book. Owner: the judgement (Track
  45).
- I4. No workflow reads `docs/services/**.md` once its repo has switched. Owner: a gate (a test that
  greps the workflow package and the prompts for the path) in each repo.

## 4. Forces and patterns

- F1. A repo switches service by service: some services have books, some do not yet. Pattern: the
  existing coverage test (a story service is covered when `services/<name>/service.py` exists) picks the
  lane per service; an uncovered service keeps the markdown lanes until its book exists. No flag.
- F2. Writing intent before code and judging after code use the same book. Pattern: the spec pass
  writes the delta and commits it on the story; the book lane later plays it and may restructure it.
- F3. The markdown spec pass and document pass each cost a seat turn. Pattern: for covered services the
  document pass is removed; the book lane's seat already updates the book after the build (Track 44/45),
  so it takes over `source=` and the index.
- F4. The scenario lane's plan is compiled from markdown obligations. Pattern: for covered services it
  has no obligations left (Track 44 defers them); its seat writes checks only for the unreached claims,
  by hand, as it already does for `unreached`.

Rejected: generating markdown from the Python book for human reading. The operator wants one book; a
generated twin is a second thing to keep in step. Decisions stay markdown by claim 1, and they are
written, not generated.

## 5. Mapping onto the existing system (from the inventory, 2026-11-11)

- Intent: **reshape**. `coder/docs` spec pass (`docs/flow.py:98-125`, `specify-story.md:85-130`) writes
  OKF nodes through scaffold, checks, fmt and doctor. For a covered service it instead writes the book
  delta with the `ostler-book` skill and ends on `ostler book check`. `record_spec_nodes`
  (`main/nodes/spec.py`) records book paths instead of nodes; the dev prompt's "The book is this story's
  spec" section (`_dev-inputs.md`) lists them.
- Build: **reshape**. `_dev-scope.md:57-60` ("merge into the book in the docs phase") changes to "the
  book lane updates the book".
- Keeping current: **reshape**. The document pass (`document-story.md`, `verify_story_documentation`,
  `commit_book_delta`, `stamp_specs`) is skipped for covered services; the book lane's seat updates
  `source=` and the index, and `ostler book stale --app` names what a coworker commit staled.
- Judgement: **exists** (book lane, Tracks 44-45, 48). The scenario lane's packet
  (`build_okf_context`, `qa/flow.py:54-167`, `qa-story.md:43-133`, `_qa-plan-contract.md`) stays for
  uncovered services; for covered ones it has only the unreached claims, and `_qa-setup-brief.md`'s
  stack page (`docs/services/<service>/ops/qa-stack.md`) moves to the book's `surface.py`/environment.
- Backfill: **reshape**. okf_book (`write_book_flow.py`, `write-book.md`, `writer_ostler.py` allowing
  scaffold/fmt/gc/relink) writes a Python book with the `ostler-book` skill, gated by `ostler book check`
  and a green `ostler book run` on a stack copy. `reground_book_flow.py` becomes the stale-driven update.
  `exercise_book_flow.py` becomes the book run.
- Finding: **reshape**. Agents use `ostler book` search (`ostler/book/search.py`, `index.tsv`) instead of
  `ostler search`, `trace` and `reach` over markdown.
- Stack bring-up: **reshape**. The book lane still finds its stack through the markdown graph.
  `stack_target` loads it to name the story's surfaces (`coder/shared/stack.py:33-34`), and
  `ensure_stack` brings no stack up unless the graph holds a served surface (`kit/qa/runner.py:142-151`).
  `release_copy` reads it the same way (`kit/qa/runner.py:107-109`). With `docs/services/**` gone the
  lane would play every book against no stack. The bring-up keys on the repo's stack copy and the
  covered services' `service.py` instead, before slice 5.
- Removal: **new**. After both repos switch: the markdown-only ostler commands (doctor, stamp, fmt, gc,
  checks, reach, search, trace, graph, refs, scaffold and their modules, `qa/context.py` and
  `qa/compile_*` once no uncovered service is left), the `ostler-okf` skill, the markdown parts of
  `ostler-cli` and `ostler-repo-docs`, `policies/repo/okf-book.md`, `scripts/bench_ostler_doctor.py`
  and `make bench-doctor`. The import graph decides the exact list at that step; the names above are an
  inventory by name.

## 6. Slices

1. A covered client API story with no markdown: spec pass writes the book delta, document pass skipped,
   scenario lane judges only unreached claims and web. Done when a live story passes and its diff holds no
   `docs/services/api/**` change.
2. The client web book (Track 47) makes web a covered service: a screen story with no markdown. Done as 1.
3. okf-book writes a Python book: backfill one stablemate service (after Track 50's command surface).
   Done when the written book plays green and its run is priced.
4. Stablemate's services all covered (backfill the rest), then a stablemate coder story with no markdown.
5. Delete the client's and stablemate's `docs/services/**`, then the markdown-only tooling, with the I4
   gate in both repos. It waits on the stack bring-up reshape in section 5.

## 7. Assumptions

- A1. The spec pass can write a useful book delta before the code exists. Basis: the story-first passes
  of Track 36 and slice 2a wrote claims from the story; they ran against built code, so the pre-build
  case is untested. If wrong: the delta moves to the book lane after the build, and the spec pass keeps
  only the behaviour model in the spec dir.
- A2. Removing the document pass loses nothing the book lane does not do. Basis: Track 42 priced both
  at the same order; the doc pass's grounding (`code:`) has the book's `source=` as its counterpart. If
  wrong: a slim pointer pass stays.
- A3. Every client and stablemate surface fits HTTP, gRPC, web, mobile or command. Basis: the inventory;
  stablemate's groom is HTTP and web. If wrong: a surface is added before its repo's slice 5.
- A4. The scenario lane's packet machinery can be deleted once no uncovered service is left. If wrong:
  it stays for repos that keep a markdown book, which the operator ruled out for these two.
