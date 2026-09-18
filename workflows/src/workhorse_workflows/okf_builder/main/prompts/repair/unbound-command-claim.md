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

# bound — each claim carries the literal argument list that proves it
- exits: 0 on success
- run: invoke(argv=["create", "https://example.com"])
- verify: exit_status(code=0)
- exits: 2 on a taken slug
- run: invoke(argv=["create", "https://example.com", "--slug", "taken"])
- verify: exit_status(code=2)
```

`argv` carries only the **arguments** — never the binary. The executable this `run:` invokes
is the owning `cli` file node's own `binary:` bullet, stated once at the top of the file;
repeating it as `argv[0]` here would be the same fact stated twice, free to drift out of sync
with the `binary:` bullet the moment either one is edited alone. If the owning `cli` node
declares no `binary:` value, the claim stays uncompilable no matter how complete its `run:`
is — fix that by adding `binary:` to the file, not by naming the executable in `argv`.

Read `code:`/`tests:` (and, when present, the command's own `usage:`/`flags:`/`args:` prose) to
find the real arguments this claim exercises — do not invent flags or values the book never
states. Each `argv` element is one literal token a shell would pass unchanged, the same
reasoning `body`'s `value` follows for a request field: a person types `"3"`, and so does a
command line.

This is the book-side twin of `uncompilable-claim`: a `command` obligation with no `run:`
compiles to nothing (the QA compiler gaps it as `uncompilable-claim` rather than emit a
scenario with no action). Adding the `run:` here is what turns that compiled gap into a real
scenario, with no runbook and no driver bullet required — `command`'s driver is always the
subprocess performer `ostler.acts.CLI` names.
