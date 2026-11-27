# Findings, and what the book cannot see

Reached from step 7 of adding a route in [../SKILL.md](../SKILL.md), and whenever a command
reports something.

## What each command reports

| Finding | Command | Means | Fix |
| --- | --- | --- | --- |
| `<Record>: no source pointer` | check | a record or element names no source | add `source`; a finding present before your pass is the baseline, leave it |
| `record <Record>: <book> keeps <Record>, which no screen of it writes` | check | a screen book keeps the lifecycle, rules or actions of a record a backend's book stores and no screen of its own writes | take the state from the backend's book with `Needs` and delete the copy; see [screens.md](screens.md#a-record-a-backends-book-stores) |
| `interaction <Act>: <book> makes <Record> outside its screens` | check | an act with no screen, in a scene, a cell or a journey, makes a record the backend stores | ask the backend's book for the state with `Needs` instead; keep the act only for what is not a record, such as the clock or the network |
| endpoint, journey or rule not registered | check | a class exists that nothing lists | add it to `ALL` or `__all__` |
| endpoint no matrix places | check | it will be played in every state | add a column to the matrix of the record it touches |
| module nothing imports | check | dead file | import it where it belongs, or delete it |
| `<file>:<line>: hardcodes <kind> ...` | check | a module of the book hardcodes a UUID, ULID, AWS ARN, cloud resource id, storage URI or host URL outside `Environment` | resolve environment ids with `Reference` or learn them from replies, mint unknown ids with `uuid4()`, and keep hosts inside `Environment` |
| `the book contradicts itself` | explore --seed-only | a scene or fixture arranges a record the model refuses | fix the scene's steps or the fixture, never the rule |
| `FAIL state ...` with `path:` and `rows differ` | explore --only | the model and the app disagree on one cell | compare the two lists; decide book wrong or app wrong |
| `rules never refused: N` | explore, run | a rule no reachable cell breaks | add the scene or input that breaks it, or the rule is dead |
| `declared scenes never reached` | explore, run | a scene no walk reaches | fix its `reached_by`, or the scene is wrong |
| `FAIL <Journey>` | run | a journey step disagreed | same as a cell FAIL |
| `KNOWN <Journey>` | run | a declared `Defect` answered as declared | nothing |
| `inputs: ... diverge as declared` | run | a declared `Diverges` held | nothing |
| `FAIL  input <Endpoint> <class>` | run | the app answered an input class other than the book predicts | book wrong: fix the shape or the refusal; app lenient: declare `Diverges` |
| `Declared divergences never met` | run | a `Diverges` whose class the app now refuses | the app was fixed or the class name changed: remove or rename it |
| a gap under "what the run witnessed" | run | an answer or field no step showed | reach it with a step, or declare it `Unseen` |
| `Seen with one value only` | run | an `Enum`, `Bool` or number field every play read in one value | read it in a second value with a fixture or a scene that differs, or declare it `Unseen` |

A copy finding blocks the run once the book refers to a record of another book with `Foreign`, and is a `NOTE` before it does, so a screen book written before a book could refer to another still passes.

## Book wrong or app wrong

A FAIL is one of two things. Read the source the endpoint's `source` names and decide:

- **The book is wrong** when the source does what the app did. Fix the model, the shape or
  the fixture. When the fix is a behaviour a reader would not guess, it gets a `why`.
- **The app is wrong** when the source, the openapi or the product's rule says otherwise. Keep
  the intended behaviour in the model and write a `DISAGREEMENTS.md` entry. Then declare it
  by where it showed. A whole input class the app accepts and the book refuses, such as any
  malformed id, is a `Diverges` on the endpoint. A call in a cell or a journey that the app
  answers wrongly is a `Defect` on the action.

Never make a FAIL pass by loosening a shape, widening an existing fixture, or adding a step
that hides the difference.

## A list answer holds a row the model does not expect

A row in a call's list that the model does not predict is not loosened in the model and not left as
prose in `DISAGREEMENTS.md`. State the rule the list breaks on `List(shape, entries=(...))`, a rule
over every entry such as `no_repeat(key)` or `in_order(key)`, so each run judges it. When the source
shows the app breaks that rule on purpose, or by a defect the app's own code or tracker names,
declare `Defect(breaks=rule)` on the action whose answer holds the list, sharing the rule object, as [model.md](model.md) says.

## DISAGREEMENTS.md

One numbered entry per disagreement, after the last one:

```markdown
## 29. <what happens, as a sentence>

- Step: <the call, and whether a probe, a replay or a run found it>.
- Source and openapi: <what they say>, when it differs from what the app did.
- App did: <the answer>.
- Classification: app wrong, app lenient, app inconsistent, or book wrong (fixed). <What the book does about it.>
```

## What the book declares it cannot see

- `Unseen(Endpoint, "401", Because.SHARED_GATE, "<why>")` or
  `Unseen(Endpoint, "200: path.to.field", Because.<reason>, "<why>")` in
  `Service(unseen=...)`: an answer or field no run reaches. `Because` is a closed list of what
  lies out of the book's reach. A gap the book can close by arranging a state, a caller or an
  input has no reason on the list: arrange it.

  | `Because` | Means | A typical case |
  | --- | --- | --- |
  | `SHARED_GATE` | the answer comes from a gate every endpoint shares, and another endpoint shows it | the 401 of a token check that every route runs |
  | `RUNTIME` | the runtime cannot yet send the request that draws it or read the answer | a refusal the app's router gives in plain text, which the runtime cannot read |
  | `NEVER_FILLED` | the app never fills the field for any caller | a field the openapi lists and no handler sets |
  | `OUTSIDE` | only a system outside the app sets it | a state a nightly job makes; the model's behaviour behind a route the app does not implement |
  | `NO_ACCOUNT` | no environment the book runs in provisions an account that draws it | an admin answer where no environment has an admin |
  | `TEST_HOOK` | the endpoint is a test hook only the book calls | a route that seeds data for the book |

  An outside happening, an action, a rule or a scene takes only `RUNTIME`, `OUTSIDE` or
  `NO_ACCOUNT`, and the book refuses any other.
  A list whose only entries other cells made gets an entry the book makes, through a standing
  fact the backstage arranges once and the model seeds.
- `Unseen(Ghost, Because.RUNTIME, "<why>")`: an outside happening, an action, a rule or a scene no play
  exercised. A full run lists each such element under "Stated and never played" and fails on
  the ones the book leaves undeclared. An outside happening is played when a step or a `Given` arranges it. An
  action is played when a step, a cell or an input class takes it and the model accepts. A rule is
  played when a play draws its refusal and the app agrees. A scene is played when a cell arranges it. The first move
  is to play it: a journey step, a matrix cell, an input class or a `Given`. A declaration is for what
  the book cannot cause, and it takes `RUNTIME`, `OUTSIDE` or `NO_ACCOUNT`. These four kinds take no item.
  A declaration for an element the run played is stale and fails the run.
- `Diverges(Endpoint, "<input class as the run prints it>", why="<why>")` in
  `Service(diverges=...)`: the app accepts an input class the book refuses.
- A route the app answers with 501 or leaves unimplemented gets an endpoint whose answer says
  so, and an entry when the openapi promises more.

Every why says something a reader could check. "Not covered yet" is not a why.
