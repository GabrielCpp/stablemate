### `undeclared-entry-url` — this surface states no address a QA plan can open

`ostler qa compile-plan` reads each target's `base_url` off the book, per surface, rather
than from one CLI flag applied to every surface alike — a `server` node's `entry-url:`
first, or failing that, a `runbook` node whose `surfaces:` bullet points into this
surface, via that runbook's own `entry-url:`. This obligation's surface states neither, so
the compiler cannot resolve where a scenario should even connect, and drops the obligation
as a gap instead of guessing.

To repair it, find the surface's own [`server`](server.md) node — the one describing the
process this obligation's endpoint or screen actually runs inside — and state where it
listens:

```markdown
- entry-url: http://localhost:8000
```

If no `server` node exists for this surface yet, or the address is only known at the
bring-up layer (a compose port, a container's published port), state it on the
[`runbook`](runbook.md) that stands the surface up instead, alongside its `surfaces:`
bullet:

```markdown
- surfaces: [web-app](../http/web-app.md)
- entry-url: http://localhost:18102
```

**Read the actual bring-up, don't invent a port.** The value has to be the address the
service really answers on locally — the compose file, the `launch:`/`run:` command, or the
runbook's own `code:` citation is where that number lives. A guessed port compiles clean
and then every scenario against it fails to connect, which is a worse failure than the gap
this finding already is.

If the surface's `server` and its describing `runbook` disagree on the address, that is a
different, earlier defect — `ostler qa context` raises it before this finding is ever
produced. Fix the stale one of the two rather than picking either at random.
