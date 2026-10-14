# `passage`

A named run of one screen's own interactions that leaves one of its states and lands on a state of
this screen or another. Reach for `passage` when a flow should walk from one settled look to the
next and check the requests the move sends. A state alone says where a screen is. A passage says how
the person gets to the next one.

## Identity

Section type. A `### <title>` under a `## Passages` heading in a [`screen`](screen.md) file, and in
no other page type. Its id is `path#anchor`. A passage mints no obligation of its own. The stop at
its `to:` state checks it.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `from` | yes | link: the [`state`](state.md) of this screen the passage leaves |
| `steps` | yes | nested; each child links one [`interaction`](interaction.md) of this screen, performed in order |
| `to` | yes | link: the [`state`](state.md) the passage lands on, on this screen or another |
| `requests` | no | nested; each child is `METHOD /path`, a request the passage sends. The stop at `to:` waits for them before it checks the state |
| `code` | no | link, **owns** its file |
| `detail` | no | link: an explanatory [`concept`](concept.md) |

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type).

## How a walk uses it

A [`flow`](flow.md) step that links a passage performs its interactions in order. The walk then
stops at the `to:` state as if the flow had a state step there. When the step before the passage is
not a stop at its `from:` state, the walk stops at `from:` first. A state step right after a passage
that names the same `to:` state is not stopped at twice.

The stop waits for the passage's `requests:`. When `to:` is on another screen, it then waits for the
requests that screen declares. A web walk then fails the stop when the page sent a `fetch` or `xhr`
request to the app's own servers that the stop did not wait for. The failure names the extra
`POST /api/...`. List it under the passage's `requests:` when the passage sends it. A device walk
makes no such check.

Every component a passage acts on is found by its `role:` and a literal `name:`, as a person
perceives it. A style selector or a test id is not that.

## Minimal example

```markdown
## Passages

### Open details

- from: [Loaded](#loaded)
- steps:
  - [Open details](#open-details-click)
- to: [Shown](details.md#shown)
- requests:
  - GET /api/results/{id}
```

A flow names it as a step: `- [Open details](../screens/results.md#open-details)`.

## Doctor codes it can trip

`passage-shape` on a `from:`, `to:`, `steps:` or `requests:` a walk cannot follow,
`unresolved-relation` on a link to a state that no longer exists, `broken-joint`, `unarranged-stop`
and `unperceivable-element` on the flows and components that use it, `misplaced-section` on any page
that is not a screen, plus the structural codes every section type can trip. See
[../doctor-codes.md](../doctor-codes.md).
