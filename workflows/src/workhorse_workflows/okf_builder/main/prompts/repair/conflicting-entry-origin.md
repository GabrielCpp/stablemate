### `conflicting-entry-origin` — a surface's address is stated twice and the statements disagree

Two kinds of node state where a surface answers, and both are read at full-book scope: the
surface's `walkthrough: true` `server` node, through its `entry-url:`, and any `runbook`
whose `surfaces:` bullet links into the surface, through its own `entry-url:`. Only the
`scheme://host[:port]` is compared — a differing path is not this finding. This finding
means two of those sources name different origins for one surface.

A service has one address. There is no reading under which both bullets are true, so nothing
downstream picks between them: the surface resolves to no entry URL at all, and every
obligation on it is gapped with this same code rather than compiled against a guess. The
operator's `--base-url` does not rescue it either, and deliberately so — that flag answers a
book that states *no* address, and passing it here would paper over a book that states two.

This usually happens one of three ways, and the finding names the nodes so you can tell
which:

1. **A port moved and only one file was updated.** The service now serves on a different
   port, the `server` node was edited, and a runbook still names the old one — or the
   reverse. Fix the stale one.
2. **The two sources describe different environments.** One names the containerised address
   the stack actually binds (`http://127.0.0.1:18102`), the other a hostname that only
   resolves inside a compose network or on a deployed host. Both were true where they were
   written. Keep the address a QA walk started from this runbook can actually open, and let
   the other file describe its environment in prose under `## Steps` rather than in
   `entry-url:`.
3. **They are two services, not one.** If the origins differ because the runbook stands up
   something genuinely other than the `server` this surface documents, the fix is not an
   address at all: a surface is the first path component under `docs/features/`, so two
   services belong under two feature directories, and then each is one surface with one
   origin. Alternatively the runbook drops `surfaces:` — the key is optional — and stops
   claiming to be how this surface is exercised.

Do not repair this by deleting one of the `entry-url:` bullets without knowing which address
is right. Deleting the correct one leaves the surface resolving to the wrong host, which
compiles cleanly and then fails at run time against an app that is not the one under test —
a silent wrong answer in place of a reported one.
