---
type: spec.executive
---

# Executive Summary: Read Back Only the Claims That Are Yours

Adds the two read paths — the register and the single claim by address — and the one rule they
both obey.

The criterion worth reading twice is that scope is decided from the verified token and from
nothing else. There is no tenant parameter to pass and no way to ask for another holder's claims,
so a register that returns everybody's is not a mis-parameterised request but a broken rule; and
it is broken invisibly, because a widened register answers `200` and carries every field the
contract declares. The rule lives in one file so that a failing scenario names the rule rather
than the route.

The single-claim path adds the ordering that keeps existence from leaking: the claim is looked up
first, and only then refused with `403 Not Your Claim`, so the difference between an id on the
books and one that is not is visible only to a caller entitled to it. See `plan.md` for the
implementation shape and `plan-context.json` for the machine-readable service manifest.
