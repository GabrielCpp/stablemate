# What a play does to the book

A play is one `run` or `explore` against the live app. It calls the book's `Service.new_model`, the surface and the model in a fixed order. Read this when you need to know what the book is asked to do, in what order, or why a world was or was not reset.

## A world and when it resets

A world is the app behind the surface plus one new model of it. A reset is `surface.reset()` and then `new_model(day)`. An HTTP surface resets by running your `restore()` and forgetting the ids it learned. A page surface sets the browser online, blanks the page, runs `restore()` and then `open()`. A phone surface runs `restore()` and then `open()`. A reset is skipped only when no step has touched the world since the last one.

A `run` goes in this order:

1. The stack and the surface start.
2. Each health journey plays on a new world. A failure stops the run with exit 3.
3. The journeys play in declared order, on one world and one model.
4. The cells of every matrix play.
5. The input classes, then the twins, of each endpoint play.

`explore` against the app resets once for the model it walks to depth 4, then plays cells. The cells of one reached state that change nothing share one arrangement and play first. Each accepted write gets an arrangement of its own, made by a reset and the steps of the path to that state.

## A journey

The first journey takes the world the first reset left. Each later journey continues in the same world and the same model, so the model holds the records the journeys before it made. Those rows are the journey's baseline, taken before its first step. `Listed` compares only what the journey added to the baseline.

A journey gets a new world before it when `alone = True`, and a new world after it when it is alone, fails or skips. A new world makes a screen book sign the page in again as its person and ask its owners for new records.

The journey takes its `given` first, in order: a `Given` calls the model and the surface, a `Needs` asks the owner's book for a record. Then it takes `steps(today)`, where `today` is the model's day once the givens are in. The first failed step ends the journey. A step that cannot be arranged ends it as skipped. Each `Given` with an `undo` is undone in reverse order at the end, unless the journey skipped.

## One step

- A claim (`Same`, `Relates`, `Shows`, `Listed`, `Check`) judges what earlier steps recorded, the rows the surface lists or a probe of the surface. It sends no call.
- A step whose `carries` is `None` is a read the model does not compute. Only the surface answers, and only a refusal fails it.
- Every other step goes to the model first, then to the surface. A screen step hands the surface the lists it must judge, and the surface's `stepping()` runs before it.
- The step passes when both sides refuse with the same message and status, or both succeed. Then the rows the model lists must equal the rows the surface lists, and the answer the model says must equal the app's answer.
- A page that sent a request no screen declares, or a list pick that differs from what the book derives, fails the step.
- A step that arranges an outside event does not call the surface. The run places the event and reads the watch again until it shows what the model says.

## The hooks ostler looks up on a surface

A surface must offer `start`, `stop`, `reset`, `perform(step)` and `rows()`. `HttpSurface`, `PageSurface` and `MobileSurface` give most of them. The book writes `restore()`, and on a page `open()`, `perform` and `rows`. Every other hook is optional, and ostler skips one the surface does not have.

| Name | When ostler calls it |
| --- | --- |
| `today()` | at each reset; the app's day, as a date |
| `follow(watch)` | once, with `Service.watch` |
| `set_lang(lang)` | before each journey, and once before the cells |
| `sign_in(account)` | on a surface that signs in; `None` signs out |
| `account(actor)` | on an owner's surface; the account a page signs in with |
| `open()` | after a sign-in or a taken `Needs` |
| `stepping()`, `expecting(...)` | around each step |
| `strays()`, `list_faults()` | after each step; what each returns fails the step |
| `shown(row)`, `watched(model)`, `express(request, outcome)` | to put model rows and answers in the form the app's are compared in |
| `send(call)` | on an owner's surface; one call and its reply |
| `client`, `watch` | read for the ids the app issued and the watch reads |
| `cover`, `take_breaches` | to judge the entry rules of the lists an answer holds |
| `record_to`, `record`, `finish`, `offset` | to keep a video |

## The model's day

The model's day is `new_model(day)`, where `day` is the surface's `today()` at the reset. A surface with no `today()` gives the machine's date. `check` and `explore --seed-only` have no app, so they use the machine's date.

A screen book's `Needs` makes the owner's model with the owner surface's day, takes the record in and sets the screen model's day to that day. The `today` a journey's `steps` receives is that day. A scene's steps receive the day the new model held before its `Needs` was taken.

## Cells

A cell is one action in one scene. The first cell of a scene resets, makes a new model and plays the scene's steps. The next cell of the scene plays on that arrangement when the cell before passed, met no known defect and left the model's state as it was. Any other outcome ends the arrangement, and the next cell resets.

## Input classes and their base

An endpoint's classes need a base: a call the model accepts, with the model just before it. The run looks for it on the model alone. It takes the first step of any journey, in declared order, that the model accepts. Else it takes the first cell, in matrix order, whose action the model accepts. Only a step with a `carries` can be a base, and a streaming call or a call with no input has no classes.

Each class resets, replays the base's path and sends the varied call. The path is the journey's givens and steps before the base step, in its language, or the cell's scene. A class that both sides refused, with nothing changed, leaves the world for the next class. An endpoint's classes play before its twins.

The finding "no journey step or matrix cell makes a call the model accepts, so its input classes have no base" asks for one of two things. Add a journey step or a cell that calls the endpoint with a success the model accepts, so the model returns an answer and not a refusal. Or declare `Unseen(endpoint, "inputs", Because.<reason>, why)`. A refusal claim or a step the model refuses is no base.

## Twins and Underspecified

A pair of twins plays from the same base, each value on a world of its own. The run skips a pair the model predicts differently, since the model already reasons on that dimension, and a pair the field declares `ignores`. It plays a pair the model predicts alike, and compares the app's two answers and the rows each call made, changed or removed.

`Underspecified` means the app answered the two values apart where the model said they are alike. The run exits 1. Decide with the story whether the intent ignores the dimension: then the app is wrong, or the field declares `ignores=` with a `why`. If the intent cares, the model gets a rule or a read of that dimension. [inputs.md](inputs.md#twins-and-underspecified) holds the dimensions and the register for a field outside your story.

## What `--only` plays

`--only` takes endpoint names, or interaction names in a screen book. It plays these and what they need to run:

- The health journeys always play.
- Every journey with a step of a named call plays whole, with all its other steps. A journey the model cannot walk plays too.
- Of the cells, those whose action is a named call play. Their scenes play whatever steps they hold.
- The input classes and twins of the named endpoints play, each from its base, which replays any steps before it.
- A declared divergence of a named endpoint that no class met fails the run.
- The report of unseen answers and witnesses covers the named calls only.

A play with `--only` is partial. The checks that a whole book has met every divergence, answer and step are left to the full run.
