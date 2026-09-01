---
type: story
id: CLAI-01KZH7Y4F2G6XQSC7T3PHW5JVB
slug: claims-adjudication
status: Not started
---
# Story: Approve or deny a claim

## Dependencies

- Blocked by: claims-crud
- Blocked by: claims-tenancy

## Fixtures

- Fixture: identity

## Context

The last story is the only one that changes a claim after it is filed, and it is the only one
with two writers in the frame. A decision quotes the version the adjuster read; a decision that
quotes a stale one is refused rather than applied, because the alternative is an adjuster who
opened a claim, went away and came back silently overwriting the decision that landed while they
were gone.

Nothing about a decision is observable inside one request. Both of the rules that matter — the
compare-and-swap and the durability of the result — need a scenario that reads, writes, and then
reads again from a process that is not the one that wrote. A single accepted `200` proves
neither.

## Acceptance Criteria

- An adjuster's decision moves the claim to `Approved` or `Denied`, keeps the note on the record,
  increments its version, and answers `200` with the stored claim.
- A caller whose token carries no `adjuster` role answers `403 Adjusters Only`, decided before
  the claim is looked up.
- A decision quoting a version other than the claim's current one answers `409 Stale Decision`
  and leaves the record as the accepted decision left it.
- A decision outside `approve`/`deny` answers `422` with `errors.decision`, a missing or
  non-positive version answers `422` with `errors.version`, and an unknown id answers
  `404 No Such Claim`.
- The decided claim is still `Approved`, at the version the decision returned, after the service
  restarts.

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

- `app/api/store.go::Store` remains the only reader and writer; a decision table held beside the
  ledger would answer every same-process read correctly and lose the decision at the restart the
  criteria check.
- `app/api/store.go::FindClaim` locates the record to compare-and-swap against, and
  `app/api/store.go::Claim` carries the `version` field that is the token — there is no separate
  decision sequence.
- `app/api/authz.go::Identity.IsAdjuster` is the existing role test, so the `403 Adjusters Only`
  refusal is the same rule `app/api/reset.go::Server.ResetClaims` already enforces.
- `app/api/submit.go::validateSubmission` is the shape a per-field `422` takes in this service;
  the decision's body errors follow it rather than inventing a second error format.
- `app/api/authz.go::writeProblem` and `app/api/service.go::writeJSON` are the two response
  writers already in use, which is what keeps the accepted and refused bodies consistent.

## Implementation Status

- **Status**: Not started
