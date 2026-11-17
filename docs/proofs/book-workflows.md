# Proofs that the book workflows run on their own

Each entry is one workflow run on a real app and what it showed. A claim enters this page only
after a run has shown it. "By hand" counts every act of a person or of an attending agent after
the launch. The client is a private web app with several backend services; it is called the
client web app here, and its services by their role.

Read a row as: the run, pinned to a stablemate commit, did this with nothing done by hand beyond
what the row says, and the evidence lives where the row points. Groom run ids resolve with
`groom status --run <id>`. Client-side details live in the goal record
`TRIED.md` of the goal record under the operator's artifacts folder.

## 2026-11-16: catch_up moves an existing book onto the current format, from a worktree

- **Run:** okf-book `catch_up`, groom run `w3-report-format`, on the client's report service book.
- **Stablemate:** launched at `ddffeacd4`; reloaded onto `504a344da` and then `c66b6f681` to
  fix the causes of two gates (below).
- **Proved:** the run filed a book behind on the book format, sent the skill's 26 changes since the
  book was written to one owner turn, played the whole book, recorded the format the book was
  judged against (`FORMAT`), and committed the book with the run's own commit. After it, the book
  holds every login as a self-renewing `Signed` credential and runs its SQL through
  `environment.exec`, with no shell-out to the ostler command line left in its backstage. The
  owner answered each of the 26 changes as applied or not applicable, with the reason.
- **Proved, worktree:** the run worked in a client worktree whose folder is not named like the
  repository. Its stack copy was brought up from the main checkout, extended by the owner from
  the worktree with `ostler env up`, played from the worktree and torn down from it.
- **Gates' last lines:** check passed; whole play `4 pass, 0 known defects, 0 fail`, `twins: 8
  pairs played, 0 underspecified`; stamp and mark written, `report: format mark a48159c2c`.
- **Cost:** $1.86 over three Sonnet owner turns, 19 minutes of turns. Wall 146 minutes, of which
  most was two operator gates waiting on the attendant. Copy up in 29 seconds, no image build.
- **By hand:** two operator gates, each answered by the attending agent after it fixed the cause in
  stablemate. (1) The owner prompt forbade starting anything, so an owner could not add a service
  its book's stack left out (`504a344da`). (2) A play that reaches a service its own services do
  not need to start had no place in the stack format: `needs` is start order and made a cycle.
  ostler gained `reaches:` (`e755b492c`) and the prompt points at it (`c66b6f681`). The owner then
  declared `reaches: [api:api]` itself.
- **Evidence:** groom `w3-report-format`; client commit `5dc054ab6`.

## 2026-11-16: python_book completes an existing book

- **Run:** okf-book `python_book`, groom run `w3-report-complete`, on the client's report service
  book after the format run above.
- **Stablemate:** `d9cc81ed3`.
- **Proved:** an existing book with 26 of 81 source files named by no element was completed in one
  lap: check clean, whole play green, `missing` empty, stamped verified at the app's HEAD, format
  mark written, committed by the run. Played from a worktree.
- **Gates' last lines:** `4 pass, 0 known defects, 0 fail`; `0 of 81 files are in no element and
  under no ignore pattern`; `nothing stale` read on client master after landing.
- **Cost:** $0.64, one Sonnet owner turn of 5 minutes. Wall 8 minutes. Copy up in 49 seconds.
- **By hand:** nothing beyond the launch.
- **Evidence:** groom `w3-report-complete`; client commit `04f6dd0c8`.

## 2026-11-16: python_book completes an existing book after a red play

- **Run:** okf-book `python_book`, groom run `w3-docs-api-complete`, on the client's docs api
  book (an HTTP service).
- **Stablemate:** `d9cc81ed3`.
- **Proved:** a book with 21 of 97 source files named by no element, and a changed seeding script
  no element named, was completed in two laps. The first lap's whole play was red, the flow sent
  the play's output back to the owner, and the second lap ended green. Then `missing` was empty,
  the book was stamped and marked, and the run committed it. Played from a worktree.
- **Gates' last lines:** `12 pass, 0 known defects, 0 fail`; `nothing missing` and `nothing
  stale` read on client master after landing.
- **Cost:** $1.28, two Sonnet owner turns of 17 and 3 minutes. Wall 27 minutes. Copy up in 28
  seconds.
- **By hand:** nothing beyond the launch.
- **Evidence:** groom `w3-docs-api-complete`; client commit `7115236fd`.

## 2026-11-16: python_book completes an existing screen book

- **Run:** okf-book `python_book`, groom run `w3-docs-app-complete`, on the client's docs app
  book (a web screen book).
- **Stablemate:** `939d70ae2`.
- **Proved:** a screen book with 209 of 425 source files named by no element was completed with
  the breadth and reasons passes and two owner laps, the first whole play red and the second
  green. Then `missing` was empty, the book was stamped and marked, and the run committed it.
- **Gates' last lines:** `10 pass, 0 known defects, 0 fail`; `nothing missing` and `nothing
  stale` read on client master after landing.
- **Cost:** $2.96 over six Sonnet turns, 51 minutes of turns. Wall 53 minutes. Copy up in 34
  seconds.
- **By hand:** nothing beyond the launch.
- **Evidence:** groom `w3-docs-app-complete`; client commit `dd458a253`.

## 2026-11-16: a first screen book refers to its backend's book

- **Run:** okf-book `python_book`, groom run `w3-todo-web`, on a copy of ostler's todo fixture
  with its web book deleted and its api book kept.
- **Stablemate:** `939d70ae2`, with the screen-book references of `d89cde80c` in the skill the
  writer read.
- **Proved:** a writer starting from no screen book wrote one that names the todo it needs by
  state from the api book (`Foreign` with the fields it reads, `Needs(TODO, "overdue")`), keeps no
  lifecycle, rule or action of the api's record, and seeds and wipes nothing in the api's store.
  Check clean, whole play green, stamped, marked and committed by the run.
- **Not proved:** the person form (`Needs` with a `Person`). The writer did not use it.
- **Gates' last lines:** `check: 0 findings`; `5 pass, 0 known defects, 0 fail`; `twins: 10
  pairs played, 0 underspecified`.
- **Cost:** $4.12 for two Sonnet owner turns; the play after the rewind spent no agent turn. Wall
  about 50 minutes.
- **By hand:** one gate, caused by the harness and not the workflow. The attendant had started the
  fixture's servers on the ports the books default to before launch; the writer gave the web book
  its own stack and reported the attendant's servers as in its way. The attendant stopped them,
  stopped the run, and rewound it to its check with `control rewind --to check` and `resume`.
- **Evidence:** groom `w3-todo-web`; the fixture repository
  `~/Documents/worktrees/w3-todo-fixture`, commit `2029c4e`.

## 2026-11-16: python_book declares the app of a command-line book

- **Run:** okf-book `python_book`, groom run `w3-farrier`, on stablemate's own farrier book, from
  a stablemate worktree.
- **Stablemate:** `939d70ae2`.
- **Proved:** a book that checked clean but declared no `App(roots=..., verified=...)`, so that
  `missing` and `stale` could not judge it, got its app declared by the owner from `missing`'s own
  refusal, with no workflow change. It ended with `missing` empty over 40 files, a whole play
  green, stamped at the commit it judged, marked, and committed by the run. One red whole play
  went back to the owner as the second lap.
- **Gates' last lines:** `8 pass, 0 known defects, 0 fail`; `nothing missing` and `nothing
  stale` read on main after landing.
- **Cost:** $3.35, two Sonnet owner turns, 38 minutes of turns. Wall 48 minutes. No stack.
- **By hand:** nothing beyond the launch.
- **Evidence:** groom `w3-farrier`; stablemate commit `8c19b5ddb`.

## Open

- **The coder's book lane, live.** Proven by tests on a real repository only. Its live proof waits
  for a real client story.
