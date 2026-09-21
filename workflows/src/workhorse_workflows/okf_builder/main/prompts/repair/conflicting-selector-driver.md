### `conflicting-selector-driver` — a component's `selector:` is written for the wrong surface driver

A `component`'s `selector:` can be spelled two ways: ordinary CSS (`#name`, `.field`,
`tag[role="..."]`), or a self-identifying `scheme=value` address (`testID=name-input`). Both
are real, addressable forms — `unaddressable-selector` is the check that rejects a string
that is neither — but only one of them is the form the surface's own driver can actually
query. A browser drives a `web` surface, and it queries the DOM: it has no way to resolve a
`testID=` address. Maestro drives a `mobile` surface, and it resolves a `scheme=value`
address or the control's visible text: it does not run a CSS engine, so an id, a class, an
attribute predicate, a combinator, or a `tag.class`/`tag#id` compound written there addresses
nothing. This finding means a `selector:` parsed fine as an address, just not the one its
surface's driver reads — the value is not malformed, it is aimed at the wrong platform.

This usually happens when a component is copied from one platform's screen to the other's —
a web screen scaffolded from its mobile counterpart, or the reverse — and the `selector:`
line comes along unchanged along with the rest of the bullets that *are* still correct on
both.

To repair it, look at which side is actually wrong:

1. **The component genuinely lives on this surface**, and the selector was carried over from
   the other platform's version of the same screen. Rewrite it in the representation this
   surface's driver reads: CSS for `web`, a `scheme=value` address (or the control's visible
   text) for `mobile`.
2. **The surface's `driver:` itself is wrong** — the runbook the engine resolves the driver
   from states the wrong one for what it actually stands up. A surface's driver is the first
   non-empty `driver:` among the runbooks whose `surfaces:` names it, ranked in the order
   `web`, `mobile`, `http`, `cli`, `artifact`, `iac`, `none` (a runbook with no or an unknown
   driver ranks last) and tie-broken by node id — so the runbook to read is the highest-ranked
   one covering this surface, and several runbooks covering it with different drivers is
   normal, not a defect. Fix `driver:` on that runbook instead; once it names the platform
   this surface really is, the selector this finding holds to the wrong platform's grammar may
   turn out to have been correct all along.
3. **The surface renders nothing to query at all** — `cli`, `iac`, `artifact`, or `none` —
   and still carries a `component`/`screen` node with a `selector:`. No driver here ever
   addresses a control, so the fix is to remove the `component` node (and the `screen` it sits
   under, if nothing else on it is real), not to reword the selector into some other shape. (An
   `http` surface is not in this group: one surface can legitimately host an `http`-driven API
   runbook alongside the `web`-rendered screens it serves, so `http` is held to the same CSS
   grammar as `web` — see option 1 above.)

Do not repair this by deleting the `selector:` bullet to make the finding go away — a
`component` with `role:`/`name:` but no `selector:` still needs one wherever a check's
`verify: visible(locator=...)` or the census depends on it, and this finding is telling you
which shape to write, not that the bullet should not exist. Do not guess at a representation
either: a `scheme=value` selector invented rather than read off the source names a prop that
may not exist in the code at all, which trades this finding for a check that fails against a
live app for a reason that has nothing to do with the product.
