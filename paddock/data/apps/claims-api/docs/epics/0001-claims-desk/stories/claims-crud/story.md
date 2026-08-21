---
type: story
id: CLAI-01KZH7X2Y5C8VNQ0J3RTB6MFAW
slug: claims-crud
status: Not started
---
# Story: File a claim and put it on the books

## Dependencies

(none)

## Context

Nothing in the desk reads until something writes, so the first story is the write path end to
end: the OpenAPI document and the code generated from it, the ledger, the submission endpoint,
the reset the ledger needs to be drivable more than once, and the verification that stands in
front of all of them.

The verification is in this story and not a later one on purpose. A first story that took
claims without a token would be a story whose acceptance criteria are satisfied by an
unprotected service, and every scenario written against it would go on passing after the
protection arrived.

The part worth stating is where that protection comes from. It is not wired per route:
[the contract](../../../../features/claims/http/claims-api.md) is what marks an operation as
secured, the generated router puts the bearer scope into the request context for exactly those
operations, and the middleware verifies whatever it finds there. `/healthz` is open because the
document says so. Nothing in a handler names a path.

## Acceptance Criteria

- A complete submission answers `201`, is stored as `Submitted` at version `1`, is attributed to
  the calling token's subject, and is on disk before the response that announces it.
- A request with no `Authorization` header, or one carrying a token minted for another project,
  answers `401` and writes nothing — being a well-formed JWT is not being a verified one.
- A token past its expiry answers `401` on the same terms as a missing one.
- A refused submission answers `422` with a per-field message under `errors` for each rule it
  broke, and a second claim by the same holder on the same policy number for the same incident
  date answers `409 Duplicate Claim` without writing.
- The stored claim comes back under the field names `openapi.yml` declares, and no refusal —
  on any path — repeats anything taken out of the credential it rejected.
- `GET /healthz` answers `200` with `{"status":"ok"}` without a token, and `DELETE /api/claims`
  empties the ledger for an adjuster and answers `403 Adjusters Only` for anyone else.

## Implementation Status

- **Status**: Not started
