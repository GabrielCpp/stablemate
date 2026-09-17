### `unarranged-journey` — the journey never says what world it starts in

A flow's claims are about the world its `steps:` left behind, and the world its steps left is
the world they started in plus the walk. This flow says nothing about the world it starts in:
it carries no `fixture:` bullet, and it does not say it needs none. So the compiler has no
scenario it could honestly emit — a walk run against whatever the scenario before it happened
to leave would assert the flow's `end:` state against accidental state, and the red it produced
would be evidence about the run order, not about the app.

The repair is one bullet on the flow node, and which one is a question about the journey:

- **The journey needs a world arranged.** Add `- fixture: <name> [args] — <what state it leaves
  behind>`, naming a fixture node under `docs/features/<surface>/fixtures/<name>.md` (or an
  existing `qa: {fixtures:}` entry). A `fixture:` on the flow node is ambient: it arranges once,
  before the first step, which is what a journey's starting world is.
- **The journey holds in whatever world it finds.** Say so, with the reason:
  `- fixture: none, because <why the claims do not depend on prior state>`. A good reason names
  what makes it true — the first step creates everything the last step observes, the route reads
  a store it is documented against empty, the screen's claim is about chrome that no data
  changes.

**A bare `- fixture:` or `- fixture: none` is not the second answer.** An empty bullet is the
undecided case — exactly the state this finding reports — and `none` with no reason is a blank
left blank. The reason is what makes "nothing is needed here" a claim a reader can check rather
than a stub nobody came back to.

Do not repair this by deleting the flow's `verify:`, and do not move the arrangement onto one of
the step nodes. A step's own `fixture:` arranges that step's own claims; the journey's claims are
about the end of the whole walk, and only the flow node can say what the walk began in.
