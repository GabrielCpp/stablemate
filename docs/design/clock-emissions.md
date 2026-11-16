# An event a service publishes from its clock

## 1. Problem

A service that publishes an event when time passes, such as an SLA timer that breaches when its
due time goes by, has nothing in its book to say so. An event goes on an action through `emits`,
and an action is reached by a call or by a heard event. The service's clock is neither. The
ticket-desk sla book, written by the workflow on 2026-11-16, declared its hearings and reads and
left both breach events out, because the format had no action to carry them. A listener's book
that hears the breach then names an emitter no book declares, and no run proves the breach is
published.

Done: the sla book's writer declares the breach and the warning as emissions of actions the
clock causes, a run arranges a timer past its moment, and the run's `emissions:` line counts both
as proven, with no sleep and no timer in the book or the run.

Out of scope: setting the service's clock; a value that moves with the clock (still `opaque=`);
streams as a cause.

## 2. Parts and concepts

1. **The cause.** An action says what moment of the clock causes it, in words. Owns the
   declaration. Never knows how a run makes the moment arrive.
2. **The moment arrives.** A journey step arranges a record already past the moment, through the
   book's backstage, the same way any state the calls cannot reach is arranged. Owns nothing new.
3. **The proof.** The step that carries a clocked action sends nothing to the app. The model
   performs it, and the run reads the tap for the emissions the action declares, as it does after
   a call. The app's own scan publishes within its interval, and the tap read waits for that
   event, not for a time.

| Concept | Owns | Never knows |
|---|---|---|
| Clocked action | the moment that causes it, as text in `clock` | how the record got past it |
| Past-due arrangement | a record whose moment has passed, through the backstage | the action it leads to |
| Clocked step | model performs, nothing is sent, the tap is read | the service's interval |

## 3. Invariants

- An action with `clock` is carried by no endpoint and hears nothing. Owner: the check, which
  fails an endpoint that carries a clocked action and an action that is both clocked and heard.
- A step for a clocked action proves its emissions from the tap only. With no tap, its emissions
  count unproven, as after a call.

## 4. Forces and patterns

- What causes an emission varies: a call, a heard event, a clock (service events, F5). A call is
  carried by an endpoint, a heard event by `hears`, so a clock gets its own cause on the action,
  `clock: ClassVar[str] = ""`, which reads as the moment in the domain's words. Text over a flag
  because the reader of the book needs the moment, and the flag would push it into prose.
- The service's interval varies (a minute here). The run already reads the tap until the event
  lands or the tap's bound is spent, so the proof needs no new waiting.

## 5. Mapping

- `Action.clock` is new in `ostler/ostler/book/domain.py`, beside `hears` and `emits`.
- The runner's `move` sends nothing to the app for a step whose action is clocked, and opens the
  tap before the model performs, as for an emitting call.
- The check gains the two faults of section 3.
- The skill's event passage (`references/grpc.md`) gains the clocked action and a past-due
  arrangement, replacing "both need a clock the book sets" for a breach.

## 6. Slices

1. The format and the runner, proven on the tool's fixture: a fixture service that publishes an
   event from its own scan, a book with a clocked action, a run that proves it.
2. The writer: `python_book` on the ticket-desk sla service through its paddock task, with
   nothing by hand. Done when the book holds both breach emissions and the run proves them.

## 7. Assumptions

1. A record can be arranged past its moment through the store. Basis: the sla service keeps
   timers in its store with their due time. If wrong: the moment cannot arrive in a run, and the
   emission stays declared and unproven.
2. The tap's bound covers the service's interval. Basis: none measured. If wrong: the bound is
   read from the environment, not changed in the book.
