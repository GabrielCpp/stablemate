### `unarranged-scenario` — nothing says what world the claims are observed in

An `endpoint`'s or a `command`'s checks are performed inside a scenario, and the http and cli
builders compile **one scenario per book file**. That scenario's world is whatever the file's
`fixture:` bullets arrange. This file arranges nothing and does not say it needs nothing, so
the compiler has no scenario it could honestly emit — the claims would be observed against
whatever the scenario before them happened to leave, and the red that produced would be
evidence about the run order, not about the app.

The repair is one bullet, and which one is a question about the claims:

- **The claims need a world arranged.** Add `- fixture: <name> [args] — <what state it leaves
  behind>` to the node whose claim depends on that state, naming a fixture node under
  `docs/features/<surface>/fixtures/<name>.md` (or an existing `qa: {fixtures:}` entry). The
  file's fixtures are arranged once, before the scenario's first call, so two nodes documented
  against the same seeded state name the same fixture rather than each seeding its own.
- **The claims hold in whatever world the scenario finds.** Say so, with the reason:
  `- fixture: none, because <why the claims do not depend on prior state>`. A good reason names
  what makes it true — the route lists whatever is there and the check only reads the envelope,
  the command's claim is about its own usage text, the endpoint rejects the request before it
  reads any store.

**A bare `- fixture:` or `- fixture: none` is not the second answer.** An empty bullet is the
undecided case — exactly the state this finding reports — and `none` with no reason is a blank
left blank.

One bullet answers for the whole file, because the file is the scenario: a `fixture:` on any of
its nodes arranges the world all of them are observed in, and a `fixture: none, because …` on
any of them states that the file's claims need none. Put it on the node the fact is true of,
not on whichever node the finding happened to name.

Do not repair this by deleting the node's `verify:`. A claim nobody checks is not a claim that
holds in any world; it is a claim the book is no longer held to.

`unarranged-journey` is this same rule on a `flow`, where the unit is the one flow node rather
than the file.
