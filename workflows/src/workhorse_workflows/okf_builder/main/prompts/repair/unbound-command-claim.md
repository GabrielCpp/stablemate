### `unbound-command-claim` — this claim checks a command that names no concrete invocation

`usage:`/`flags:`/`args:` on a `command` node are the invocation's **prose synopsis** — every
way to call it, not any one of them: `shortener create <url> [--slug SLUG]` still has `<url>`
in it. `run:` is the concrete counterpart, and it is what the QA compiler needs to turn a
`exits:`/`verify:` claim into `qa.tool(...).run(...)`: one literal invocation per value, an
*act* (`ostler.acts`'s `invoke`) rather than a fixture name.

The finding names the claim (`ref`) that has a check and no `run:` bound to it. Binding is
**document order**, the same rule `verify:`/`fixture:`/`capture:` already bind by: a `run:`
sits directly beneath the `exits:`/`verify:` pair it arranges, above the next claim.

```markdown
# misbound — nothing observes this exit code
- exits: 0 on success
- verify: exit_status(code=0)
- exits: 2 on a taken slug
- verify: exit_status(code=2)

# bound — each claim carries the literal invocation that proves it
- exits: 0 on success
- run: invoke(argv=["shortener", "create", "https://example.com"])
- verify: exit_status(code=0)
- exits: 2 on a taken slug
- run: invoke(argv=["shortener", "create", "https://example.com", "--slug", "taken"])
- verify: exit_status(code=2)
```

Read `code:`/`tests:` (and, when present, the command's own `usage:`/`flags:`/`args:` prose) to
find the real argv this claim exercises — do not invent flags or values the book never states.
Each `argv` element is one literal token a shell would pass unchanged, the same reasoning
`body`'s `value` follows for a request field: a person types `"3"`, and so does a command line.

This is the book-side twin of `uncompilable-claim`: a `command` obligation with no `run:`
compiles to nothing (the QA compiler gaps it as `uncompilable-claim` rather than emit a
scenario with no action). Adding the `run:` here is what turns that compiled gap into a real
scenario, with no runbook and no driver bullet required — `command`'s driver is always the
subprocess performer `ostler.acts.CLI` names.
