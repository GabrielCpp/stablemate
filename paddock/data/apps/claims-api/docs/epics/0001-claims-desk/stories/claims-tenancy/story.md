---
type: story
id: CLAI-01KZH7XKD9E7WPRB5S2NGV4HTZ
slug: claims-tenancy
status: Not started
---
# Story: Read back only the claims that are yours

## Dependencies

- Blocked by: claims-crud

## Fixtures

- Fixture: claims
- Fixture: identity

## Context

The desk now takes claims and can say who filed them; this story is the first that has to act
on the answer. Reading is where a multi-tenant service is usually wrong, and it is wrong
invisibly: a register that returns everybody's claims renders perfectly, answers `200`, and
carries every field the contract promises.

[Claim tenancy](../../../../features/claims/concepts/claim-tenancy.md) is the whole of the
rule and lives in one place, so a scenario that catches a widened register names the rule
rather than the route. Scope is decided from the verified token and never from a query
parameter — there is no way to *ask* for someone else's claims, which is what makes a wrong
answer a bug rather than a request.

## Acceptance Criteria

- A holder's register lists exactly the claims whose `holder_uid` is the subject of their own
  token, and an empty register is `200` with an empty list rather than an error.
- An adjuster's register lists every claim on file, whoever filed it.
- Fetching a claim by id answers `200` for its own holder and for an adjuster, with the version
  a decision would have to quote.
- Fetching a claim on file that belongs to another holder answers `403 Not Your Claim`, and an
  id that is not on the books answers `404 No Such Claim`.
- The refusal is decided after the lookup, so the difference between an id that exists and one
  that does not is visible only to a caller entitled to it.

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

- `app/api/store.go::Store` and its `Read` are the one route to the ledger; a register that
  cached the showing between requests would answer correctly in-process and stale everywhere else.
- `app/api/authz.go::Identity` is what a verified token becomes, and
  `app/api/authz.go::Identity.IsAdjuster` is the one role test — scope is read from it rather
  than from anything the caller can set.
- `app/api/store.go::FindClaim` is the existing lookup, which is why the entitlement refusal can
  be decided after the claim is found rather than in place of finding it.
- `app/api/service.go::apiClaim` maps a stored claim to the contract's shape, so a new read
  surface inherits the field names instead of restating them.
- `app/api/authz.go::writeProblem` is the shared refusal writer that gives `403` and `404` the
  same body shape the first story's refusals already have.

## Implementation Status

- **Status**: Not started
