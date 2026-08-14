### `compound-normative-bullet` — one bullet carrying several requirements

A normative bullet mints exactly **one** obligation and is proved by **one** scenario. A bullet that
carries a paragraph — the success effect *and* the error case *and* what is persisted — is several
requirements wearing one id: the scenario covering it proves whichever clause the planner read, and
the rest is documented, claimed as covered, and never tested.

**Split by repeating the key**, one clause per bullet, each with its own `verify:`:

```markdown
# before — one id over three requirements
- does: creates the hold, emails the payer, and returns 409 when the seat is already held

# after — three obligations, three observations
- does: creates a hold on the seat under the caller's name
- verify: created(subject="the caller's hold on that seat")
- emits: a payer notification for the created hold
- verify: emitted(event="hold.created", count=1)
- raises: 409 when the seat is already held
- verify: http_status(409, title="Seat Held")
```

You are reading the source right now, so you are the one who can tell which clauses are genuinely
separate — the success effect, each error case, what is persisted, what is emitted. Split there.

Two ways to get this wrong:

- **Splitting on punctuation.** A comma is not a requirement boundary. "creates a hold, under the
  caller's name" is one claim with a qualifier; cutting it invents an obligation nobody has to meet
  and a check nobody can write.
- **Collapsing instead of splitting.** Shortening the bullet until it stops tripping the length rule
  deletes the clauses rather than promoting them. That is the forbidden move: the count comes out
  even and the book says less.

Carry each clause's existing `verify:` to the bullet it actually observes, and write one for any
clause that ends up with none — a split that leaves new obligations unbound just trades this finding
for `undeclared-obligation` next round.
