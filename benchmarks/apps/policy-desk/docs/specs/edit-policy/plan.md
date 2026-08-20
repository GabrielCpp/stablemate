---
type: spec.plan
---

# Plan: Amend and Cancel a Policy

## 0. Status

This story is **implemented**. The plan is retained as a description of the shipped shape, not a
work order to rebuild it: the tree carries the finished services, and what runs against them is QA.

## 1. Approach

Both writes go through one gate. The screen renders a version, the form sends it back, and the
handler compares it with the stored one before touching anything: equal, and the write lands with
the version bumped; different, and it is refused; absent, and the request is rejected as malformed
rather than treated as an unconditional write.

The two actions live in a component of their own so the detail screen stays a reading of the record
and the writes against it stay one file.

## 2. Files

- `app/api/update.go` — `PUT /api/policies/{id}`.
- `app/api/cancel.go` — `POST /api/policies/{id}/cancel`.
- `app/api/service.go` — the route table gains both routes.
- `app/api/validate.go` — the policy number is create-only, so an amendment neither sends it nor may
  change it.
- `app/web/src/EditPolicy.tsx` — the amendment form, carrying the version it was rendered from.
- `app/web/src/PolicyActions.tsx` — the edit link and the confirmed cancellation.
- `app/web/src/PolicyDetail.tsx` — renders the actions beside the reading.

## 3. Acceptance Checklist

- [x] A valid amendment answers 200, bumps the version, and leaves the status alone.
- [x] A stale version answers `409 Stale Policy` and writes nothing.
- [x] A missing version answers `400 Version Required`.
- [x] An amendment is judged by the same field rules as a creation, minus the policy number and the past-start-date refusal.
- [x] Cancelling requires the policy number typed back; anything else answers 422 beside the field.
- [x] A cancelled policy reads `Cancelled` at a bumped version and stops offering the cancellation form.
- [x] A refused amendment leaves the detail screen's reading intact.

## 4. QA

Every claim above is observable over HTTP or on the rendered page. The stale-write criterion is the
one that needs two requests from one reading: read a policy, amend it, then amend it again with the
version from the first reading. A scenario that re-reads between the two writes never sees a
refusal, and passes against a handler that ignores the version entirely.

The ledger persists across scenarios and nothing empties it, so a scenario that needs a policy it
can cancel must create one — a cancelled policy cannot be cancelled twice.
