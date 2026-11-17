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

## 2026-11-16: python_book writes the client web app's book from nothing, from a worktree

- **Run:** okf-book `python_book`, groom run `w3-web-scratch`, in a client worktree with the web
  book's package deleted except its stack. The result was compared with the book on client
  master and not merged.
- **Stablemate:** launched at `192ee2d04` (runner later moved to `0b1aa3f1c` and `5b24826cd`;
  prompts read at each turn).
- **Proved:** a first screen book of the client web app reached the same gates as the book on
  master with nothing in the book written by hand: `check: 0 findings, 8 notes` on both, `missing`
  0 of 561 files on both, a whole play of 31 pass, 5 known defects, 0 fail, stamped, marked and
  committed by the run. It holds 81 interactions and 36 journeys against master's 34 and 34, and
  found 7 app defects, 1 of them also on master's list and 6 new.
- **Not proved:** that it costs less than the earlier first web book. It cost more: $61.82 against
  $33.82, in one owner turn of 445 minutes that handed the book to six subagent writers in a row.
  Those writers held 87 percent of the cache writes and slept 215 minutes on plays. The prompt
  now has the owner write the book itself (`0b1aa3f1c`); not re-proven by a run.
- **Gates' last lines:** `31 pass, 5 known defects, 0 fail`, 64 input classes with 5 declared
  diverging, 12 twin pairs played.
- **Cost:** $61.82. Wall 7 hours 41 minutes. Copy up in 48 seconds and 41 seconds on the resume;
  no image built inside the run.
- **By hand:** (1) the finished owner wrote its app defects into `blocked`, which parks the run;
  the attendant stopped it, rewound it to its check and resumed it on a new copy (cause fixed in
  `5b24826cd`). (2) The commit was refused by the clone check and the run's fix turn waived nine
  clones in the check's configuration outside the commit; the waiver was not kept (cause fixed in
  `c4f61d892`).
- **Evidence:** groom `w3-web-scratch`; client branch `book/web-scratch` at `93a1354db`; the
  comparison report in the goal record.

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
- **By hand:** after landing, the book failed the repository's lint: 8 unused imports and one
  untyped lookup. The workflow's commit ran none of the repository's declared checks. Fixed at
  the cause: a book commit now runs the declared commit checks and a refusal goes to the fix turn
  (`24b900511`), and the declared Python check runs ruff, ty and basedpyright on staged files
  (`1471dc4ab`). The 9 lines were then fixed by an agent (`92b465f28`, `41a9bd3dd`), and the
  book still checks clean and plays green.
- **Evidence:** groom `w3-farrier`; stablemate commit `8c19b5ddb`.

## 2026-11-17: python_book completes the client's largest service book

- **Run:** okf-book `python_book`, groom run `w3-api-complete`, on the client's api book (an HTTP
  service of 731 source files), resumed from the half-written book the wave's first attempt left.
- **Stablemate:** resumed at `0b1aa3f1c`; the runner stayed at `f9fe5b740` to the end.
- **Proved:** under the prompt that has the owner write the book itself, one owner finished the
  book with no subagent writer: check clean, whole play green, `missing` empty, stamped, marked
  and committed by the run. Played from a worktree on its own stack copy, which the run tore down.
- **Not proved:** that a book of this size is cheap. One line of the play's witness report was
  1.5 MB, because the book unrolled a recursive tree four levels deep, and it nearly doubled the
  owner's context. The hand-off to the owner is now cut in width (`f49b332db`) and the report's
  list is bounded (`b6b5ea472`); neither is re-proven by a run. The format has no recursive shape.
- **Gates' last lines:** `check: 0 findings, 5 notes`; `0 of 731 files are in no element and under
  no ignore pattern`; `nothing stale` read on client master after landing.
- **Cost:** $13.20 billed by groom, about $24.80 at list price. Wall 6 hours 47 minutes.
- **By hand:** (1) the run's fix turn for a refused commit reshaped seven endpoints, and the flow
  committed with no replay. The attendant replayed those seven on a fresh copy: 7 pass, 0 fail.
  (2) The attendant rebased the run's commit onto client master and landed it by fast-forward.
- **Evidence:** groom `w3-api-complete`; client commit `f5d3e6d5c`.

## 2026-11-17: python_book writes two command-line books from nothing

- **Run:** okf-book `python_book`, groom runs `w3-paddock` and `w3-saddlebag`, on stablemate's own
  paddock and saddlebag packages, each from a stablemate worktree with no book.
- **Stablemate:** launched at `f9fe5b740`; released on `52966c3cd`.
- **Proved:** each writer wrote a first command-line book that reached check clean, a green whole
  play, `missing` empty and a stamp, in one owner lap, with no stack.
- **Not proved:** that a first command-line book commits on its own. Both commits were refused by
  the clone check and both runs parked on the operator. The books copied the watched file row and
  its two helpers from the farrier book, because the tool had no type for that row. One fix turn
  made the paddock book import the farrier book's model, which the prompt's wording invited.
  ostler now ships the row as `Watched` (`ab62dcc03`), the skill teaches it (`9e2aef010`) and the
  fix turn's prompt forbids the import (`0b9c4a9d5`); none is re-proven by a run.
- **Also seen:** the saddlebag owner turn took 139 minutes, about 100 of them in plays, because a
  first book's writer played every element and the flow then played the whole book again. The
  prompt now says to play nothing twice (`0b9c4a9d5`); not re-proven.
- **Gates' last lines:** paddock `8 pass, 0 known defects, 0 fail`, `cells: 54 played`; saddlebag
  `7 pass, 0 known defects, 0 fail`, `cells: 480 played`; both `nothing missing` and `nothing
  stale` on main after landing, and `make lint` clean.
- **Cost:** paddock $4.67 billed over four Sonnet turns, 35 minutes to the gate. Saddlebag $6.81
  over two turns, 2 hours 44 minutes to the gate. Each then waited about 10 hours on the operator.
- **By hand:** an agent moved each book's file row onto `Watched`, gave the paddock book its own
  state row, folded two repeated fixture blocks in the saddlebag book and restated one copied
  function there as a named table. The attendant replayed each book green, rewrote each stamp at
  the played commit and answered each gate. Each run then made its own commit.
- **Evidence:** groom `w3-paddock`, `w3-saddlebag`; stablemate commits `126479b77`, `926dfc755`.

## Open

- **The coder's book lane, live.** Proven by tests on a real repository only. Its live proof waits
  for a real client story. Its worktree path reaches the copy through the same `copy_for` as the
  runs above, read from the code, not from a run.
- **A writer declaring an event the service's clock causes.** Run `td-sla-2` ($8.11) wrote a green
  book without the breach events; the skill was widened after it, not re-proven.
- **A phone list read through the recording proxy by a writer.** The tool is built and the app's
  plain HTTP target was confirmed on the phone reference app; no writer run yet.
- **Books for groom, ostler, workflows and workhorse.** Not run yet.
- **A first command-line book that commits with nothing by hand.** The two above did not.
