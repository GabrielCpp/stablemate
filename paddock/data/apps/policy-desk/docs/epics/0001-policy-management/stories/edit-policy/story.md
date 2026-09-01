---
type: story
id: POLI-01KZGN1TZGBWDASB4V28BJ4HN4
slug: edit-policy
status: Not started
---
# Story: Amend and cancel a policy

## Dependencies

- Blocked by: create-policy
- Blocked by: policy-list

## Fixtures

- Fixture: policies

## Context

A policy on the books changes: the premium is re-rated, the term moves, the holder cancels. Both
edits go through the same gate — the version the screen was rendered from travels with the write,
and a write against a stale reading is refused rather than applied over whatever landed in between.

The policy number is not amendable. It is what the id was derived from, so the edit form neither
sends it nor may change it, and a validator that keeps asking for it refuses every amendment.

## Acceptance Criteria

- A valid amendment answers `200`, bumps the version, and leaves the status alone.
- An amendment carrying a version other than the stored one answers `409 Stale Policy` and writes
  nothing; one carrying no version at all answers `400 Version Required`.
- The amendment is judged by the same field rules as a creation, except the policy number, which is
  neither sent nor changed, and the start date, which may stay in the past on an existing policy.
- Cancelling requires the policy number typed back as confirmation; anything else answers `422`
  with the message beside the confirmation field.
- A cancelled policy reads `Cancelled` at a bumped version, and its detail screen stops offering
  the cancellation form.
- A refused amendment leaves the detail screen's reading intact rather than blanking it.

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

- `app/api/validate.go::Validate` already takes an `isCreate` flag, which is the seam the
  policy-number and past-start-date exceptions go through — not a second validator.
- `app/api/store.go::Policy` carries the `Version` field the compare-and-swap quotes, and
  `app/api/service.go::indexOf` is the existing lookup the write reads through.
- `app/api/service.go::Server.Routes` registers the amendment and the cancellation beside the
  existing routes, and `app/api/service.go::decode` is the one request-body reader.
- `app/api/service.go::writeError` gives `409 Stale Policy` and `400 Version Required` the body
  shape every earlier refusal already has.
- `app/web/src/api.ts::updatePolicy` and `app/web/src/api.ts::cancelPolicy` are the client calls,
  and `app/web/src/FieldError.tsx::FieldError` is the existing per-field renderer the confirmation
  message reuses.

## Implementation Status

- **Status**: Not started
