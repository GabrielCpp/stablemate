# What a run types into a field

Reached from [../SKILL.md](../SKILL.md) when a finding names an input class or a twin, or when a
field's shape must say what a run tries on it. The run derives both from the shapes the book
declares. A book states the shape and the rules, never the class names.

Each class is sent once, from a call the run saw succeed, with every other input as that call
had it. It is named `<field> <class>` in the run's lines: `title too long`. A call the model
already refuses for its caller has no classes and no twins.

## Input classes by shape

| Shape, with its options | Classes the run builds | Twins |
| --- | --- | --- |
| `Str()` or `Str(max_len=N)`, any `format` not listed below | each label of `classes={label: value}` (valid), `blank` (body or screen, required), `too long` (`max_len`) | `surrounding spaces`, `case` (only when the text has letters) |
| `Str(format="date")` | as `Str()`, and `malformed date` | none, and at a screen `midnight` |
| `Str(format="date-time")` | as `Str()` | `time of day`, `offset` |
| `Str(format="uuid"/"hex32"/"ulid")` as a plain field | as `Str()` | none |
| `Id(Record, of=Str(format=...))` | `malformed` (when `of` rejects the text), `one short`, `one long`, `foreign character`, `one unit short` and `one unit long` (`hex32` only), `unknown`, `wrong kind` (another record kind exists in the model), `another owner's` (valid, when the kind names `owned_by`) | none |
| `Id(..., minted=...)` | the classes of its `of`, as a plain field | none |
| `Enum(values)` | `out of enum` | none |
| `Int()` | `malformed number` at a screen | none |
| `Num(places=, text=, min=, max=)` | `malformed number` at a screen; `places`, `min` and `max` add none | `trailing zeros` |
| `Bool()`, `Map`, `Bytes`, `Object` | none of its own | none |
| `List(shape)` | none of its own | `order`, `duplicate` (a call holding two items or more; no `duplicate` for ids) |

Every field also gets the classes below, by where it goes and how it is declared.

| Class | Sent when | Refusal key |
| --- | --- | --- |
| `missing` | the field is required and is not in the path | `missing` |
| `wrong type` | the field is in the body: `123`, `"many"` for an `Int`, `"yes"` for a `Bool` | `wrong_type`, else `malformed` |
| `null` | the field is in the body and not `nullable` | `missing` |

The other default keys: `missing` for `blank`; `malformed` for `malformed`, `too long`, `malformed date`, `out of enum`,
the near misses and `neither`/`all`; `unknown_id` for `unknown`; `wrong_kind` for `wrong kind`.
The keys are in [surface.md](surface.md#refusal-keys).

- Only at a screen: `malformed number`. A field is typed only where the component declares
  `takes` and `holds`; an untyped component gets nothing.
- Only on the wire: `wrong type` and `null` (body), and the relation classes. A `Command` drops
  `wrong type` and `null`, a gRPC `Rpc` drops `wrong type`, `out of enum` and `null`.
- A relation on a body: `Object(...).one_of("a", "b")` sends `a+b neither` and `a+b all`.
  `.together("a", "b")` sends `a+b only a` and `a+b only b`, each when both were sent.
- Only the fields of the top object are typed, and those of the first item of a list body,
  written `[].name`.

## What the book must say for each class

- The model refuses the class: a `Rule` carries the app's words, and the action checks it in
  order. The run expects that refusal from the app, the same words and status.
- The model accepts the class, a valid one such as `another owner's`: the action saves. The run
  plays the call on both sides and compares the rows.
- The model has no rule for a wrong class: the service's `Refusals` (or the endpoint's `refusals`)
  names the key above, and the run expects that refusal. A screen takes the service's keys only.
  With no key and no `Diverges`, the class fails: "the model has no rule for ...".
- The app answers otherwise: settle it as [findings.md](findings.md) says. An app that accepts
  what the book refuses is a `Diverges` on the label as the run prints it, such as
  `Diverges(AddTodo, "title too long", why="...")`.

## Twins and `underspecified`

A twin is two valid values that differ along one dimension of the wire type. The dimensions are
`time of day`, `offset`, `surrounding spaces`, `case`, `trailing zeros`, `order`, `duplicate`
and `midnight`. A pair is dropped when either value fails the shape's own check, so a short
`max_len` can drop `surrounding spaces`.

- The model predicts the pair differently: the run does not send it, and counts it "skipped
  because the model distinguished them". The model already reasons on that dimension. A pair
  that differs only by echoing the typed value counts as alike.
- The model predicts it alike: the run arranges the base twice, sends one value each time and
  compares the two app answers and the rows each call made, changed or removed.
- The two answers differ: the pair is `underspecified`, and the run exits 1. The story answers it.
  The intent ignores the dimension and the app is wrong, or the book models it.
- A field says the dimension does not matter with
  `Field(shape, ignores=("case",), why="...")`. `ignores` takes a dimension above, and `why` is
  required. The pair is then counted "skipped as declared indifferent".
- A pair whose one side the model cannot predict is neither played nor counted.
- A select gets no twins of spelling, however its shape reads: a typed select is left out.
- A date typed into a screen also gets `midnight`: `today` and the day after.

## The language

A journey plays in its `lang`, else in the first language the service declares. The run has no
language option: `run` takes none, and only `screens --lang` does. A journey `lang` the service
does not declare is a `check` finding.

- Journeys: `Journey.lang`, else `Service.language`.
- Cells: `Service.language`, set once before they play.
- Input classes and twins: `Service.language`, set once before they play, whatever language the
  last journey played in. A base arranged by a journey of another language replays in that
  journey's language, and the surface returns to `Service.language` before the class or the twin
  is sent.
- A refusal's words are compared as written: a `Rule` message is one string and equals the
  app's text, character for character, with the status unless the app's is 0. A book has no
  translation of a refusal, so a class whose refusal reads differently per language is
  judged in one language only.

## What a surface answers

[screens.md](screens.md) says the surface returns `Done(rows)` or a `Refusal`, and
`fill` raises `CannotReach`. Add what the run makes of each.

| Answer | Means to the run |
| --- | --- |
| `Done(rows, view)` | the app saved. Agrees with a model `Done`, and the rows are compared. A `Done` where the model refuses fails, unless a `Diverges` names the class |
| `Refusal(message, status=400)` | agrees when the model refuses with the same message and status. A status of 0 matches any |
| `CannotReach(reason)`, raised | the run reads it as `Unreachable`. It agrees with a model refusal, and the class passes. Against a model `Done` it fails |

A surface never returns `Flawed`: the model makes it, where a `Defect` shows.
A class the model has no rule for is read the same way: a `CannotReach` there is `Unreachable`.
It agrees with the refusal the book expects, by a rule or by a default key, and the class passes.
It fails where the book expects the input to save, as a `Diverges` does.

## What the run prints

| Line | Read it as |
| --- | --- |
| `FAIL  input <Endpoint> <field> <class>` | the app answered a class otherwise than the book predicts; the next line says how |
| `inputs: N played, N diverge as declared, N fail` | classes sent and judged. A class skipped for an arrangement it could not make is not in `played` |
| `twins: N pairs played, N skipped because the model distinguished them, [N skipped as declared indifferent,] N underspecified[, N known]` | the pairs and what became of them. `underspecified` above 0 fails the run |
| `Underspecified (fails the run)` | each pair with both app answers and the dimension; answer it as above |
| `KNOWN  twin ...` | a pair registered in `UNDERSPECIFIED.md`; nothing to do |
| `repeats: N delivered, N applied again as declared, N fail` | printed only after a heard event was delivered a second time; it counts events, not fields |
| `Declared divergences never met` | a `Diverges` whose class the app now refuses, or no longer sent |
