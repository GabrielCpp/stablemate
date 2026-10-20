# `state`

One settled look of a screen, written as the components a person perceives in it. Reach for
`state` when a walk should check, at one point, that a screen shows the right thing: the loaded
table, the failure banner, the empty message. A control's own looks stay on its
[`component`](component.md) as `states:`.

## Identity

Section type. Every [`screen`](screen.md) declares at least one, or doctor raises `stateless-screen`. A `### <title>` under a `## Screen states` heading in a [`screen`](screen.md)
file, and in no other page type. Its id is `path#anchor`. The heading is `Screen states`, not
`States`, so a free-form `## States` section of prose keeps parsing as prose.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `shows` | no | nested; **mints an obligation** per state. Each child links one component of the same page, then may add `absent`, `disabled`, `checked`, `expanded` or `selected`, in any number. A link with no modifier must be visible |
| `code` | no | link, **owns** its file |
| `when` | no | link, one per record: a [`data-state`](data-state.md). The screen settles in this state only while the record is in that data state. The settle walk reads it back before the settle. It mints no obligation |
| `detail` | no | link: an explanatory [`concept`](concept.md) |
| `verify` | no | a check |
| `fixture` | no | a fixture |
| `tests` | no | link: the test files covering it |

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type).

## How a walk uses it

A [`flow`](flow.md) step that links a state is a stop. At a stop the walk waits for the requests
the screen declares with `requests:` to be answered, then for its `busy:` component to go, then
for one of the screen's states to hold. It then checks that the state which holds is the one the
step names. A different state holding fails the stop at once and names that state.

Doctor also reads the stop against the data. When the state has a `when:` link to a data state, the
walk must hold that record in that data state at the stop. A fixture of the flow can arrange it, and so can an earlier
step that sends a request moving the record there. An [`interaction`](interaction.md) with `sends:`
or a screen passage whose interactions send one counts as that step. The stop fails with
`unheld-condition` when the walk holds another state of the record, or none.

The walk that settles one state on its own reads the state's `when:` back too. After the
fixtures and the navigation, and before the settle, it sends the data state's `observe:` request
and holds its `verify:` rows. A false read stops the walk as the book's red, naming this page:
the state's fixture does not arrange the condition the state claims. A held read makes a failed
settle the app's red. A `when:` binds to the state wherever it sits among the state's bullets.

On a screen that declares `requests:`, a state with `fixture: none` raises `unnamed-condition`.
What the screen shows depends on the answer, so the state names the data state it holds under.

Every component a state shows, and the screen's `busy:` component, is found by its `role:` and
its `name:`. A component with neither cannot be found, and the walk is not compiled.

A busy sign is awaited until it goes. No state lists it as a component that must be visible.

The page names no duration. One responsiveness ceiling, set once for the app, bounds every wait.

## Minimal example

```markdown
## Components

### Results table

- role: table
- name: Results

### Load error

- role: alert
- name: Could not load results

## Screen states

### Loaded

- shows:
  - [Results table](#results-table)
  - [Load error](#load-error) absent

### Error

- shows:
  - [Load error](#load-error)
```

A flow names a state as a step: `- [Results loaded](../screens/results.md#loaded)`.

## Doctor codes it can trip

`stateless-screen` on a screen that declares none, `misplaced-section` on any page that is not a screen, `unresolved-relation` on a `shows:` link,
`unnamed-condition` on a `fixture: none` under a screen that declares `requests:`,
plus the structural codes every section type can trip. See [../doctor-codes.md](../doctor-codes.md).
