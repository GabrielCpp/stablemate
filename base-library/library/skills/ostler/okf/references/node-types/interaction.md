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
| `one-per` | no | the iteration variable — one node stands for a whole generated family |
| `unique-by` | no | a dot-path whose value is distinct per instance, with the evidence in prose |
| `variants` | no | `path = token \| token \| …` — a closed per-instance axis from the source |
| `does` | **yes** | nested; **mints an obligation** per value |
| `code` | no | link, **owns** its file |
| `detail` | no | link — an explanatory [`concept`](concept.md) |
| `verify` | no | a check |
| `fixture` | no | a fixture |
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
`leads-to:` — not here. See [component](component.md#relationships).

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
- verify: created(subject="a link row for the submitted URL")
```

## Doctor codes it can trip

`missing-required-bullet` (five keys), `undeclared-obligation`, `weak-check`,
`unstated-precondition`, `compound-normative-bullet`, `unresolved-relation` on `on:`,
`ambiguous-locator`, `stale-defect`, `malformed-defect`; with the repeat keys also `static-template`, `unproven-unique-name`,
`malformed-template`, `malformed-variants`. See [../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

Bullets state what this action does. If a reader could pick the wrong one — a legacy flow and
its replacement, each right in its own context — and still satisfy every claim on it, that
belongs in a [`concept`](concept.md), pointed at with `detail:`.
