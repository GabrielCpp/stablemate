# Events a service emits and hears

Status: proposed, not built. Written with the decompose order. I had read the book runtime
and its outside events before writing it, so each part and concept below was checked against
the test "would I have named this without having seen the code".

## 1. Problem

Two people feel this.

The first is handed an event name, such as `ticket.changed`, and must follow it across
services: who emits it, when, what it carries, who hears it, and what each listener does.
Today they search several repositories owned by several teams. The books do not help. An
event has no name in any book, no endpoint says it emits one, and `search` on the name
finds nothing.

The second hunts bugs between services. A listener reads a field the emitter no longer
sends, or sends under another type. An action that should announce a change stops doing so.
A handler that hears the same event twice applies it twice. No run of any book sees these.

Facts of the domain:

- **A service is one unit however it is deployed.** An API pod and a handler pod run the
  same code. The handler reads a queue.
- **An event travels by name.** The emitter publishes on a bus: a name, a source and a JSON
  detail. The bus routes by rule to one queue per listener. A queue delivers a message at
  least once, in no promised order.
- **Emitter and listener are often different teams.** Their code sits in different
  repositories. Their books may or may not sit under the same root.
- **What causes an emission varies.** A call to the API, another event the service heard, a
  clock, or a change in a data store that a stream turns into an event.
- **An environment is shared.** An event put on the bus reaches every listener, the other
  teams' services included. A message read off a queue and deleted is gone for every other
  reader.

Done, as those two people see it:

- `search ticket.changed` across the books of a root answers the first person in one
  command: the event and its fields, each emitter with what causes it, each listener with
  what it does. `explain` on the event says the same.
- `check` reports a listener that reads a field its event does not declare or declares under
  another type, and a listener of an event nothing under the root emits.
- A run of the emitter's book fails when an action that should emit does not, or emits other
  values than the book says.
- A run of the listener's book fails when the handler, given the event, does not reach the
  state the model predicts, or reaches another state when given it twice.
- On the ticket-desk fixture, `ticket.changed` shows its one emitter and its four listeners.

Out of scope:

- The order of two events, and anything two handlers do at once.
- Retries, dead-letter queues and messages no handler can read.
- Whether the bus's rules are configured right, beyond the event's name.
- How long an event takes to arrive.

## 1b. Claims that reached this note

1. "A change another service announces is an outside event: one class per thing that happens
   there, carrying an action of this book's model. The surface makes it happen by sending the
   other service's own call, imported from that service's book, and the run reads a watch
   until the change shows." The book runtime and its skill, today.
2. "One book is one service even if deployed as two pods. The handler sits within the rest."
   The operator, 2026-11-14.
3. "The event is a named element declared once. The action that publishes says it emits it.
   The run proves a handler by putting the event on the bus." My own earlier sketch.

## 2. Parts and concepts

### Level 1: parts

| Part | Owns | Never knows | Hands over |
|---|---|---|---|
| The contract | what one event is: its name, its source, what it carries | who listens, what any listener does | the event, to both sides and to the map |
| The emitting side | when this service emits an event and with which values | the listeners | the emissions the proof must observe |
| The hearing side | what this service does when it hears an event, and which fields it reads | who emitted it and why | the hearings the proof must exercise |
| The proof | observing an emission, placing an event before this service, judging the state | any other service | a verdict per emission and per hearing |
| The map | every emitter and listener of an event across the books of a root | how either side is proven | search results, and findings where the two sides disagree |

Flow. An event's contract is written once. A service's book says which of its actions emit
it. Another service's book says what it does on hearing it and which fields it reads. The
map joins the two by the event's name whenever a book is searched or checked. During a run,
the proof watches for the emissions the run caused, and places events before the service's
own handler to exercise each hearing.

### Level 2: concepts

**The contract**

| Concept | Owns | Never knows |
|---|---|---|
| Event | a name, a source and the shape of the detail | emitters' logic, listeners |
| Foreign event | the same, for an event whose emitter has no book under this root, and who owns it | the emitter's logic |

**The emitting side**

| Concept | Owns | Never knows |
|---|---|---|
| Emission | that one action of the model results in one event, and how the detail follows from the model after the action | what caused the action, the listeners |

**The hearing side**

| Concept | Owns | Never knows |
|---|---|---|
| Hearing | that one happening elsewhere reaches this service as one event, which action of the model it carries, and which fields of the detail the handler reads | the emitter |
| Repeat rule | what a second delivery of the same event does | why it was delivered twice |

**The proof**

| Concept | Owns | Never knows |
|---|---|---|
| Tap | the events emitted during the run that concern a record the run made | events about anyone else's records |
| Delivery | placing one event before this service's handler in the form the bus would give it | every other listener |
| Landing | reading again until the state the model predicts shows | how the event arrived |

**The map**

| Concept | Owns | Never knows |
|---|---|---|
| Event index | for each event name under a root: its contract, its emissions, its hearings | how a run proves them |
| Disagreement | a field a hearing reads that the contract lacks or types otherwise | which side is wrong |
| Orphan | a hearing of an event nothing under the root emits and no foreign event declares, or an event nothing hears | whether it matters |

## 3. Invariants

| Invariant | Owner |
|---|---|
| An event has one contract under a root. Every emission and hearing names it. | Event index |
| A hearing carries an action of the model, and the handler is judged by the state the model predicts. | Hearing |
| The run places an event only before the service its book is of. No other listener receives it. | Delivery |
| The tap removes no event another reader needs, and judges only events about records the run made. | Tap |
| The run waits by reading again, never by a wait of fixed length. | Landing |
| A book that declares no event behaves as it does today. | Event index |

## 4. Forces and patterns

Forces:

- F1. One service, two pods, one book.
- F2. Emitter and listener are different books, often different teams.
- F3. The environment is shared, and its other listeners are real.
- F4. How an event travels varies between companies and over time: a bus and queues here, a
  topic or a log elsewhere.
- F5. What causes an emission varies: a call, a heard event, a clock, a stream.
- F6. A queue delivers at least once.
- F7. A listener's team may have no access to the emitter's service, or it may be down.

Between parts: the contract is a value both sides refer to by name. The map is a read over
the books, computed when asked. The proof depends on the two sides and on nothing else.

Inside parts:

- F1 puts hearings in the service's one declaration, beside its endpoints, on the same model,
  journeys and decisions. There is no handler package and no new kind of surface.
- F2 makes the event's name the join. A listener under the same root refers to the emitter's
  own contract. A listener of another root's event declares a foreign event and names its
  owner.
- F3 decides how a hearing is proven: the run writes the message to this service's own
  queue, in the form the bus would have written it. It never publishes on the bus. F3 also
  makes the tap a reader that deletes nothing.
- F4 makes delivery and the tap one role with a variant per way of travelling. The book's
  environment chooses the variant and names the queue. The first variant is a bus that routes
  to queues.
- F5 attaches an emission to an action of the model, not to an endpoint. Whatever caused the
  action, the emission follows.
- F6 gives every hearing a second delivery the runtime adds itself, the way it adds twins to
  a typed input. The repeat rule says "same state" unless the hearing states otherwise with
  a reason.
- F7 means a hearing no longer needs the emitter's service or its book to be exercised.

Claims from 1b:

1. Kept and reshaped. "One class per thing that happens elsewhere, carrying an action" is the
   hearing, re-derived from F2. Making it happen through the other service's own call is no
   longer the only way (F3, F7). It stays for a journey that wants the whole chain.
2. Re-derived from F1.
3. The named event and the emission are re-derived from F2 and F5. "Putting the event on the
   bus" is rejected by F3.

SOLID check. A new way of travelling adds one variant and one line in an environment. A new
event adds one contract. The hearing side never names an emitter. The proof names neither a
bus nor a queue.

Open lookups:

- L1. Whether a run may write to a service's queue and read a tap in the environments at
  work (A1).
- L2. Whether the books of two teams sit under one root (A2).

## 5. Mapping onto the existing system

Revision log: none yet.

| Item | Verdict | Where |
|---|---|---|
| Event, foreign event | New | A class in the emitter's book, its detail in the shapes an endpoint's answer already uses (`ostler/ostler/book/http.py`). |
| Emission | New | An attribute of a model action, with a function from the model to the detail. |
| Hearing | Reshape | `Arrange` in `arrange.py` is the hearing without its event. It gains the event it is heard as, the fields it reads, and the detail for one occurrence. |
| Repeat rule | New | On the hearing. The second delivery is one more column the runtime derives. |
| Landing | Exists | The watch, read again until the model's state shows (`runner.py`). |
| Delivery, tap | New | One role beside the surfaces, the first variant for a bus that routes to queues. The AWS client becomes an optional dependency of the tool. |
| Event index | Reshape | The book-wide search already reads every book under a root (`index.py`). It knows no event, and `search` has no kind for one. |
| Disagreement, orphan | New | `check` judges one book today. These are the first findings that read two. |

The author's lines. The emitter's book:

```python
class TicketChanged(Event):
    """A ticket's stored record changed."""
    name = "ticket.changed"
    source = "zeta.dynamostream"
    detail = Object(ticket_id=Id(Ticket), actor=Str(), changes=List(Change), snapshot=Snapshot)

class Transition(Action[TicketFixture, Ticket]):
    emits = (TicketChanged,)
```

The listener's book:

```python
from services.dynamostream.events import TicketChanged

class Opens(Arrange[Ticket]):
    does = "A customer opens a ticket. Both of its timers start."
    carries = actions.TicketOpened
    heard = TicketChanged
    reads = ("ticket_id", "snapshot.priority", "snapshot.team")
```

Mismatch found: the fixture's `ticket.changed` is emitted by a stream service, not by the
ticket service whose call caused the change. So the emitter of an event is not always the
service a reader would guess. The map answers that, and the emission sits in the stream
service's book, on the action that hears the store change.

What the existing system has that the design lacks: making an outside event happen through
the other service's call. It is not waste. It proves the whole chain, and it stays.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| A book with outside events made through another service's call | its cells play green | the gRPC book tests | pass | pass unchanged |
| A book that declares no event | `check` exits 0, index unchanged | the index comparison | 0 findings on the fixture books | 0 findings, index byte-identical |
| Other listeners on a shared bus | no event from any book run | nothing | none sent today | none sent, by the delivery invariant |
| A person installing the tool without a bus | no AWS client needed | nothing | not a dependency | still optional |

The third row is enforced by nothing today. It becomes the delivery invariant of section 3.

## 6. Slices

1. **An event can be followed by its name.** Event, emission and hearing as declarations.
   `search <event name>` across a root's books returns the contract, each emitter and each
   listener. `explain` on the event prints the same. Done on two fixture books, with no run
   involved.
2. **Two books that disagree are told.** A hearing that reads a field the contract lacks, or
   under another type, is a finding of `check` that names both books. An orphan is a
   finding that does not block. Done with one planted disagreement.
3. **A handler is proven with no other service.** Delivery to the service's own queue, the
   landing, and the second delivery. Done on one ticket-desk listener: green as it stands,
   red when the handler applies a second delivery again.
4. **An emission is proven.** The tap. Done on the ticket-desk emitter: red when an action
   stops emitting, and red when a field's value differs from the book's.
5. **The writers.** The skill, and the book workflow states events from the source. Done
   when a workflow run on a ticket-desk listener writes its hearings.

## 7. Assumptions

- A1. **Assumption:** in each environment a book runs on, the run may write a message to the
  service's own queue and read a tap queue provided for it. **Decided:** F3. **Basis:** true
  on the fixture's emulator. None for the environments at work. **If wrong:** there, a
  hearing is proven only through the other service's call, as today, and an emission is not
  proven. Slices 1 and 2 do not depend on it.
- A2. **Assumption:** the books of an event's emitter and listener often sit under one root.
  **Decided:** the map reads one root, and a foreign event covers the rest. **Basis:** the
  operator's rule that the books of a workspace of several repositories sit together. None
  across teams. **If wrong:** most events are foreign, the map shows one side only, and a
  shared place for contracts becomes its own design.
- A3. **Assumption:** the form the bus writes to a queue is stable and documented.
  **Decided:** delivery writes that form itself. **Basis:** the provider documents it.
- A4. **Assumption:** a second delivery should leave the same state unless the book says
  otherwise. **Decided:** F6. **Basis:** the queue's at-least-once delivery.
- A5. **Assumption:** the detail of an event follows from the model after the action.
  **Decided:** an emission is a function of the model. **If wrong:** a field the model cannot
  predict is left unjudged, the way an answer's field already can be.
