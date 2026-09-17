### `unarranged-interaction-precondition` — a `when:` names a state the scenario cannot reach

This `interaction`/`invocation` arm's `when:` states a precondition — the finding's `message`
quotes it — and nothing in the compiled scenario can arrange that state before the arm's
assertions run. Rather than run the arm against whatever state actually holds and risk a false
result for a state the claim never established, the compiler withholds the arm entirely and
gaps it here.

**Which key arranges it is decided by who can establish the state**, and picking the wrong one
leaves the gap standing:

- **`arrange:`** — an act the **performer of the step** carries out on this node's own surface:
  `fill`, `click`, `press`, `select`. Reach for this whenever the `when:` is about what is on
  the screen right now — what the user typed, which option is selected, which panel is open. A
  `when:` over the contents of a form is true only once someone has typed into it, and no
  out-of-process command can type into a form.
  ```markdown
  - when: `name` non-empty and `quantity` a non-negative number
  - arrange: fill(locator="#name-field", value="Widget A")
  - arrange: fill(locator="#quantity-field", value="3")
  ```
- **`fixture:`** — something run *beside* the surface: a seeded row, a signed-in session, a
  stopped dependency. The performer arrives and the state is already there. Reach for this when
  the `when:` is about the world the surface reads from rather than the surface itself. Name a
  fixture node under `docs/features/<surface>/fixtures/<name>.md` that provides it, or an
  existing fixture that already does.

Both bind by **document order**, exactly as `verify:` does: the bullet is written directly under
the `when:` it arranges, so an arm with two `when:` clauses gets its own arrangements under each.
An act's `locator=` is a reference into this book — the anchor of the `component` or
`interaction` that declares the control — and a raw selector is `undeclared-act-locator`. The
act names are a closed list; the vocabulary is rendered into this prompt.

**An arm that `extends:` another inherits the base case's control identity — `on:`, `trigger:`,
`role:`, `name:`, `keyboard:` — and inherits none of its arrangements.** That is deliberate: an
arrangement exists to make a `when:` true, and an extending arm restates `when:` precisely
because its condition differs from the base case's. So a refusal arm extending a success arm
declares its own `arrange:` bullets, filling the form with the values its own `when:` describes;
inheriting the base arm's would arrange the exact state this arm says is false.

If nothing can arrange that state from this surface at all — not by an act, not by a fixture —
the `when:` clause may be claiming something this book cannot actually test yet; say so rather
than forcing an arrangement that does not exist.

**This is not `unresolved-precondition`.** That code covers a `verify:`/path reference to a fact
no earlier producer left behind, or a missing request body — mechanics internal to one already-
compiling scenario. This one is specifically an `interaction`/`invocation`'s own `when:` clause
naming a precondition the compiler could not arrange at all.
