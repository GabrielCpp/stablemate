# `interaction`

Something a person does on a screen and what happens when they do. Reach for `interaction` for
a **human-driven** action; a machine-driven one is an [`invocation`](invocation.md), and the
control itself is a [`component`](component.md).

The line between the two types is the actor, and getting it wrong is the most common
`node-type` finding: a browser click is an interaction, a webhook or a scheduled job is an
invocation.

## Identity

Section type. A `### <id>` under a `## Interactions` heading, normally in a
[`screen`](screen.md) file. Its id is `path#anchor`.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `on` | **yes** | link — the component this acts on |
| `trigger` | **yes** | what fires it |
| `role` | **yes** | the ARIA role of the control |
| `name` | **yes** | its accessible name |
| `keyboard` | **yes** | **mints an obligation** — how it is fired without a pointer |
| `when` | no | **mints an obligation** — the condition it applies under |
| `exclusive-with` | no | link — a sibling it can never co-render with |
| `extends` | no | link — the base arm this one narrows, inheriting its control identity (`on:`/`trigger:`/`role:`/`name:`/`keyboard:`), none of its arrangements |
| `same-as` | no | link, multi-valued — another node documenting this same interaction |
| `one-per` | no | the iteration variable — one node stands for a whole generated family |
| `unique-by` | no | a dot-path whose value is distinct per instance, with the evidence in prose |
| `variants` | no | `path = token \| token \| …` — a closed per-instance axis from the source |
| `does` | **yes** | nested; **mints an obligation** per value |
| `code` | no | link, **owns** its file |
| `detail` | no | link — an explanatory [`concept`](concept.md) |
| `verify` | no | a check |
| `fixture` | no | a fixture |
| `arrange` | no | an act performed on this node's own surface |
| `capture` | no | a capture |
| `tests` | no | link — the test files covering it |

An interaction is by definition operable, so five keys are required. `role:`/`name:` give
`getByRole(role, {name})` instead of a brittle selector. `none` on `keyboard:` is a *claim*
that the control is pointer-only — an accessibility defect worth being able to **find**, not a
blank to leave empty.

An interaction repeated once per member of a collection carries the same repeat keys as a
component — see the
[repeat grammar](../bullet-grammar.md#repeated-controls-one-per--unique-by--variants). Note
`on:` is a reference, not membership: pointing `on:` a repeated component does **not** inherit
its family; write the repeat keys where the iteration actually is.

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type).

## Relationships

`on:` links the component this acts on. Navigation is recorded on that **component**, with
`leads-to:` — not here. See [component](component.md#relationships). `same-as:` names another
node documenting this same interaction.

## Minimal example

```bash
timeout 30 ostler scaffold interaction save-link --in docs/features/acme/gui/screens/link-editor.md
```

```markdown
### save-link

- on: [save-button](#save-button)
- trigger: click or Enter on the Save button
- role: button
- name: Save
- keyboard: Tab to focus, Enter to activate
- when: the URL field holds a valid absolute URL
- does: persists the link and returns to the list
- code: web/src/LinkEditor.tsx::onSave
- fixture: signed_in_editor
- arrange: fill(locator="#url-field", value="https://example.com/a")
- verify: created(subject="a link row for the submitted URL")
```

## Arranging a precondition: `fixture:` or `arrange:`

A `when:` states the condition the interaction applies under, and a scenario that performs the
step in a world where that condition is false proves nothing about the claim. Which key
arranges it is decided by **who can establish the state**:

- **`fixture:`** — something run *beside* the surface: a seeded row, a signed-in session, a
  stopped dependency. The performer arrives and the state is already there.
- **`arrange:`** — an act the **performer of the step** carries out on this node's own surface:
  `fill`, `click`, `press`, `select`. A `when:` over what the user typed is true only once
  someone has typed, and no out-of-process command can type into a form.

Both bind by document order, exactly as `verify:` does, so an arrangement written under a
`when:` arranges *that* arm. An act's `locator=` is a reference into this book — the anchor of
the `component` or `interaction` that declares the control — and a raw selector is
`undeclared-act-locator`. The act names are a closed list; see
[../check-vocabulary.md](../check-vocabulary.md) for the vocabulary this repo renders into
every builder prompt.

An arm that `extends:` another inherits the base case's **control identity** — `on:`,
`trigger:`, `role:`, `name:`, `keyboard:` — and inherits **none of its arrangements**. An
arrangement exists to make a `when:` true, and an extending arm restates `when:` precisely
because its condition differs; inheriting the base arm's acts would arrange the exact state
this arm says is false. So a refusal arm extending a success arm writes its own `arrange:`
bullets, filling the form with the values its own `when:` describes.

`same-as:` is unrelated to that inheritance. `extends:` says this arm is a narrower version of
another; `same-as:` says this interaction and the one it names are the *same* documented action,
described again in a second place — never a narrower one, and carrying none of `extends:`'s
control-identity inheritance. It is symmetric and must be declared on both sides. Its consumer is the QA obligation packet: a change to the cited symbol maps to every node that cites it, and without `same-as:` one thing written in three places reads as three things and trips the container fan-out demotion that exists to catch sprawl. `same-as:` is the declared fact that collapses them back into one family.

The occurrences must also *agree*: each states the same normative claims, not two different
ones. A member that omits a key is not a disagreement — silence just means that occurrence
was written cheaply, without repeating a claim another occurrence already made — but two
members that both state a key must state the same value; `doctor`'s `same-as-disagreement`
finds it when they don't.

## Doctor codes it can trip

`missing-required-bullet` (five keys), `undeclared-obligation`, `weak-check`,
`unstated-precondition`, `compound-normative-bullet`, `unresolved-relation` on `on:` or
`same-as:`, `one-way-same-as`, `same-as-disagreement`,
`ambiguous-locator`, `unparsed-act`, `undeclared-act-locator`, `stale-defect`, `malformed-defect`; with the repeat keys also `static-template`, `unproven-unique-name`,
`malformed-template`, `malformed-variants`. See [../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

Bullets state what this action does. If a reader could pick the wrong one — a legacy flow and
its replacement, each right in its own context — and still satisfy every claim on it, that
belongs in a [`concept`](concept.md), pointed at with `detail:`.
