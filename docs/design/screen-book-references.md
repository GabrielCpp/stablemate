# A screen book asks the backend's book for what it shows

Status: design, not built. This is slice 7 of [service-boundary.md](service-boundary.md),
for Python screen books only.

Order disclosure. The author read the existing system before writing sections 1 to 4, because
the request named the reading order: the service-boundary note, the `ostler-book` skill and its
references on neighbours and screens, the tool's code for slices 1 to 3, the fixture books, and
the client's web and api books. Every part and concept below was checked against the question
"would I have named this without having seen the tool". The design decisions that reading
carried are listed as claims in section 1b.

## 1. Problem

A team writes the book of a web or phone app that shows records a backend stores. The
backend already has a book. Today the screen book restates the backend's records, and it seeds
its world with backstage code of its own: SQL and API calls that say again how the backend
makes a record and how it mints an account.

Three people feel it.

- The person who writes or pays for a screen book. The client web app's book restates backend
  records in about a quarter of its lines (measured 2026-11-16). Its seeding sits in 29 call
  sites across 6 files and a 74-line backstage that mints accounts by SQL and auth calls.
- The person who changes the backend. When the backend changes how a record comes to be, the
  screen book's seeding goes on making records the old way. Nothing names the screen book.
- The person who reads a red screen run. A seeding script that no longer matches the backend
  fails inside the screen book, and the screen's team gets a report about the backend.

Done looks like this:

- A screen book written by the workflow holds no code that makes, changes, wipes or mints
  anything the backend stores. Each state it needs comes by name from the backend's book, for
  a named person, and the page is signed in as that person.
- A change to how the backend's book reaches a state, that keeps the state's name, the fields
  the screen reads and the person, leaves the screen book untouched and green.
- The checker names a screen book that keeps the backend's lifecycle, rules or actions for a
  record its screens never write, and an act outside its screens that makes such a record. The
  finding names the record and the owner's book.

Out of scope:

- A screen's own writes of a backend record. An interaction that creates or edits a record
  through a form keeps its action in the screen book. The operator scoped this out on
  2026-11-16. A later slice may make such an interaction reach the owner's call.
- Markdown screen books. They hold no model to refer to.
- States of the backend service as a whole that are not a record: its clock and its store
  being down. The screen book keeps performing them as world events.
- Migrating the client's web book. Section 8 puts it to the operator.
- A phone surface. The format change applies to it, and no slice proves it (A10).

## 1b. Claims

1. A needed state is a scene of the owner's lifecycle. The owner's book reaches it on a fresh
   record and hands the neighbour the id the owner's app issued. Source: service-boundary
   section 4, `neighbours.md`.
2. The read set lists the fields of the owner's answers the neighbour reads, and `check` fails
   a field no answer has. Source: `neighbours.md`.
3. A screen book keeps its own model of what its user sees. Source: service-boundary
   assumption 1, and the trespass check that skips screen books.
4. A copy is found by a record name two books share. It blocks only once the book refers to a
   foreign record. Source: the trespass check of slice 3.
5. An outcome that counts an account's whole history needs a `fresh=` actor, who gets a new
   account per cell. Source: the `ostler-book` skill.
6. A screen that asks a backend through its book asks as the person taking the step. Source:
   `screens.md`, on `asked`.
7. A neighbour's environment lists the owner's hosts and secrets beside its own. Source:
   `neighbours.md`.
8. The backstage arranges and never tears down. Source: the `ostler-book` skill.
9. Slice 7 covers four things: a need with its person, the read set, replacing the seeding
   scripts, and a check for a copied move table of a record the screen does not write. Source:
   the operator, 2026-11-16.

## 2. Parts and concepts

### Level 1: parts

1. **The shown record.** Which record of which owner a screen shows, and which of its fields
   the screen reads. It never knows how the owner stores or moves the record.
2. **The need.** Where a situation starts: a record in a named state that belongs to a named
   person. It never knows the steps that reach the state.
3. **The owner's arrangement.** The owner's book makes the record in that state, as that
   person, against the owner's own service, and holds the person's account. It never knows
   which screen asked.
4. **The hand-over.** What the screen receives once the owner is done: the record's id, the
   fields it reads, the day the owner left the world at, and a page signed in as the person.
   It never knows how the record was made.
5. **The copy check.** Reads every book under one root and names a screen book that keeps the
   life of a record its screens never write, or makes such a record outside its screens. It
   never plays anything.

Flow. A writer names each shown record and each need. Before any play, the copy check reads
the books and names copies and broken names. At play, each need goes to the owner's
arrangement, which plays the owner's own steps on the owner's service and model. The hand-over
then puts the read fields into the screen's model, moves the screen's day to the owner's, signs
the page in as the person and opens it again. The screen's own steps follow and are judged as
today. In the seed walk, with no app, the arrangement plays on the owner's model alone and the
hand-over is the same.

In plain words: the screen book says "I need an overdue todo of Ana, and I show its title and
due day". The todo service's book makes one. The screen signs in as Ana and checks its page.

### Level 2: concepts

**The shown record**

| Concept | Owns | Never knows |
|---|---|---|
| Reference | The owner's book and the record it names | How the record is stored |
| Read set | The fields of the owner's view of the record the screen reads | Fields the screen does not read |

**The need**

| Concept | Owns | Never knows |
|---|---|---|
| Needed state | A scene of the owner's lifecycle, by name | The steps that reach it |
| Person | The owner's cast member the state belongs to and the page plays as | How the account is made |

Reference and person are shared value types. The owner's book defines both, and the screen
book names them.

**The owner's arrangement**

| Concept | Owns | Never knows |
|---|---|---|
| Scene choice | The owner's scene of that name that leaves such a record in the state with the person among its actors | Why the screen needs it |
| Arrangement | Playing that scene against the owner's service and model, and picking the one record it left | The screen |
| Account | What a person types to sign in, as the owner's service holds it now | The screen's sign-in form |

**The hand-over**

| Concept | Owns | Never knows |
|---|---|---|
| View | The read-set fields of the arranged record, as the owner's book shows that record | Fields outside the read set (revised, see section 5) |
| Taking in | How the screen's model holds a view, written by the screen book in its own terms | The owner's model |
| Day | The screen model's day after an arrangement, taken from the owner | How the owner moves its clock |
| Entry | The page signed in as the situation's person and opened again after an arrangement | How the account was minted |

**The copy check**

| Concept | Owns | Never knows |
|---|---|---|
| Shown-only copy | A record a screen book holds that a backend book under the root stores, and that no screen of the screen book writes | How the owner moves it |
| Hand seeding | An act outside the screens that makes a record in the screen's model | What the act does on the app |
| Broken need | A needed state, read field or person the owner's book no longer has | How to repair it |
| Adoption | Whether the screen book refers to any foreign record yet, which decides whether a copy blocks | The copy itself |

## 3. Invariants

1. A screen book holds a lifecycle, a rule or an action only for a record one of its own
   screens writes. Owner: the copy check (shown-only copy).
2. A screen book makes no record outside its screens when a backend book under the root
   stores that record. A state it needs comes from the owner's book. Owner: the copy check
   (hand seeding).
3. Every needed state, read field and person resolves in the owner's book. Owner: the copy
   check (broken need).
4. The person a need names takes part in the scene that makes the record. Owner: scene
   choice, which fails the need and names the scene's actors.
5. The screen's model sees only the read set of a needed record. Owner: the view, which hands
   exactly those fields and fails a read of any other.
6. After an arrangement, the screen model's day is the owner's day. Owner: the day.
7. A change in how the owner reaches a state that keeps its name, the read fields and the
   person needs no edit in a screen book. Owner: the reference and the needed state, which hold
   names only.

## 4. Forces and patterns

Forces:

- F1. The backend changes how it makes a record more often than what it calls the record, its
  states and its fields.
- F2. A page shows what its signed-in person may see. A state is useful to a screen only when
  it belongs to the person the page plays as.
- F3. A shared environment is never wiped. A screen counts on no empty list and on no state it
  did not ask for.
- F4. A screen writes some backend records itself through its forms, and keeps their model
  (operator's scope).
- F5. The seed walk runs with no app and must reach the same states as a play.
- F6. A screen's writer reads no source outside the screen app. The backend's book is its only
  view of the backend.
- F7. The owner's arrangement can move a clock the screen shares.
- F8. A copied record usually keeps the owner's name. A record made outside the screens is a
  copy whatever its name.

Between parts:

- **Reference by name, resolved late** (F1, F6). Claims 1 and 2, kept. The screen book names
  the owner's record, scene and cast member. The names resolve at check time and at play.
- **The owner's book as the only maker of its records and accounts** (F1, F2, F3). Claim 1,
  kept, and widened to the account. The person is the owner's cast member, and the owner's
  service holds the account a page signs in with. Claim 6 already makes the step's person the
  owner's actor. Claim 5 is kept: a fresh person gets a new account from the owner.
- **One hand-over for play and walk** (F5). The view, the day and the taking-in read the
  owner's model after the arrangement in both modes. Only the entry needs an app.

Inside the parts:

- Scene choice is a filter over the owner's scenes (F2). A plain function.
- Taking in is a function the screen book writes (F4). The screen keeps its own record type
  for what its forms also write, so a needed record must enter that same type.
- Entry is two hooks the screen's surface writes: sign in as an account, and open (F2). The
  tool calls them and never knows the form.
- The copy check is one pass with two signals (F8): a shared record name, and an act outside
  the screens that makes a record. Claim 4 is kept and widened to screen books. Claim 3 is
  narrowed: a screen book keeps its own model only for records its screens write.

Claims 7 and 8 are kept. Claim 8 removes the fixture web book's wipe of the backend's store,
in slice 2. Claim 9 is the scope.

Open lookups, resolved in section 5:

- L1. Can a screen book's scene start from a need, in the seed walk and in the cells?
- L2. Does the owner's service hold anything a person types to sign in?
- L3. Does the check read screen books for copies?
- L4. Does the fixture have a person a page signs in as?
- L5. Where can the view come from, so that it is what the owner's service holds?

SOLID check. Each Owns reads without "and". A new owner needs no change in the tool. A new
sign-in method is a new surface hook body, not a tool change. Scene choice depends on the
owner's book alone. The screen's surface declares only sign-in and open.

## 5. Mapping onto the existing system

Revision log:

- Section 2, view: its source is the owner's model of the arranged record, not a fresh read of
  the owner's service. L5 found that the arrangement judges every owner step against the
  owner's app (`owners.py` 126 to 131 play each step through `attempt` on the owner's
  surface). A record that arrived means the owner's app agreed with the owner's model on the
  way. A second read would cost a call and a second declaration for no new fact (A1).
- Section 2, scene choice: added. The arrangement today picks the first matrix whose scene has
  the name (`owners.py` 111 to 147). Once the owner offers one state name for two actors, as
  the fixture api will after slice 2, the person must decide.

| Item | Verdict | Where, and the mismatch |
|---|---|---|
| The shown record | Reshape | `Foreign` in `boundary.py` 24 to 39. No screen book holds one today. |
| Reference | Exists | `Foreign.record`, `Foreign.owner`. |
| Read set | Reshape | `Foreign.reads` is checked only against calls a book passes on (`check.py` 444 to 448). A screen passes nothing on, so its reads go unchecked. |
| The need | Reshape | `Needs` in `boundary.py` 42 to 75. Journey givens only (`journey.py` 207). No person. |
| Needed state | Reshape | `check.py` 455 to 463 checks the state of a journey's need, never a scene's. |
| Person | New | A step carries `by` (`screen.py` 389 to 391), and `asked` sends as it (`runner.py` 327 to 340). A need names none. |
| The owner's arrangement | Exists | `Owners.arrange`, `owners.py` 107 to 132. |
| Scene choice (revised) | Reshape | `Owners.matrix_of`, `owners.py` 134 to 147, ignores the actor. |
| Arrangement | Reshape | Cells never reset the owners: `cells.py` 99 to 113 plays scene steps through `attempt`, and only `walk` calls `Owners.journey` (`runner.py` 54). |
| Account | New | The HTTP surface holds tokens per actor (`http.py` 734 to 757). The fixture api holds one fixed token. The client api's `Account` holds an email and a token, while its minting builds a password it drops (`backstage_local.py` 192 to 229). |
| View (revised) | Reshape | `Needs.record` hands the owner's whole entity (`boundary.py` 70 to 72). Nothing limits it to the read set. |
| Taking in | New | A screen model cannot hold a handed record. |
| Day | New | |
| Entry | New | `PageSurface` asks a book for `restore`, `open`, `perform` and `rows`. Signing in is each book's own code (client `surface.py` 118 to 141). |
| The copy check | Reshape | `trespass_faults` returns nothing for a screen book (`check.py` 467 to 477). |
| Shown-only copy | Reshape | The name match of `held_records` and `trespass_faults` (`check.py` 415 to 498), with no exemption for a record a screen writes. |
| Hand seeding | New | |
| Broken need | Reshape | As needed state and read set above, plus the person against the owner's `Service.cast` (`service.py` 44). |
| Adoption | Exists | `told=record not in foreign` and `told=not stated`, `check.py` 488 and 497. |

The seed walk (L1): `Scene.arrange` applies each step to the model (`state.py` 26 to 29). A
need is no action, so a scene that starts from one cannot be arranged. Reshape: a need in a
scene arranges the owner's model and hands over, as at play.

The writer's side. The skill's `screens.md` says nothing of a backend's record. Its
`neighbours.md` speaks of endpoints. The workflow prompt's references block
(`write-python-book.md` 22 to 36) already sends every writer, a screen writer included, to the
owner's book and forbids reading the owner's source (A6).

What the system has that the design lacks:

- `asked` feeds (`screens.md` 147 to 157). A concept the design reuses: the step's person is
  already the owner's actor. Not waste.
- `Passes`, `Reaches` and `OwnerRefused`. The write path for screens is out of scope. Not
  waste.
- The fixture web book's `backend.py` hooks for the clock and the store. World events, kept.
  Its `reset` wipes the backend's store on every restore, which breaks claim 8. Waste, removed
  in slice 2.
- The fixture web book's `SetStore` names `app.py`, the api's source (`interactions.py` 54 to
  57). This breaks invariant 6 of service-boundary. Recorded, left for the world-event work.
- The kit book imports the web book's record, rules and backend (`kit/model.py` 9 to 11,
  `kit/surface.py` 11). A copy of a copy. Out of scope, and a receiver in 5b.

The lookups:

- L1. Cells accept a need as a scene step, since `attempt` routes it to the arrangement
  (`runner.py` 160 to 161). The seed walk does not. Both need the owners reset per situation.
- L2. No. Section 2's account is new on both the tool and the owner books.
- L3. No, `check.py` 467 to 477.
- L4. No. The fixture web app sends a fixed bearer token (`web/app.js` 39 to 41). Slice 2
  gives the fixture persons (A3).
- L5. The owner's model after the arrangement, as logged above.

Claims against the system: claims 1, 2, 5, 6, 7 and 8 are followed by both. Claim 3 is what
the system does, and the design narrows it. Claim 4 is followed by both, and the design widens
it to screen books. The fixture web book breaks claim 8 today.

## 5b. What must not move

Measured on 2026-11-16 at `e755b492c`, on the fixture with each book's own stack.

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| A user of the fixture web app | Journeys and cells that play the app end to end | The web book's run | 8 journeys pass, 41 cells on 23 arrangements, 8 impossible, 10 inputs, 0 fail | 0 fail, 8 journeys, at least 41 cells |
| The person waiting on the web book | A run time | Nothing | 60 s: journeys 17.5 s, cells 24.3 s, inputs 17.9 s | At most 90 s (A8) |
| The owner's book, the fixture api | Its own plays | The api book's run | 5 journeys, 38 cells, 49 inputs (5 diverge as declared), 0 fail | 0 fail; counts grow only by the person's new cells |
| The kit book | Its plays, on the web book's copied model | The kit book's run | 4 journeys, 3 inputs, 0 fail | The same |
| The digest book | Its plays through the api book | The digest book's run | 3 journeys, 0 fail | The same |
| Every fixture book | A clean check | `ostler book check` | 0 findings on api, web, kit and digest | 0 findings |
| The client web book | A clean check | `ostler book check` | 0 findings, 5 notes | 0 findings; notes may add the copies the check names |
| The web book's reader | Findings on typed inputs | The web book's run | 10 input classes played, 0 fail | At least 10 played |
| A world event a screen performs | The network dropping, the store going down | The web book's run | `OfflineShowsTheLastList` passes; the Offline and StoreDown cells pass | Unchanged |
| The person paying for a screen first book | A price | Nothing | Kit: $1.26, 6 minutes. Web: not measured (A2) | Each proof run at most $6 and 30 minutes |
| The tool's tests | Green tests for web, kit and the boundary check | pytest | 150 passed, 0 failed, in 4.5 minutes | 0 fail |

The row for the client web book has a check behind it once slice 3 lands. Until then a copy in
it is a note, by adoption, so the client's book keeps passing while it is not migrated.

## 6. Slices

Each slice ends with the tool built, the `ostler-book` skill updated in the library and
installed, and a writer run that proves it with nothing done by hand. The writer run is the
okf-book `python_book` workflow on a copy of the fixture: `app.py`, `web/`, `digest/`, the api
and digest books, and no `services/web` or `services/kit` (A7). It writes the web book from the
web app's source with the api book under the root. Prices come from the record: service-boundary
slices 1 to 4 landed in 3.4 hours from design to skill, about 50 minutes each. The kit's
`python_book` run cost $1.26 and 6 minutes on 2026-11-16, and the web book is about four times
its size (A2).

1. **A screen needs a todo the owner makes overdue.** Parts: the shown record, the need without
   a person, the arrangement, the view, taking in, day, entry (open again). The tool lets a
   need be a scene step and a journey given in a screen book, resets the owners per cell,
   arranges a need in the seed walk, hands the read set of the owner's model of the record,
   moves the screen's day to the owner's, and opens the page again. The check fails a read
   field the owner's view of the record lacks and a scene's need of a state the owner lacks.
   The fixture web book's overdue scene and `TheDayPasses` start from
   `Needs(TODO, "overdue")`. `screens.md` gains a section on a record a backend's book stores.
   Done when: the web book plays green with the overdue state from a need; changing the api
   book's overdue scene to move the clock five days instead of three leaves the web book
   unedited and green; a read field the api lacks fails `check`; the writer run ends green
   with its overdue scene and journey starting from a need and no step that moves the clock to
   reach overdue; every row of 5b is measured again. Price: 1.5 worker hours, one proof run of
   about $5.
2. **Ana's todo, signed in as Ana.** Parts: person, scene choice, account, entry. The fixture
   app gains persons: an admin hook mints one with a password, a person signs in for a token,
   a todo a person makes is theirs, and a person lists and reaches only their own. The test
   token and the API key keep today's behaviour. The web app signs a person in first. The api
   book gains a fresh person in its cast, a surface that mints them and offers their account,
   scenes of a person's own todo, and the rule that another's todo is not found. The tool adds
   the person to a need, chooses the owner's scene by person, fails a need whose scene the
   person takes no part in, asks the owner's surface for the account, and signs the page in
   through the screen surface's hook before a step whose person differs. A journey whose needs
   name one person plays its steps as that person. The web book's restore stops wiping the
   api's store. `screens.md` and `neighbours.md` say how a screen names the person and writes
   its sign-in. Done when: the web book plays green signed in as a fresh person per journey; a
   need naming a person its scene does not use turns the run red with the scene's actors in
   the note; the writer run ends green, its needs name the person, and its book holds no code
   that mints a person, makes a todo or wipes the store; every row of 5b is measured again.
   Price: 3 worker hours, one proof run of about $5.
3. **The check names a copied move table.** Parts: the copy check. The check reads screen
   books. It names a shown-only copy and a hand seeding act, and each blocks once the book
   refers to a foreign record. `findings.md` and `screens.md` say what the check names and the
   fix. Done when: a test copy of the web book with an act outside its screens that makes an
   overdue todo is named, with the record and the owner's book; the same copy with no foreign
   reference gets a note and passes; the client web book's check stays at 0 findings and names
   its seeded lines in a note; the writer run ends green with the check among its gates; every
   row of 5b is measured again. Price: 1 worker hour, one proof run of about $5.

Total: 5.5 worker hours and about $15 in proof runs, with a ceiling of $18.

## 7. Assumptions

1. **An arrangement that passed means the owner's app holds what the owner's model says of
   that record.** Decided: the view reads the owner's model after the arrangement, in play and
   in the walk. Basis: each owner step plays through `attempt` on the owner's surface, which
   judges its answer and rows against the owner's model (`owners.py` 126 to 131, `runner.py`
   74 to 105). If wrong: section 2's view reads the owner's service, the reference names the
   owner's read call, slice 1 grows by an hour.
2. **A web `python_book` first book costs about four times the kit's: $5 and 25 minutes.**
   Decided: each proof run is priced at $5 with a $6 ceiling. Basis: the kit run cost $1.26
   and 6 minutes; the web book is 1,407 lines against the kit's 355; the web app's source is
   344 lines of script against the kit's 71 lines of pages. If wrong: the price of every slice
   and the price row of 5b.
3. **Giving the fixture persons is the cheapest honest proof of the person.** Decided: slice 2
   changes the fixture app, the web app and the api book. Basis: the web app signs nobody in
   (`web/app.js` 39 to 41). The test token keeps today's behaviour, so the other books and
   tests keep theirs. If wrong: slice 2's fixture work, and the api, kit and digest rows.
4. **A screen keeps its model for the records its forms write.** Decided: the fixture web book
   keeps its todo record, rules and add, edit and remove. Basis: the operator's scope, "a
   record it does not write". If wrong: a slice for an interaction that reaches the owner's
   call.
5. **A copy usually keeps the owner's record name.** Decided: the copy check matches by name,
   and names any record made outside the screens whatever its name. Basis: the fixture web
   book's record shares the api's name; 3 of 8 restated records in the client web book share
   the api's names, and 2 of those 3 are written by a screen. If wrong: the check misses copies
   it cannot name, and slice 3 needs a field-shape match.
6. **The writer prompt needs no change.** Decided: slices change the skill only. Basis: the
   prompt's references block already sends every writer to the owner's book, and service-boundary
   slice 4 proved it for a neighbour. If wrong: one sentence for screen books in the prompt,
   in slice 1.
7. **The proof runs on a fixture copy with no web or kit book, in the harness of the 2026-11-16
   kit run.** Basis: the kit book imports the web book's modules, so it cannot load without
   them. If wrong: the copy keeps the kit book, and its check notes the missing web book.
8. **Arranging a need and opening the page again costs about a second.** Basis: the api book
   plays all its journeys and cells in 0.4 s; a page open in the web run takes about 0.5 s. If
   wrong: the run time row of 5b.
9. **A standing person's older records do not break a screen journey.** Basis: a journey
   compares the rows against those shown at its start (`runner.py` 270 to 285). If wrong for
   cells: the person a screen needs is a `fresh=` member of the owner's cast.
10. **A phone surface takes the same hooks.** Basis: none; no slice plays a phone. If wrong:
    the entry hooks for the phone surface in a later slice.
11. **The owner's clock is the screen's day.** Basis: the fixture web surface reads its day
    from the api's clock. If wrong: the day concept, for a screen with a clock of its own.
12. **The client api can offer a password with its accounts.** Basis: its minting builds one
    and drops it (`backstage_local.py` 197). If wrong: the client's migration needs a sign-in
    by token, a second body of the same sign-in hook.

## 8. For the operator

1. **Should the client web book be migrated by a writer run after slice 3?** The fixture
   proves the format. Only the client's book shows whether the quarter of restated lines and
   the 29 seeding sites go. The record holds no run of the client's web book, so the price is
   unknown. Recommendation: yes, as its own attended run after slice 3 lands, under a ceiling
   you set, judged by the seeding sites left and the lines of restated records.
