---
type: story
id: POLI-01KZJ34J3MHVBDBJ91JJDT7RM0
slug: create-policy
status: Not started
---
# Story: Write a policy to the register

## Dependencies

(none)

## Fixtures

- Fixture: policies

## Context

Nothing in the desk reads until something writes, so the first story is the write path end to end:
the ledger, the create endpoint, the form that posts to it, and the record it redirects to.

The part worth stating is that the rules are not uniform across coverage types.
[A policy](../../../../features/policy/concepts/policy.md) asks for a vehicle VIN only when the
coverage is `auto` and a property address only when it is `home`, and an `umbrella` policy may not
be written at all unless the same holder already has one of the other two on file. A validator
written as one required-fields list passes every scenario that only ever posts an `auto` policy.

## Acceptance Criteria

- A complete policy answers `201`, is stored as `Draft` at version `1`, and is on disk before the
  response that announces it.
- The response's `id` is the policy number slugged, and posting a policy number already on file
  answers `409 Duplicate Policy Number` without writing.
- A missing or malformed field answers `422` with a per-field message under `errors`, and the form
  renders each message beside the field it names rather than as one blob.
- `auto` requires `vehicle_vin`, `home` requires `property_address`, and neither field is asked for
  under the other coverage type.
- `umbrella` is refused unless an `auto` or `home` policy for the same holder email is already on
  file.
- A start date in the past is refused, and an end date on or before the start date is refused.
- A successful creation lands on the new policy's detail screen at `/policies/{id}`, client-side,
  and that URL also works as a deep link into a freshly loaded document.

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

No prior implementation reference exists.

## Implementation Status

- **Status**: Not started
