# `screen`

A user-facing view of a GUI surface: one addressable destination a person can be on. Reach for
`screen` when the thing has a route and a person can be *at* it; the controls on it are
[`component`](component.md) nodes and the things a person does there are
[`interaction`](interaction.md) nodes, both `### id` sections in this same file.

Not a screen: a modal or drawer that has no route of its own (that is a component with
`states:`), or a server-rendered page with no client surface (see [`server`](server.md)).

## Identity

File type. Its own `.md` under `docs/features/<service>/gui/screens/`, with `type: screen` in
frontmatter — stamped by `ostler create` / `ostler scaffold`, never hand-written. Its id is the
file path; section nodes inside it are `path#anchor`.

## Bullet keys

Canonical order — the order `ostler fmt` will put them in.

| key | required | what it does |
| --- | --- | --- |
| `route` | yes | the path this screen is addressed by |
| `requires` | yes | nested; each child resolves as a link — the preconditions to be here |
| `params` | yes | nested; each child resolves as a link — route/query parameters |
| `entry` | no | this screen is entered from outside in-app navigation |
| `detail` | no | link — an explanatory [`concept`](concept.md) |

All three required keys are required **even when empty**. A screen that omits `requires:` is
indistinguishable from one that is genuinely unconditional, and reachability cannot tell
"nothing to satisfy" from "nobody wrote it down" — so state `none`.

`entry:` is a claim, not a silencer: it says the screen is reached from outside the app (app
root, emailed deep link, OAuth callback) and the value says how. It exempts the screen from the
reachability check, so it earns that exemption by stating the route in.

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type),
which mint an obligation on every type.

## Required sections

None. `## Components` and `## Interactions` are the conventional headings, added as the screen
gains them.

## Relationships

A component on this screen navigates here with `leads-to:`; that is what makes the screen
reachable. Nothing on the screen node itself points outward except `requires:` and `params:`.

## Minimal example

```bash
timeout 30 ostler scaffold screen link-editor --service acme
```

```markdown
---
type: screen
---

# Link Editor

- route: /links/:id/edit
- requires: signed-in editor session
- params: id — the short-link id being edited
```

## Doctor codes it can trip

`missing-required-bullet`, `unreachable-screen`, `no-entry-point` (warn, raised against the
surface when no screen on it declares `entry:`), `unresolved-relation`, plus the structural
codes every file type can trip. See [../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

Bullets state what this screen is. If a reader could pick the wrong screen — an old editor and
a new one, both correct in different contexts — and still satisfy every claim on it, that
belongs in a [`concept`](concept.md), pointed at with `detail:`.
