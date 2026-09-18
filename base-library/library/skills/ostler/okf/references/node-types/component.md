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
| `selector` | no | a locator, when role+name cannot address it — CSS, or a `scheme=value` self-identifying address |
| `role` | **yes** | **mints an obligation** — the ARIA role |
| `name` | **yes** | **mints an obligation** — the accessible name |
| `placement` | no | viewport bands, e.g. `width 60-100%, x 0-20%` |
| `keyboard` | no | **mints an obligation** — how it is reached and operated |
| `extends` | no | link — the component this specializes |
| `same-as` | no | link, multi-valued — another node documenting this same component |
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

**The pair is one address, not two claims.** `getByRole(role, {name})` is a single query built
from both bullets, and the compiler never emits a role without a name — a role on its own
resolves to more than one element and Playwright's strict mode raises. So no check in the
vocabulary can observe `role:` apart from `name:`, and a `verify:` under a component discharges
the pair together. Do not add a second check to "cover" the role: the two bullets are an address,
nothing counts them as claims to be evenly covered, and a check written to satisfy that intuition
asserts the same query twice. When `name:` is `none` the address falls through to `selector:`,
and the by-role requirement relaxes with it.

**`name:` is an observation of the accessibility tree, not a transcription of the text on the
screen** — and for most roles those are different strings. An accessible name comes from an
author label (`aria-label`, `aria-labelledby`, a `<label for>`, and for a `table` its
`<caption>`); only a **name-from-content** role takes its name from its own text. That set is
`button`, `cell`, `checkbox`, `columnheader`, `gridcell`, `heading`, `link`, `menuitem`,
`menuitemcheckbox`, `menuitemradio`, `option`, `radio`, `row`, `rowheader`, `switch`, `tab`,
`tooltip`, `treeitem` — and nothing else. A `status`, `alert`, `region`, `paragraph`, `table`,
`form`, `textbox`, `spinbutton` or `combobox` with no author label has **no** accessible name,
so its `name:` is `none`.

Writing the announced wording into `name:` on such a node makes a claim no reading of the
accessibility tree can check, and the compiler turns it into a locator that matches nothing:
against a live stack, `getByRole("status", name="No widgets are on file yet.")` resolves to 0
elements while the element is painted and visible. The wording is still a real claim — it moves
to the one check that can observe it, `verify: visible(locator=..., text="...")`, beside a
`name: none`.

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
not just an unlucky one.

Off the web, there is a third spelling: a self-identifying `scheme=value` selector, e.g.
`selector: testID=widget-table` for a React Native control. It names its own grammar in the
string itself, so `ostler doctor` can tell it apart from a bare CSS string with no lookup of the
node's `driver:` — see `is_addressable` in `ostler/vet/placement.py`. The recognized schemes are
listed there (`testID`, the prop React Native source writes and the representation Maestro's
`id:` selector resolves against); an unrecognized scheme is rejected rather than guessed at, the
same as any other unaddressable string. Neither reader above compiles it to a live locator: the
census has no web render to scan, and this tree has no Maestro/mobile driver yet, so a
`verify:` against a `testID=` selector compiles to a gap (`uncompilable-claim`) instead of code —
an honest "documented, not yet runnable" rather than a locator that silently matches nothing. A
control whose identity depends on a piece of state (`booked`, not
merely `disabled`) belongs on `states:`, not folded into `selector:` on a second component node
that exists only to carry it. That does not mean a raw-CSS `locator=` bypasses the census: a
check's `locator=` is a reference into the book, not a live selector — it must resolve to a
`#component` or `#interaction` anchor the book declares (`ostler doctor`'s
`undeclared-check-locator` enforces this unconditionally, with no exception for a raw string that
happens to match a real element). A state distinguishable by rendered text (`booked` vs. `held`)
still gets a `verify:` bullet, pointed at the one real component's own anchor and filtered by
`text=`. A state with no rendered counterpart — a control the product will not let the user act on —
is checked by `inert(locator="#this-component")`, and its opposite by `actionable(...)`. Both
ask what the user can do rather than what one rendering spells it with, which is why the
vocabulary has them and not an `attribute(...)`: `disabled` is HTML's word, a mobile surface
says `enabled=false`, and a check named after either would be compilable by one driver and
meaningless to the rest. A `states:` bullet that says the control cannot be used and has no
such check anywhere in the book is `ostler doctor`'s `unchecked-availability-state` — leaving
it as a documented, unverified fact is no longer the remedy, because `visible(...)` passes on
a greyed-out button and reports that pass as coverage.

`exclusive-with:` is a *claim* grounded in source (mutually-exclusive states, a variant switch),
not a way to silence a real same-screen collision. It is a DOM co-render assertion and nothing
more — it does not mean one control supersedes another.

`same-as:` is different from all three of `extends:`, `parent:` and `exclusive-with:`: it does not
specialize, nest, or rule out co-rendering — it says this component and the one it names are the
*same* documented control, written more than once (a shared nav region reachable from two
screens, say). It is symmetric and must be declared on both sides. Its consumer is the QA obligation packet: a change to the cited symbol maps to every node that cites it, and without `same-as:` one thing written in three places reads as three things and trips the container fan-out demotion that exists to catch sprawl. `same-as:` is the declared fact that collapses them back into one family.

It deliberately has no effect on `competing-implementations`. That check judges only same-file groups, and two sections of one file claiming to be the same documented thing would be the defect, not the exemption.

A control rendered once per member of a collection carries `one-per:`, and its `name:` becomes
a template with `{…}` holes — see the
[repeat grammar](../bullet-grammar.md#repeated-controls-one-per--unique-by--variants). A child
nested under it (containment or `parent:`) inherits the family.

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type).

## Relationships

`parent:` nests it, `extends:` specializes another component, `exclusive-with:` names a
sibling, `same-as:` names another node documenting this same component.

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
`weak-check`, `stale-defect`, `malformed-defect`, `unaddressable-selector`,
`one-way-same-as` if `same-as:` is used; with the repeat keys also `static-template`, `unproven-unique-name`, `malformed-template`,
`malformed-variants`. See [../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

Bullets state what this control is. If a reader could pick the wrong component — a legacy
widget and its replacement, each right in its own context — and still satisfy every claim on
it, that belongs in a [`concept`](concept.md), pointed at with `detail:`.
