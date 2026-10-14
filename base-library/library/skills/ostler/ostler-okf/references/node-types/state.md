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
plus the structural codes every section type can trip. See [../doctor-codes.md](../doctor-codes.md).
