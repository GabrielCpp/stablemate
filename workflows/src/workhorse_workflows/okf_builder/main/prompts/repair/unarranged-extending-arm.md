### `unarranged-extending-arm` — an arm leaning on arrangements it does not inherit

This `interaction`/`invocation` arm `extends:` a base case that declares arrangements — the
finding names it — and the arm declares none of its own. **Arrangements are not inherited**, so
nothing puts the arm's precondition in place and `qa compile-plan` withholds the whole arm as
`unarranged-interaction-precondition`.

That the identity carries over and the arrangement does not is deliberate, not an omission:
`extends:` inherits the base case's **control identity** — `on:`, `trigger:`, `role:`, `name:`,
`keyboard:` — because the two arms press the same control. An **arrangement exists to make a
`when:` true**, and the arm's `when:` is not the base case's:

- The arm **restates `when:`**, which is the usual reason to write one at all. Then the base's
  arrangement makes the base's condition true — that is, the exact state this arm says is false.
  Inheriting it would click submit on a valid form and assert the refusal it can never get.
- The arm **leaves `when:` silent** and inherits it. The condition is the same one, so the
  arrangement is the same one — but it has to be written down here, because an act is read from
  the bullets of the node that performs it.

**The repair is to declare this arm's own arrangement, for the state its own `when:` describes.**
Which key depends on who can establish that state — `arrange:` for an act the performer carries
out on this surface (`fill`, `click`, `press`, `select`), `fixture:` for something run beside it.
The `unarranged-interaction-precondition` fragment carries that choice in full.

```markdown
### refuse-new-widget
- when: `name` empty, or `quantity` missing or negative
- arrange: fill(locator="#name-field", value="")
- arrange: fill(locator="#quantity-field", value="-1")
- extends: [submit-new-widget](#submit-new-widget)
```

A scaffolded `- arrange:` or `- fixture:` with nothing after the colon does not clear this: the
finding reads the bullet's **value**, because an empty bullet says the template ran, not that
somebody wrote an arrangement.

If this arm genuinely needs no arrangement — its `when:` is about the world rather than the
surface and some `needs:`-reachable fixture already holds — name that fixture on the arm rather
than leaving the bullet blank, so the book says which arrangement it is relying on.
