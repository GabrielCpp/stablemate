---
type: spec.executive
---

# Executive Summary: Amend and Cancel a Policy

Adds the two writes against an existing record — the amendment and the cancellation — both gated on
the version the screen was rendered from.

The criterion worth reading twice is the stale write. An amendment that carries a version other
than the stored one must be refused and must write nothing, which no single successful amendment
can demonstrate: it takes two writes issued from one reading. The second criterion behind it is the
policy number, which is what the id was derived from and is therefore not amendable — a validator
that keeps demanding it refuses every amendment the form can send.

Two services (`app/api`, Go; `app/web`, React), same origin. See `plan.md` for the implementation
shape and `plan-context.json` for the machine-readable service manifest.
