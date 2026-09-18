### `unparsable-bullet-value` — a bullet's value does not parse as the kind its key declares

Some bullet keys declare a `value_kind`: `screen.route`/`endpoint.path` (`route`), `screen.entry`
(`door`), `server.entry-url`/`runbook.entry-url` (`url`), `endpoint.method` (`http-method`). A
role — `required:`, `locator:`, whatever else the key is *for* — says nothing about what the
value may *say*. Declaring a key required only checks that it is present; it does not stop an
author from writing prose, a typo, or a placeholder into it, and nothing short of parsing the
value the way its one real consumer parses it will catch that. This code is what parsing catches.

Fix the bullet by writing a value of the kind its message names:

```markdown
- method: POST
- path: /widgets
```

```markdown
- entry: /login
```

**A prose `entry:` is not required — delete it, or write the real route.** `entry:` is optional:
it exists to say *this screen is reached from outside in-app navigation*, and stating that
exempts the screen from the reachability check. Prose like `entry: no; it is reached from
dashboard` looks like it is answering that question, but `screen.md` is explicit that a value here
is a claim the reachability check can act on, not a note to a future reader — "documents nothing
the check can use." If the screen really is reached in-app, the fix is to delete the bullet, not
to write around it: an unwritten `entry:` lets the reachability walk find the screen the way a
user would; a prose one silently claims exemption from that walk while asserting nothing the walk
can verify.

A parameterised route is **not** this defect: `/policies/{id}` and `/links/:id/edit` parse fine as
`route`-kind values — they name a family of pages, which is a legal thing for `screen.route`/
`endpoint.path` to say. Do not "fix" one by inventing a literal id.

**This is not `invalid-http-method`.** That code fires later, when a plan tries to *compile* a
`method:` that never parsed — it is raised from a `Gap`, against one compiled plan, and it exists
so the compiler withholds the call rather than emitting one no verb backs. This code fires earlier
and unconditionally: it is a statement about the book alone, true whether or not any scenario ever
compiles it, and it is what makes `invalid-http-method` mostly unreachable in a book this check
already runs against — fix the value here and there is nothing left for that gap to find.

**This is not `unidentifiable-screen`.** That code, too, is a compiled-plan consequence: a
scenario that ended on a screen whose route no URL comparison could use. This code is the reason a
scenario is less likely to reach that state in the first place — a `screen.route` this check has
already accepted as `route`-kind is a route a browser's URL can be compared against, literal or
parameterised; `unidentifiable-screen` is for the walk-time case where a parameterised hole was
never bound by the scenario that reached it.

**This is not `missing-required-bullet`.** An empty or absent value is that code's, not this one's
— a value_kind check runs only against a value an author actually wrote; skipping empty values is
deliberate, so this code never doubles up with the one that owns "nobody wrote it down."
