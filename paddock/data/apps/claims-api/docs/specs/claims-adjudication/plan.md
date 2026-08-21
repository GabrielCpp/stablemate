---
type: spec.plan
---

# Plan: Approve or Deny a Claim

## 0. Status

This story is **implemented**. The plan is retained as a description of the shipped shape, not a
work order to rebuild it.

## 1. Approach

One handler, read-modify-write through the ledger story 1 shipped. The role is read first, then
the claim is looked up, then the quoted version is compared against the stored one, then the
decision is applied and written before the response is composed.

The order is the design. Reading the role first is what keeps a holder from learning whether a
claim exists; writing before responding is what makes the returned version a promise about disk
rather than about memory.

## 2. Files

- `app/api/decide.go` — `POST /api/claims/{id}/decision`, the role gate, the compare-and-swap and
  the field rules.

The store is untouched: a decision is a write through the ledger that already exists.

## 3. Acceptance Checklist

- [x] An adjuster's decision moves the claim, keeps the note, increments the version, answers 200 with the stored claim.
- [x] A token with no `adjuster` role answers 403 Adjusters Only, decided before the lookup.
- [x] A stale version answers 409 Stale Decision and leaves the accepted decision in place.
- [x] A decision outside approve/deny answers 422 errors.decision; a missing or non-positive version answers 422 errors.version; an unknown id answers 404 No Such Claim.
- [x] The decided claim survives a service restart at the version the decision returned.

## 4. QA

Two of these need more than a request each. The compare-and-swap needs two writes off one reading,
in that order, with nothing re-read between them — a scenario that refreshes the version before
the second write proves nothing and passes. Durability needs the process replaced between the
write and the read: `docker` is opted into in `agents.yml` for exactly this, and a re-read inside
the same process is satisfied by a decision table held in memory.

The desk is not empty when this story's scenarios start; they file what they decide, through the
documented submission route, so the version they quote is one they watched being issued.
