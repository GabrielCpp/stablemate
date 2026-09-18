### `unknown-driver` — `driver:` is not a value the vocabulary declares

A runbook's `driver:` is a closed vocabulary of seven values — `web` (a browser against a
screen), `mobile` (a native/mobile client against a screen), `http` (a direct client against
a server's API), `cli` (a command-line invocation against a `cli` node), `artifact` (a build
that produces something rather than performing against a surface), `iac` (infrastructure
provisioning, nothing in this vocabulary represents what it performs against), and `none`
(the book stating outright that nothing performs against these surfaces). This finding means
the value written is not one of the seven — a typo (`htttp`, `browser`) or a value from
some other vocabulary entirely. Case is not the defect: every reader lowercases the value
before it looks it up, so `Web` is `web`.

To repair it, read what the runbook's `## Steps` actually bring up and what its `surfaces:`
resolve to, then pick the one value of the seven that names what actually carries out the
steps against those surfaces — not the value closest in spelling to what is there now. A
`surfaces:` list of `screen` nodes reached through a browser is `web`; the same reached
through a native client is `mobile`; a `surfaces:` list of `server` nodes hit directly (no
browser, no native client in between) is `http`; a `surfaces:` list of a `cli` node is
`cli`. If `surfaces:` is empty or absent, read the steps' `run:`/`health:` commands for what
they actually launch and exercise.

Do not pick a value just to make this finding go away. An unrecognized spelling and a wrong
spelling fail differently once this finding is fixed: get the family wrong — `web` where the
steps really drive a `cli` — and the runbook now passes `unknown-driver` while dispatching
the wrong kind of QA walk at bring-up time (`no-drivable-surface` may then catch the
mismatch against `surfaces:`, but only if `surfaces:` is populated; a `driver:` with no
`surfaces:` at all sails through silently) and grading it against the wrong route grammar
(`routes.ROUTE_GRAMMAR`) besides. A wrong-but-recognized value is a second defect layered on
top of the one this finding reports, not a fix for it.
