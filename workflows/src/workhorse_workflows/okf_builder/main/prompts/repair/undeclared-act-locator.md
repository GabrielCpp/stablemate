### `undeclared-act-locator` — an act is performed on something the book never declared

The `locator=` inside an `arrange:` act — `fill(locator=…)`, `click(locator=…)` — is a
**reference into this book**, resolved exactly as a check's locator is. This one names
nothing the book declares: a raw CSS selector, a `role:name` string, or an anchor that does
not exist.

**A string is not a reference.** A hand-written selector states where the control sits in
today's DOM, which nothing in the book promises and nothing notices when it changes. The
control moves, the act arranges nothing, and the step it was arranging for fails later with
a message about the step rather than about the arrangement.

To repair each one:

1. Use the anchor of the `component` or `interaction` that declares the control:
   `- arrange: fill(locator="#name-field", value="Widget A")`, where `#name-field` is that
   node's anchor. The selector then lives on the node that owns the element.
2. **If nothing declares it, declare it.** An act operating an undocumented control is the
   book telling you a control is missing from it. Write the `component` node — that is the
   repair, not a rewritten string.
3. **A `screen` is not operable.** You do not fill or click a screen; name the control on it.

This is the sibling of `undeclared-check-locator`, one key over, and the difference is worth
keeping in mind while repairing: a check *observes* a control and an act *operates* one, so
the anchor you reach for is frequently not the same anchor.
