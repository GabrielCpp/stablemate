### `uneven-claim-coverage` — one claim carries two checks, its sibling carries none

`registry.attributed_checks` credits each `verify:` to the **nearest normative bullet above it**.
This node has one claim with two or more `verify:` bullets bound to it and another normative claim
— on the same node — with none. That is not `undeclared-obligation`'s all-or-nothing silence; the
node did write a check, it just landed under the wrong claim.

The usual cause is a check written for a *later* bullet, placed before it was written, or a bullet
inserted between an existing claim and the check that was meant for it:

```markdown
# misbound — both checks land on `does:`, `raises:` gets neither
- does: publishes the revision under a new id
- verify: created(subject="the published revision")
- verify: http_status(code=409, title="Conflict")
- raises: `ManifestConflict` when the revision moved under it

# bound — each check sits directly under the claim it observes
- does: publishes the revision under a new id
- verify: created(subject="the published revision")
- raises: `ManifestConflict` when the revision moved under it
- verify: http_status(code=409, title="Conflict")
```

The finding names the over-covered claim (`ref`) and the under-covered one (in the message). Move
the check that actually observes the named claim down to sit directly beneath it — do not delete
either check, and do not add a new one: the checks already exist, they are bound to the wrong
bullet. If, after moving it, one of the two checks turns out to genuinely observe the first claim
twice (two assertions about the same outcome), leave both under it — a node may declare more than
one check per claim on purpose; the defect is a claim left with **none**, not a claim with several.

Read `code:` to confirm which claim each check is actually testing before you move it — the
bullet text alone will not always tell you which was misfiled.
