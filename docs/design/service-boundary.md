# A book stops at its service's boundary

Status: design, not built. Sections 1 to 4 were written from the problem and from two runs'
records. The author had already seen the tool, so every part and concept below was checked
against the question "would I have named this without having seen the tool".

## 1. Problem

A team owns one service among many that call each other and hear each other's events. They
write a book for their service. Today that book restates what the neighbours do: the states
of the neighbours' records, the rules the neighbours refuse by, and the calls that drive the
neighbours from one state to the next.

Three people feel it.

- The person who pays for a first book. On the work-shaped fixture, the book of a gateway in
  front of nine services cost 2.8 times a book of a single backend service. Its writer read
  the source of seven other services before writing a line. A service with more neighbours
  costs more, with no ceiling.
- The person who changes a service. When the ticket service changes how a ticket is
  resolved, every book that restated that life is wrong. Nothing marks those books out of
  date, because each one points only into its own service's code.
- The person who reads a red run. A gateway's run fails on a ticket rule. The defect may sit
  in the ticket service, and the gateway's team is the one that gets the report.

Done looks like this:

- A book of a service with many neighbours costs at most 1.5 times a book of a service with
  none, on the same fixture.
- A change inside one service edits one book. A neighbour's book is named by the checker
  only when something it refers to by name was removed or changed shape, and the finding
  says which name.
- A book says nothing it cannot trace to its own service's code or to a name in a
  neighbour's book.

Out of scope:

- Proving that two services agree on a wire format beyond the fields a book reads.
- Replacing a neighbour with a fake. A shared environment gives no control over what is
  deployed.
- How the owner's book is written. This note covers what a neighbour may ask of it.
- Concurrency and delivery order between services.

## 1b. Claims

Design decisions that reached this note from the current format, each to re-derive or reject:

1. A state another service makes is an "outside event" the book declares, and the book's
   own surface performs it by the other service's call. Source: the book skill.
2. Every state that changes what a call answers must be reachable in the book's model.
   Source: the book skill.
3. An event a service hears is declared in the emitter's book, or by the listener when the
   emitter has no book. Source: the service-events design.
4. A value a page shows is judged against the answer the page was given, not against a
   whole restated list. Source: the screen-lists design.

## 2. Parts and concepts

### Level 1: parts

1. **Ownership.** Says which service a record belongs to. It owns the line between what a
   book models and what it only refers to. It never knows how any record behaves.
2. **The owner's offer.** What a service's book puts at its neighbours' disposal: the names
   of its records, the shapes its calls answer with, and named ways to get one of its
   records into a named state. It never knows who asks.
3. **The neighbour's reference.** How a book speaks of a record it does not own: which
   record, which fields it reads, which named state it needs. It never knows how the owner
   gets there.
4. **The boundary claim.** What a service does with a neighbour's record: what it passes
   on, renames, hides, joins, and how it answers when the neighbour refuses. It never knows
   why the neighbour answered as it did.
5. **The cross-book check.** Reads every book under a root and names a reference that no
   longer resolves, and a book that models what it does not own. It never plays anything.
6. **The order of a backfill.** Decides which book is written first so that an owner's
   offer exists before a neighbour refers to it. It never knows what a book contains.

Flow. Ownership sorts each record of a service into owned and foreign. For an owned record
the book models its life as today, and that model is also the owner's offer. For a foreign
record the book writes a reference. At play time the reference is resolved through the
owner's offer: the owner's book makes the record, the neighbour's book plays its own call on
it, and the boundary claim is judged against what the owner answers about the same record.
The cross-book check runs before any play. The backfill order runs before any writing.

Two code bases could both fit this split. It holds for calls and for events alike.

### Level 2: concepts

**Ownership**

| Concept | Owns | Never knows |
|---|---|---|
| Owned record | A record the service itself stores and changes | Any other service's records |
| Foreign record | A record the service only receives from, or sends to, its owner | The record's life |
| World record | Something no service owns that happens to this one: a mail arriving, a feed, a person acting (revised, see section 5) | Any service's records |

**The owner's offer**

| Concept | Owns | Never knows |
|---|---|---|
| Answer shape | The fields a call of the owner answers with | Which neighbour reads which field |
| Offered state | A name for a state of an owned record that the owner's book can reach on request | Why a neighbour needs it |
| Emitted event | The contract of an event the owner emits (already designed) | Who hears it |

**The neighbour's reference**

| Concept | Owns | Never knows |
|---|---|---|
| Reference | The owner's book and the record it names | How the record is stored |
| Read set | The fields of the owner's answer this service reads | Fields it does not read |
| Needed state | The offered state a situation starts from, by name | The steps that reach it |

**The boundary claim**

| Concept | Owns | Never knows |
|---|---|---|
| Passing on | How this service's answer derives from the owner's answer | Whether the owner's answer is right |
| Narrowing | Who this service lets ask, beyond what the owner allows | The owner's own permission rules |
| Refusal map | How each class of the owner's refusal comes back from this service | The rule behind the refusal |
| Reach | That a call of this service arrives at a named call of the owner | The effect of that call |

**The cross-book check**

| Concept | Owns | Never knows |
|---|---|---|
| Broken reference | A reference, read field or needed state that the owner's book no longer has | How to repair it |
| Trespass | A book that gives a life, a rule or a driving action to a record it does not own | The owner's life for it |
| Open reference | A reference whose owner has no book yet | When that book will exist |

**The order of a backfill**

| Concept | Owns | Never knows |
|---|---|---|
| Dependency list | Which services each service calls or hears, read from code | What the calls do |
| Writing order | Owners before neighbours, and a second pass for a cycle | The content of a book |

## 3. Invariants

1. A book holds a life, a rule or an action only for a record its service owns. Owner: the
   cross-book check (trespass).
2. Every reference, read field and needed state resolves in the owner's book, or is marked
   open. Owner: the cross-book check (broken reference).
3. A boundary claim is judged against what the owner answers at play time, never against a
   copy of the owner's model. Owner: the boundary claim (passing on).
4. A neighbour's situation that starts from a foreign state is set up by the owner's book.
   Owner: the neighbour's reference (needed state).
5. A change inside the owner that keeps its names and shapes needs no edit in any
   neighbour. Owner: the owner's offer.
6. Every source pointer of a book points into its own service. Owner: ownership. A fact
   about a neighbour is a reference, not a pointer into the neighbour's code.

## 4. Forces and patterns

Forces:

- F1. The number of neighbours varies from zero to dozens, and a book's cost must not grow
  with it.
- F2. An owner changes its inner behaviour more often than its names and shapes.
- F3. A shared environment holds other people's records and is never wiped, so no book can
  count on finding a record in a given state.
- F4. Books are written over months. An owner's book may not exist when a neighbour's book
  is written.
- F5. A service decides little about a foreign record, and what it decides is the same for
  every state of that record except the few it branches on.
- F6. A refusal changes nothing, so asking the owner the same question twice is safe. A
  success may change the record, so it cannot be asked twice.

Between parts:

- **Reference by name, resolved late** (F1, F2, F4). A neighbour names the owner's record,
  fields and offered states. The names are resolved when the book is checked and when it is
  played. This is the pattern the event design already uses for an event a service hears.
- **The owner's book as the only maker of its records** (F3, F5). A needed state is reached
  by playing the owner's own book up to that state on a fresh record. The neighbour's book
  gets the record's id.

Inside the boundary claim:

- **Derivation from the owner's answer** (F5, claim 4 re-derived). After this service
  answers, the runtime asks the owner about the same record through the owner's book and
  applies the stated derivation. A plain function, the same shape as a list derived from
  fetched data.
- **One situation per class the service tells apart** (F5, F1). A book plays a forwarded
  call once per outcome its own code distinguishes: passed on, refused by the owner per
  refusal class, not found, not allowed by its own narrowing. It does not replay the
  owner's matrix.
- **Ask twice for a refusal, read back for a success** (F6). A refusal is judged by asking
  the owner the same question and mapping the answer. A success is judged by reading the
  record back from the owner and seeing that the named call arrived.

Claims:

- Claim 1 is narrowed (revised, see section 5). It holds for a world record, which no book
  owns. For a record a service owns it is rejected: a surface that performs another
  service's call puts the knowledge of how that service is driven inside the wrong book
  (F2). There the owner's book performs it, asked by name.
- Claim 2 is narrowed. It holds for owned records. For a foreign record the states a book
  needs are the offered states it names.
- Claim 3 is kept, and is the event-shaped case of "reference by name, resolved late".
- Claim 4 is kept and widened from a page's list to any answer that passes a neighbour's
  data on.

Open lookups, resolved in section 5:

- L1. What the skill tells a writer to do today about a state another service makes.
- L2. Whether the runtime can load and play a second book during a run.
- L3. How a book learns the address of another service.
- L4. What the cross-book check already compares.

SOLID check: each Owns reads without "and". A new neighbour adds one reference and no
change to the runtime. The boundary claim depends on the owner's offer, never on a given
owner. The owner's offer declares only names, shapes and offered states.

## 5. Mapping onto the existing system

Revision log:

- Section 2, Ownership gains a third concept, the world record. The format already has an
  occurrence no service owns (a mail arriving, a feed, a person acting between commands),
  and it is legitimate. The design had missed it.
- Section 4, claim 1 is narrowed instead of rejected outright: the outside event stays for a
  world record, and leaves for a record a service owns.
- Section 2, the owner's offer: an offered state needs nothing new from the owner's writer.
  The owner's book already arranges each state of its lifecycle to play its own cells.

| Item | Verdict | Where, and the mismatch |
|---|---|---|
| Owned record | Exists | A book's model records. Nothing says a record is owned. |
| Foreign record | New | No record carries an owner. `inputs.py` knows only a foreign id in generated input. |
| World record (revised) | Exists | `Arrange` in `arrange.py`, and `Outside` in `command.py`. |
| Answer shape | Exists | The owner's endpoint shapes. |
| Offered state | Reshape | The runner arranges a state to play a cell of the same book. No other book can ask for it. |
| Emitted event | Exists | `event.py`, `Service(events=...)`. |
| Reference | New | A book reaches another book only by a plain Python import of its endpoints. |
| Read set | Reshape | `Arrange.reads` lists the fields read of an event. A call has no equal. |
| Needed state | New | Today the neighbour's surface performs the owner's calls, `grpc.md` lines 148 to 195. |
| Passing on | Reshape | `Lists(given, derived)` judges a list against the answer a page received. Calls have no equal. |
| Narrowing | Exists | The book's own rules. |
| Refusal map | New | |
| Reach | New | |
| Broken reference | Reshape | `check.py` `event_faults` names a read path the event lacks. Calls and states have no equal. |
| Trespass | New | |
| Open reference | Reshape | `event_faults` names an event nothing under the root emits, without blocking. |
| Dependency list, writing order | New | The workflow writes one book per launch, in the order the operator launches. |

What the system has that the design lacked: `Arrange.carries`, an action of this book's
model that an outside occurrence reduces. For a world record it is right. For a record a
service owns it is the mismatch: it puts the owner's transition inside the neighbour's
model. The gateway book holds 13 of them. The design is right and the format is wrong here.

The lookups:

- L1. The skill says the surface performs the occurrence "by sending the other service's own
  call, imported from that service's book", and that its `carries` is "an action of this
  book's model" (`grpc.md` 154 to 193). The first half already points at the owner's book.
  The second half is what makes a neighbour restate the owner. No sentence tells a writer
  to stop at its own service.
- L2. The runtime loads another book's `service` module to read its events
  (`eventmap.py` 75 to 87). It never plays another book.
- L3. An environment lists hosts by name and a surface asks for one
  (`environment.py` 169 to 188). A call to a host the book does not declare is already said
  to belong to another service's book (`witness.py` 149 to 153).
- L4. The cross-book check compares events only, five findings (`check.py` 255 to 289).

Claims against the system: claim 1 is what the system does, and the design narrows it to
world records. Claim 2 is what the system does, and the design narrows it to owned records.
Claims 3 and 4 are followed by both.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| A customer's path through the phone gateway | Journeys that cross services play end to end | The gateway book's run | 14 journeys, 179 situations, 0 failed | Each journey a customer lives still plays, the other services' steps performed by their books |
| The person paying for a gateway's book | A price | Nothing | $21.83, 98 minutes, 28 commands and 3 helpers on other services' code | At most $11.30, and no read of another service's code |
| The person paying for a backend's book | A price | Nothing | $7.53 on average over eight books | Within 20 percent |
| Defects found on the fixture | Ten findings across nine books | Nothing | user 3, ticket 2, asset 2, notifications 1, SLA 1, gateway 1 | Each still found, by the book of the service whose code holds it |
| Books already written | A clean check | `ostler book check` | 0 findings on every book outside this repository and on the fixture books | 0 blocking findings |
| A screen book's reader | Findings on the app's own inputs: two inputs the form treats alike, a date kept as a moment | The screen book's run | Present in the fixture web book and the client's web book | Unchanged until slice 7 is measured |
| A world record | An outside event the book performs | The format | Used by the command books | Unchanged |

The gateway found one defect, a push token made of spaces. The code that accepts it is the
notifications service's, and its book already asks about it. Under this design the gateway
book no longer finds it. That loss is accepted: one defect, one book.

The second row has no check behind it. It becomes the measure of slice 5.

## 6. Slices

1. **A neighbour refers, the owner arranges.** The fixture gains a small second service
   that calls the todo service and passes its answer on. Its book names the todo as a
   foreign record with the fields it reads, starts a situation from "a done todo" by name,
   and states how its answer derives from the owner's. The runner asks the todo book to
   arrange the state. Done when the new book holds no life, rule or action for a todo and
   plays green, a change to how the todo book completes a todo leaves the new book untouched
   and green, and a planted fault in the passing on turns its run red. Rows 3, 5 and 7 of
   section 5b are measured again.
2. **Refusal and reach.** The same book states how the owner's refusal comes back and that
   its write arrives at the owner's call. Done when a planted wrong status and a planted
   dropped write each turn the run red.
3. **The check.** Broken reference, trespass, open reference, two books owning one record.
   Trespass does not block on a book written before this design. Done when removing a read
   field from the todo book names the neighbour and the field, and row 5 holds.
4. **The writers.** The skill replaces the passage of L1: a writer reads no source outside
   its service, takes a neighbour's facts from that neighbour's book, and writes an open
   reference when there is none. The workflow gives a writer the list of books under the
   root and writes owners first. Done when the skill check passes and a workflow run on the
   fixture's second service makes no read outside its folder.
5. **The measure.** The phone gateway's book is written again on the corrected harness,
   with the nine backend books under its root. Done when rows 1 and 2 hold.
6. **Events.** Delivery of a heard event on the bus, slice 3 of the service-events design,
   is this rule for an event. Done when the audit book makes no call to the ticket service.
7. **Screen books.** A screen book's records are references to the backend's book under the
   same root. Measured first on the two SvelteKit books before anything is changed.

## 7. Assumptions

1. **A screen book may keep its own model of what its user sees while no backend book
   exists.** Decided: slices 1 to 6 leave screen books alone, and the check reports a screen
   book's restated records without blocking. Basis: the fixture's web book holds its own
   lifecycle and rules today, and the operator's first books at work are the web and phone
   ones, before any backend has a book. If wrong: slice 7, and row 6 of section 5b.
2. **The owner's book is under the same root as the neighbour's.** Decided: a reference
   resolves under the root, and is open otherwise. Basis: the operator's rule that a
   workspace's books sit in one artifacts folder under unique names. If wrong, for another
   team's books kept elsewhere: every reference to them stays open and the book falls back
   to what it can judge from the data it received.
3. **A run may make records at the owner's service through the owner's own calls.**
   Decided: the owner's book arranges the needed state on the shared environment. Basis:
   every book does this today for its own service. If wrong: the needed state concept.
4. **A service tells few states of a foreign record apart (F5).** Decided: one situation
   per class its code distinguishes. Basis, measured on the fixture's gateway: 981 lines of
   code that branch on a foreign state in one place, a label per ticket status, and filter
   on one, published articles. Its book restating the neighbours is 3,812 lines. If wrong
   for another service: the list of needed states grows, and the price in row 2.
5. **Arranging a state through the owner's book costs seconds.** Basis: the ticket book
   plays 406 situations in one run. Measured in slice 1.
6. **Which services a service calls can be read from its code.** Basis: none. If wrong: the
   writing order of slice 4 comes from the operator's list of books instead.
