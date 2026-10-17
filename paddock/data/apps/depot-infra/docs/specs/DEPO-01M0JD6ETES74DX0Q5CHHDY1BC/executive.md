---
type: spec.executive
---

# Executive Summary: One Deploy Identity, One Grant, and a Nightly Sweep

Adds the identity the build pipeline authenticates as, the single grant it holds, the secret
its token is kept in, and the scheduled job that expires old artifacts.

The criterion worth reading twice is that a grant which is too wide works. An identity holding
`roles/editor` publishes artifacts exactly as well as one holding object admin on a single
bucket — every pipeline keeps passing, nothing errors, and the difference is visible only in
the plan, as the type of one resource and the string in one field. The same is true of the
sweep: a plan that stopped declaring it is a shorter plan, not a failing one, and the symptom
arrives months later on a bill.

The token is the third shape of the same problem. The program passes it through as a secret,
so the plan reports it as `[secret]`; a stack whose configuration stores it in the clear
produces an identical resource graph and prints the token into whatever holds the preview's
output.

No service, no credential, no request. See `plan.md` for the implementation shape and
`plan-context.json` for the machine-readable service manifest.
