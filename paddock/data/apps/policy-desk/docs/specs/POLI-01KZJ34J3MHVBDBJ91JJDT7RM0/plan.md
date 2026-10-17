---
type: spec.plan
---

# Plan: Write a Policy to the Register

## 0. Status

This story is **implemented**. The plan is retained as a description of the shipped shape, not a
work order to rebuild it: the tree carries the finished services, and what runs against them is QA.

## 1. Approach

The API is Go's standard `net/http` with no third-party runtime dependency, and the client is React
Router built by Vite into a static bundle the binary serves. The domain rules live apart from the
HTTP layer: routes parse, call one function, and serialise, so a failing scenario names the rule
rather than the route.

Anything not matched by a documented route falls back to `index.html`, which is what makes every
client route a deep link rather than a 404 on reload.

## 2. Files

- `app/api/store.go` — the JSON ledger: read on every request, written atomically.
- `app/api/validate.go` — the field rules, including the two conditional ones and the umbrella
  prerequisite.
- `app/api/service.go` — the server, the route table, the health and read routes, and the
  refusal-to-status mapping.
- `app/api/create.go` — `POST /api/policies`.
- `app/web/src/NewPolicy.tsx` — the form, its per-field messages, and the redirect on success.
- `app/web/src/PolicyDetail.tsx` — the record a creation lands on.

## 3. Acceptance Checklist

- [x] A complete policy answers 201, is stored as `Draft` at version 1, and is on disk before the response.
- [x] The `id` is the policy number slugged, and a duplicate answers `409 Duplicate Policy Number` without writing.
- [x] A refused field answers 422 with a per-field message under `errors`, rendered beside its field.
- [x] `auto` requires `vehicle_vin` and `home` requires `property_address`; neither is asked for under the other.
- [x] `umbrella` is refused unless an `auto` or `home` policy for the same holder is already on file.
- [x] A past start date is refused, and an end date on or before the start date is refused.
- [x] A successful creation lands on `/policies/{id}` client-side, and that URL is also a working deep link.

## 4. QA

Every claim above is observable over HTTP or on the rendered page. There is no unit-test surface to
cite: a sandboxed scenario has the stack and nothing else on the far side of a forwarded port.

The ledger persists across scenarios and nothing empties it, so a scenario that needs a policy
number free must put the register back first — `DELETE /api/policies`, documented on the policy desk
API. QA drives this stack repeatedly (a rehearsal, the scored execution, a re-run after a repair),
and a scenario that assumes the number it used the first time fails the second for being a duplicate
rather than for anything this story claims.
