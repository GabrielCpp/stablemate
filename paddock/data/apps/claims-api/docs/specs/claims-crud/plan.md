---
type: spec.plan
---

# Plan: File a Claim and Put It on the Books

## 0. Status

This story is **implemented**. The plan is retained as a description of the shipped shape, not a
work order to rebuild it: the tree carries the finished service, and what runs against it is QA.

## 1. Approach

`app/api/openapi.yml` is the source and `app/api/gen/` is a pinned generator's output, committed
so a trial never needs the generator on its path. The routes, request bodies and response types
below are the document's, checked by the compiler rather than by a reviewer.

Verification is one middleware over the generated router. It keys off the bearer scope the router
stamps into the request context for the operations the document secures, so the middleware knows
nothing about paths and `/healthz` is reached without an identity because `security: []` says so.
Token verification is the Firebase Admin SDK against the emulator named by
`FIREBASE_AUTH_EMULATOR_HOST`; the service reads no credential and holds none.

The domain rules live apart from the HTTP layer: a handler parses, calls one function, and
serialises.

## 2. Files

- `app/api/openapi.yml` — the contract, including which operations are secured.
- `app/api/gen/` — generated types and chi server, committed and frozen.
- `app/api/store.go` — the JSON ledger: read on every request, written by rename.
- `app/api/authz.go` — the bearer middleware, the `Identity` it hands down, and the `Problem`
  shape every refusal takes.
- `app/api/service.go` — the shared surface: `/healthz`, and the one conversion from a stored
  claim into the generated response type.
- `app/api/submit.go` — `POST /api/claims`, its field rules and its duplicate rule.
- `app/api/reset.go` — `DELETE /api/claims`.
- `compose.yml`, `Dockerfile`, `auth/` — the service, the emulator beside it, and the step that
  creates the fixture identities.

## 3. Acceptance Checklist

- [x] A complete submission answers 201, stored `Submitted` at version 1, attributed to the token's subject, on disk before the response.
- [x] No token, or a token minted for another project, answers 401 and writes nothing.
- [x] An expired token answers 401 on the same terms as a missing one.
- [x] A refused submission answers 422 with per-field messages; a repeat on one policy and date answers 409 Duplicate Claim without writing.
- [x] Stored fields come back under the names `openapi.yml` declares, and no refusal repeats anything out of the rejected credential.
- [x] `GET /healthz` answers 200 without a token; `DELETE /api/claims` empties the ledger for an adjuster and answers 403 Adjusters Only otherwise.

## 4. QA

Every claim above is observable over HTTP. There is no unit-test surface to cite: a sandboxed
scenario has the stack and nothing else on the far side of a forwarded port.

Two consequences of the identity model are worth planning for. Acquiring a token is a request to
the emulator on `18086` and needs no secret, so a scenario that needs three callers acquires
three; and the two refusal arms — another project, and past expiry — cannot be acquired at all.
They are constructed: the emulator does not sign, so a token for a foreign project or a lapsed
one is a JWT the scenario builds and presents.

The ledger persists across scenarios and nothing empties it, so a scenario that needs a policy
number and date free must put the desk back first — `DELETE /api/claims`, documented on the claims
API and needing an adjuster's token. QA drives this stack repeatedly (a rehearsal, the scored
execution, a re-run after a repair), and a scenario that assumes the pair it used the first time
fails the second for being a duplicate rather than for anything this story claims.
