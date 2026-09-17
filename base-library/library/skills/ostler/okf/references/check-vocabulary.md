# The check vocabulary

The sixteen named checks a `verify:` bullet may call, their signatures, and — the part that
matters when judging whether a check earns its bullet — **the defect each one excludes**. A check
that excludes no plausible defect is a rubber stamp, and `doctor` refuses it as `weak-check`.
Companion to [`../SKILL.md`](../SKILL.md) and to [bullet-grammar.md](bullet-grammar.md), which
says where the bullet goes and what it binds to.

`ostler checks` and `ostler checks <name> --json` print this **live** from
`ostler/ostler/checks.py`. The tool is the authority; run it before writing a call you have not
written before, not after `doctor` refuses one.

## How to read a signature

- `name*` — required argument.
- `one of …` — at least one of the listed arguments must be present. `required` cannot express
  this: each is optional alone, and it is the *choice* that is mandatory. Without it, a check can
  be spelled so nothing it observes can come out false.
- Types are `str`, `int`, `bool`, `scalar`, `str[]`.
- Arguments marked *(path)* are paths into the observed document, not free prose. Both resolvers
  strip a leading `$` root token, so `$.policy.id` and `policy.id` name the same field.
- Arguments marked *(locator)* name a **component the book declares** — the `- selector:` of a
  `component` or `interaction`, by its anchor. Also not free prose, and for the same reason one
  level up: see below.

Arguments are parsed as **literals only**, via `ast` (`checks.py:265-310`) — no expressions, no
names, no interpolation. A `verify:` whose value is a test path is not a parse failure to fix in
place: it is a category error, and `parse_check` redirects it to `tests:`.

## The vocabulary

### `http_status(code*=<int>, title=<str>, method=<str>, path=<str>)`
Excludes a branch that returns the right shape under the wrong status, and an error response
distinguished from its siblings only by a body nobody read.

**A request is identified by its method and its path, not its path alone.** On the `web`
driver, `path=` selects which of the page's own exchanges a `verify:` row is about — see
"Selecting an exchange on a page" below — and a page that creates a thing and then lists it
POSTs and GETs the same route, so a path-only selector names both and neither. `method=` is
not `required=True`: it follows `path=`'s own precedent, which has always been enforced by
`compile_plan` refusing an undetermined selection (`uncompilable-claim`) rather than by a
grammar-level requirement, because a book whose page only ever hits a route once needs
neither argument to disambiguate anything. Declare `method=` wherever the same route is hit
more than once in one scenario; `compile_plan` gaps rather than guessing when it is missing
and needed.

### `json_path(path*=<str> (path), equals=<scalar>, matches=<str>, absent=<bool>) — one of equals, matches, absent`
Excludes a field asserted by presence rather than value, which passes on the default the defect
also produces.

### `unchanged(subject*=<str>, except_fields=<str[]>)`
Excludes collateral damage outside the field under test — the defect a diff that masks the whole
object before comparing cannot see.

### `keys_unchanged(subject*=<str>)`
Excludes a move implemented as a copy: every object compared individually matches, and only the
key inventory shows the old one is still there.

### `count(subject*=<str>, equals*=<int>)`
Excludes an operation that produced the expected item *and* extras nobody counted.

### `absent(subject*=<str>)`
Excludes a delete that hid the thing from one surface and left it readable on another.

### `created(subject*=<str>)`
Excludes a thing that was already there reported as created. A presence check run only afterwards
passes identically on a no-op, so the absence *before* the action is part of the observation
rather than an assumption about it.

### `removed(subject*=<str>)`
Excludes a delete asserted only by absence afterwards, which passes identically when the subject
was never there — the presence before the action is what makes the disappearance attributable to
it.

### `visible(locator*=<str> (locator), text=<str>)`
Excludes an element present in the tree but not on the screen, and the right widget showing the
wrong content.

### `actionable(locator*=<str> (locator))`
Excludes a control the book says the user can use and the product has disabled — which
`visible` passes, because a greyed-out button is on the screen and reads the right label.

### `inert(locator*=<str> (locator))`
Excludes a control the product leaves usable after the state that should have closed it, which
no assertion about what is on the screen can see: the defect is that the element still accepts
the action, not that it is still drawn. This is the positive form of a `- states: disabled …`
bullet — write the claim about what the user can do, not about the attribute one rendering
happens to spell it with. `disabled` is HTML's word for it; a mobile surface says
`enabled=false` and an API says nothing at all, so a check named after the attribute would be
compilable by one driver and meaningless to the rest.

### `focusable(locator*=<str> (locator), activates=<str>)`
Excludes a control reachable only by pointer, which `visible`/`actionable` both pass because
it is on the screen and enabled — and, when `activates` is given, a control that receives
focus but does not fire on the key the book names, which no assertion about what is drawn can
see: the defect is in what the keypress does, not in what is on the screen.

### `persists(subject*=<str>)`
Excludes a write observed only through the same session that made it, which cannot tell a commit
from a cache.

### `emitted(event*=<str>, count=<int>)`
Excludes an effect asserted at its source instead of at its subscriber, and an at-most-once
effect fired twice.

### `omits(subject*=<str> (path), text=<str>, matches=<str>) — one of text, matches`
Excludes a value the response was never supposed to carry — a refusal quoting the credential it
rejected, an error echoing an internal path. Every other check in this vocabulary passes over
this, because they all assert what the subject *does* hold and a clause about what it may **not**
hold has no positive form.

### `exit_status(code*=<int>)`
Excludes a command that failed, or succeeded for the wrong reason, where the plan only read its
output — a tool result asserted by what it printed passes identically when the process printed it
on the way to a non-zero exit.

### `conflict_on_stale(subject*=<str>, token=<str>)`
Excludes an unconditional overwrite standing in for compare-and-swap — a write followed by a read
cannot tell them apart, only a stale write refused can.

## Selecting an exchange on a page

`qa.http`'s scenarios have exactly one response, because the scenario made exactly one call.
A page scenario on the `web` driver has however many the page chose to make, so the operand of
an `http_status`/`json_path` row observing a response or its body is a *selection*, not "the"
response — and the book is what writes the selector down. `http_status`'s `method=`/`path=`
are read once per obligation and shared by every row in it (`json_path`'s own `path=` is a body
JSON path and never selects an exchange, even though it inherits this same ambiguity through the
shared selector). An obligation whose `http_status` rows name two different `(method, path)`
pairs is not one exchange, and `compile_plan` reports it as `uncompilable-claim` rather than
guessing which response the rest of the obligation means.

## A locator names a declared component

A `locator` argument is a reference into the book, not a string the driver happens to accept.
Written as free text it type-checks, runs, and goes green against an element the book has never
heard of — so renaming that element breaks the run and leaves the book undisturbed, which puts
the staleness on the wrong artifact.

Measured across the paddock fixtures: **26 of 31 distinct check locators name nothing any
`- selector:` declares**, written in three incompatible dialects that had accumulated because
nothing ever read them —

```
#new-widget-form              a CSS id no component declares
button:Save policy            a role:name form
text=End date must be after the start date.
```

None of these is wrong about the app. All of them are unresolvable, which is the same defect the
`link` flag exists to prevent one bullet over. A locator therefore names the declared component
by its anchor, and the selector lives in exactly one place — the component that declares it:

```markdown
### widget-table
- selector: table[aria-label="Widgets on hand"]
...
- verify: visible(locator="#widget-table")
```

`#widget-table` there is the node anchor `ostler` already resolves links by — the same
`path#anchor` identity `trace` walks — and *not* a CSS id that happens to start with `#`. A
component in another document is named the long way, `screens/widget-list.md#widget-table`.

`doctor` reports a locator resolving to no declared component as `undeclared-check-locator`
(error), and `compile_plan` gaps rather than emitting against it — undetermined, so no executable
code.

Only a `component` or an `interaction` may be named: a `screen` is the page, and `visible` has
nothing to point at on it. A navigation interaction is the common case that gets this wrong, and
the fix is not to name the destination screen but to name the one thing on it that says you
arrived — its heading, its record summary — and declare that component if the book has not:

```markdown
- does: navigates to [the policy's detail screen](policy-detail.md)
- verify: visible(locator="policy-detail.md#policy-heading", text="Policy PN-1001")
```

## Why the vocabulary is small

Every entry has to name a defect class that a plausible *weaker* assertion lets through, and
every entry costs a harness callable that has to behave identically under every driver. Growing
it is a deliberate act, not a convenience. If no check fits, the claim is usually the thing that
needs splitting — see [bullet-grammar.md](bullet-grammar.md).

## The lifecycle pair

`created` and `removed` are the two checks `doctor` reaches for by name
(`LIFECYCLE_CHECKS`, `doctor.py:856`). When a normative bullet states a lifecycle change and the
declared checks read only the state *afterwards*, that is `unstated-precondition` (warn): the
after-state is the same state a no-op leaves when the subject was already there.

## The act vocabulary — the other closed list

`verify:` says what observing a claim looks like. `arrange:` says how to reach the state where
observing it is possible, by an act the **performer of the step** carries out on the node's own
surface. It is a separate, smaller vocabulary in `ostler/ostler/acts.py`, parsed by the same
call grammar as a check and refused against its own names:

| Act | Establishes | Drivers |
| --- | --- | --- |
| `fill(locator*, value*)` | a text control holds a stated value | web, mobile |
| `click(locator*)` | a control has been operated once — an expander opened, a row selected | web, mobile |
| `press(locator*, key*)` | a real keypress has reached a control (focus order, a key-handled shortcut) | web, mobile |
| `select(locator*, option*)` | a chooser holds a stated option | web |

Every argument is a `str`: an act's arguments are what the performer types or points at, so
`fill(locator="#quantity-field", value="3")` and never `value=3`. `locator=` is a reference into
the book, the same rule and the same reason as a check's — a raw selector is
`undeclared-act-locator`.

**`arrange:` is not `fixture:`.** A fixture arranges the world *beside* the surface — a seeded
row, a signed-in session — and is right whenever something other than the performer can
establish the state. An act is for the state only the performer can reach: a `when:` over what
the user typed is true only once someone has typed. A bare name under `arrange:` is a fixture
written under the wrong key, and `unparsed-act` relocates it rather than asking for a
performance that does not exist.

**`select` is web-only on purpose.** A `<select>` is a control the platform renders; a mobile
chooser is a screen of its own, and arranging one there is the steps that reach it, not one act.
A `mobile` target facing `arrange: select(…)` gaps rather than emitting — which is the driver
list doing its job, not a hole in the vocabulary.
