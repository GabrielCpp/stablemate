### `undeclared-check-locator` — a check points at something the book never declared

A `verify:` bullet's locator argument — the `selector=`/`target=` inside `visible(...)`,
`absent(...)` and their siblings — is a **reference into this book**, resolved the same way
a `trace` or a link is. This one names nothing the book declares: it is a raw CSS selector,
a `role:name` string, a `text=` fragment, or an anchor that does not exist.

**A string is not a reference.** A hand-written selector states where the element sits in
today's DOM, which nothing in the book promises and nothing notices when it changes. The
element moves, the selector rots, and the check either goes red against a correct build or —
far more often — silently matches nothing and passes.

To repair each one:

1. Find the `component` or `interaction` on the screen the check is about, and use its
   anchor: `- verify: visible(selector="#submit-button")` where `#submit-button` is the
   anchor of the declared component. The selector then lives in exactly one place, on the
   node that owns the element, and renaming it shows up here rather than in a silent pass.
2. **If nothing declares it, declare it.** A check pointing at an undocumented control is
   the book telling you a control is missing from it. Write the `component` node — that is
   the repair, not a rewritten string.
3. **A `screen` is deliberately not locatable.** A navigation does not verify "I am on
   screen X"; it names the component on the destination that says you arrived. If the
   locator is a screen, replace it with that component.

Do not "fix" this by deleting the check. An unobserved claim is a gap that gets reported;
a check aimed at nothing is a green that means nothing.
