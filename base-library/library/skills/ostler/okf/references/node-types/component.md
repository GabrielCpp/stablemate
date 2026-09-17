# `component`

One control or region on a screen: the thing a person sees and a test locates. Reach for
`component` for what is *present*; what a person *does* with it is an
[`interaction`](interaction.md).

## Identity

Section type. A `### <id>` under a `## Components` heading, normally in a
[`screen`](screen.md) file. Its id is `path#anchor`, kebab-cased by `ostler fmt`.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `selector` | no | a locator, when role+name cannot address it |
| `role` | **yes** | **mints an obligation** — the ARIA role |
| `name` | **yes** | **mints an obligation** — the accessible name |
| `placement` | no | viewport bands, e.g. `width 60-100%, x 0-20%` |
| `keyboard` | no | **mints an obligation** — how it is reached and operated |
| `extends` | no | link — the component this specializes |
| `parent` | no | link — the component containing it |
| `exclusive-with` | no | link — a sibling it can never co-render with |
| `one-per` | no | the iteration variable — one node stands for a whole generated family |
| `unique-by` | no | a dot-path whose value is distinct per instance, with the evidence in prose |
| `variants` | no | `path = token \| token \| …` — a closed per-instance axis from the source |
| `states` | no | **mints an obligation** — the states it can be in |
| `code` | no | link, **owns** its file |
| `detail` | no | link — an explanatory [`concept`](concept.md) |
| `verify` | no | a check |
| `fixture` | no | a fixture |

`role:` and `name:` are required because they are the same fact twice: the accessibility
contract a screen reader announces, and the `getByRole(role, {name})` a test locates by. `none`
is a legitimate value on `name:` — a decorative element has no accessible name — but it must be
*stated*, so "no name" and "nobody looked" stay distinguishable.

`placement:` is screen-relative on purpose: no `sidebar`/`main-column` vocabulary, nothing that
assumes a grid. It is the one documented fact a role+name assertion cannot check — `getByRole`
finds an element whether the page lays it out across the window or crushes it into a sliver.

`selector:` has two different readers, and only one of them is general-purpose CSS. A compiled
`verify: visible(locator=...)` resolves `selector:` to a live Playwright locator (`qa.by_css`),
so any valid CSS — including an attribute-value predicate like `[data-state="booked"]` — works
there. `ostler vet`'s screen census is narrower: it matches against strings the render scan
itself mints for each element (`#id`, or `tag.class:nth(i)` for one with no id), plus one extra
form it resolves by the ARIA role it recorded rather than by string match, `tag[role="..."]`. Any
other predicate — an attribute value, a boolean attribute, a pseudo-class — addresses nothing the
scan ever produces, so a component whose `selector:` uses one reads `missing` on every render,
not just an unlucky one. A control whose identity depends on a piece of state (`booked`, not
merely `disabled`) belongs on `states:`, not folded into `selector:` on a second component node
that exists only to carry it. That does not mean a raw-CSS `locator=` bypasses the census: a
check's `locator=` is a reference into the book, not a live selector — it must resolve to a
`#component` or `#interaction` anchor the book declares (`ostler doctor`'s
`undeclared-check-locator` enforces this unconditionally, with no exception for a raw string that
happens to match a real element). A state distinguishable by rendered text (`booked` vs. `held`)
still gets a `verify:` bullet, pointed at the one real component's own anchor and filtered by
`text=`. A state with no rendered counterpart to check against — a boolean attribute like
`disabled` — has no mechanical check in this book's vocabulary at all; it stays a documented,
unverified fact on `states:` rather than a `verify:` bullet that cannot actually be satisfied.

`exclusive-with:` is a *claim* grounded in source (mutually-exclusive states, a variant switch),
not a way to silence a real same-screen collision. It is a DOM co-render assertion and nothing
more — it does not mean one control supersedes another.

A control rendered once per member of a collection carries `one-per:`, and its `name:` becomes
a template with `{…}` holes — see the
[repeat grammar](../bullet-grammar.md#repeated-controls-one-per--unique-by--variants). A child
nested under it (containment or `parent:`) inherits the family.

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type).

## Relationships

`parent:` nests it, `extends:` specializes another component, `exclusive-with:` names a
sibling.

A component that navigates carries **`leads-to:`** — that edge is what makes the destination
[`screen`](screen.md) reachable, and its absence is what `unreachable-screen` reports. It is a
relation key rather than a per-type one, so it appears in no type's key table and never raises
`unknown-bullet`; write it on the component a person activates to go somewhere.

## Minimal example

```bash
timeout 30 ostler scaffold component save-button --in docs/features/acme/gui/screens/link-editor.md
```

```markdown
### save-button

- role: button
- name: Save
- placement: width 0-20%, x 60-100%
- keyboard: reachable by Tab, activated by Enter or Space
- states: disabled until the URL field is valid
- code: web/src/LinkEditor.tsx::SaveButton
- verify: visible(locator="button[name=Save]", text="Save")
```

## Doctor codes it can trip

`missing-required-bullet`, `invalid-role`, `unnamed-interactive`, `missing-placement`,
`malformed-placement`, `ambiguous-locator`, `duplicate-bullet`, `undeclared-obligation`,
`weak-check`, `stale-defect`, `malformed-defect`, `unaddressable-selector`; with the repeat keys also `static-template`, `unproven-unique-name`, `malformed-template`,
`malformed-variants`. See [../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

Bullets state what this control is. If a reader could pick the wrong component — a legacy
widget and its replacement, each right in its own context — and still satisfy every claim on
it, that belongs in a [`concept`](concept.md), pointed at with `detail:`.
