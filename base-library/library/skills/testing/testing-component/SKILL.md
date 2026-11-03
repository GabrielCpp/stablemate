---
name: testing-component
description: "The component test contract for any UI, framework-neutral: the line between a component test and an end-to-end spec drawn by the defect each one can see, a screen's state matrix proven at component level, a component designed so the test decides the order async answers arrive, held answers in place of delays, and the absence assertion that passes before anything happened. Load when writing or reviewing a component, widget or screen test, when deciding which layer a UI test belongs in, when designing a component that fetches or subscribes, or when a UI test races. Applies to UI test files."
applyTo: "**/*.test.tsx,**/*.test.jsx,**/*_test.dart"
tags: [standards, tests]
---

# The Component Test Contract

This contract extends {{ skill_link("testing-design") }}, and every rule there applies here. The
runner, the render call and the fake are stack-specific.

**A component test proves a screen behaves in every state. An end-to-end spec proves the parts are
connected.** Most UI defects live in the first claim, so most UI tests belong at this layer. A
state tested end to end costs a booted stack per run and gives a race that nobody controls.

## 1. Draw the line by the defect

Name the defect first, as testing-design §1 asks. Then ask one question: **would this defect still
show with the backend faked at the screen's seam?** A yes puts the test here. A no makes it an
end-to-end spec.

| The test fails when | Layer |
| --- | --- |
| A 403 shows the message meant for a 500 | Component |
| The list is empty and the screen shows a blank area | Component |
| A double click submits the form twice | Component |
| A late answer overwrites a newer one | Component |
| A failed save loses what the user typed | Component |
| The server rejects the payload this form sends | End to end |
| The session token never reaches the API | End to end |
| A record saved on one screen is missing from the next one | End to end |
| The link on a screen leads to a route nobody registered | End to end |

The end-to-end set stays small by being tied to user goals. It holds one spec per goal the product
exists for, on its success path, and a failure path only where the failure crosses a boundary, such
as an expired session sending the user back to sign-in. A new spec names a connection that no
existing spec crosses. A spec that adds another condition to a screen a journey already crosses
moves down to this layer.

A spec driven through a real browser with a faked backend sits on the component side of this line,
whatever its driver. It answers to this contract, and it runs in the cheapest runner that can show
the defect.

## 2. Mount the largest unit you can put in a state

The default unit is the **screen**: real children, real store, real validation, an in-memory
router, and a fake only at the seam to the outside world. Faking a child hides the wiring defect
testing-design §6 warns about, at a smaller scale.

Test a component on its own when it holds states of its own that are costly to reach through a
screen: a combobox, an upload control, a multi-step form. A leaf that only renders its inputs is
already proven by the screen around it.

Locate elements by role and accessible name, as {{ skill_link("testing-e2e") }} §1 requires. This
layer has the same user-facing contract, and a missed locator here is often an accessibility defect
found cheaply.

## 3. Keep the fake honest

The cost of this layer is a fake that agrees with the component and disagrees with the server. Both
stay green while the product is broken.

- Build every payload from the producer: generated types, the API schema, or a response captured
  from the real server. This is testing-design §3.
- Capture the error bodies too. An error handler written against an invented error shape has never
  run against a real one.
- Make the fake refuse a request it was not told about, and name that request in the failure. A
  request left pending in silence looks like a loading state.

The end-to-end set proves the rest: one real response through each contract the screens rely on.

## 4. Cover the state matrix

Write the screen's states and actions as a matrix before its tests. A
{{ skill_link("behaviour-model") }} is that matrix when the work has one. Every async screen owes at
least these rows:

- Loading, observed while the answer is held.
- Empty, as distinct from loaded.
- Loaded, including partial data where the shape allows it.
- Each error the user is told about differently.
- Recovery: a retry after a failure reaches the loaded state and clears the error.
- An action taken mid-flight: a second submit, a navigation away, a new filter.

The step is complete when every cell has a test or is named impossible. One test covers one cell,
so a red test names the cell that broke.

## 5. Design the component so the test decides the order

Async ordering is predictable when the component states its rule and takes its answers through a
seam. These are design rules, and they belong in the first version of the component:

1. **One seam for every outside answer.** The component receives its client, loader or provider by
   injection. The test replaces that one object and leaves modules alone.
2. **Async state is one value.** A status union (`loading`, `loaded`, `failed`) replaces separate
   flags, so an impossible pair cannot be rendered. The view renders from that value, and a test can
   mount any state without waiting for it.
3. **Concurrency is a written rule.** Each request carries an identity, and the component names what
   happens to an older one: the latest wins, the older is aborted, or the newer queues behind it. A
   rule in code has a cell in the matrix. An order left to the network has none.
4. **Work starts from a named event.** A user action or a mount starts a request. A chain of effects
   watching state makes the order depend on render timing, so collapse it into one transition.
   First-mount effects stay idempotent, because some frameworks run them twice in development.
5. **Time comes through a clock.** Debounce, polling, backoff and expiry read an injected clock or
   the runner's fake timers, so the test advances time.

A test that seems to need a sleep is reporting a missing seam. Fix the component.

## 6. Hold the answer

The fake hands back a pending answer, and the test settles it. The test now owns the order on every
run, and the answer's speed plays no part. For React or Flutter, the hold and the settle are written
out in [references/held-answers.md](references/held-answers.md).

```
first  = backend.hold(search="a")
second = backend.hold(search="ab")

type("a")
type("b")
await visible(role="progressbar")

second.resolve(rows("ab"))
await visible(row="ab result")

first.resolve(rows("a"))
await settle()
assert visible(row="ab result")
assert absent(row="a result")
```

- **Run each order that differs.** Two requests in flight owe both orders. Add the older request
  failing late, which must show no error, and the unmount while pending, which must write nothing.
- **Observe loading while the answer is held.** A fake that answers at once turns the loading
  assertion into a race.
- **Wait on what must become true.** Use the runner's retrying assertion for anything that appears.
- **Settle before you assert absence.** A retrying "absent" passes at once, before the late answer
  has arrived, so it can never fail. Settle the answer and flush the framework's queue, then assert.
  Pair it with a positive assertion that shows the screen is still live.
- **See the race test red.** Remove the concurrency rule from the component and watch the test fail,
  as testing-design §2 requires. An ordering test that stays green with the rule removed proves
  nothing.
- **Count calls for interaction defects.** A double-submit test asserts the fake received one
  request. The disabled button alone is status, and the request count is evidence of work.

## Smells

| Symptom | What it usually means |
| --- | --- |
| A journey spec asserts its fifth error message | A state matrix in the wrong layer (§1) |
| The end-to-end count grows with screens | Specs are tied to screens, and they belong to user goals (§1) |
| Child components are faked in a screen test | Wiring is hidden at a smaller scale (§2) |
| Component tests pass and the server rejects the request | The fake restates the contract (§3) |
| The test patches a module to reach `fetch` | The component has no seam (§5) |
| A sleep or a magic timeout in a component test | A missing seam or clock (§5) |
| `loading && error` can both be true | Async state is flags, not one value (§5) |
| The test passes alone and flakes under load | The fake answers at once and the test races it (§6) |
| An absence assertion was never seen red | It ran before the answer arrived (§6) |

## Review checklist

- [ ] The named defect still shows with the backend faked, or the test is end to end.
- [ ] A new end-to-end spec names a connection no other spec crosses.
- [ ] The unit is the screen, or a component with costly states of its own.
- [ ] Payloads and error bodies come from the producer.
- [ ] Every cell of the state matrix has a test or is named impossible.
- [ ] Each race holds its answers, and runs each order that differs.
- [ ] Every absence assertion comes after a settle.
- [ ] Each ordering test was seen red with the concurrency rule removed.
