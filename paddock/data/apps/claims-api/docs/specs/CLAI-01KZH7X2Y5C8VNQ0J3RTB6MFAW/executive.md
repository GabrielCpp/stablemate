---
type: spec.executive
---

# Executive Summary: File a Claim and Put It on the Books

Adds the write path end to end: the OpenAPI contract and the server generated from it, the JSON
ledger, the submission endpoint, the reset that makes the ledger drivable more than once, and the
bearer verification that stands in front of all of them.

The criterion worth reading twice is that protection is not a property of any handler. `openapi.yml`
marks an operation as secured, the generated router puts the bearer scope into the request context
for exactly those operations, and the middleware verifies whatever it finds there. `/healthz` is
open because the document says `security: []`, not because a handler checks a path — so the
document is the thing to read when asking what is protected, and an operation it forgets to secure
is served without an identity while all of its own rules still pass.

One service (`app/api`, Go) and no client at all. Identity comes from a Firebase Auth emulator
running beside it, which is why there is no credential anywhere in the tree. See `plan.md` for the
implementation shape and `plan-context.json` for the machine-readable service manifest.
