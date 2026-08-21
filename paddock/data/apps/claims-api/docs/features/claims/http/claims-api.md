---
type: server
slug: claims-api
title: Claims API
---
# Claims API

- code: app/api/main.go
- code: app/api/authz.go
- code: app/api/service.go
- code: app/api/openapi.yml
- openapi: app/api/openapi.yml

The claims API is the whole of the product: there is no client. A holder files a
[claim](../concepts/claim-ledger.md) against a policy number, reads the claims that are
theirs, and an adjuster decides them. Every path is JSON, and `/healthz` answers whatever is
waiting on the process to come up.

The contract is not a description of this service — it is the source of it. `openapi.yml` is
committed and `app/api/gen/` is the generator's output, so the routes, the request bodies and the
response shapes below are the document's, checked at compile time rather than at review time.

That has one consequence worth stating plainly, because it is not visible from any handler:
**which operations are protected is decided in `openapi.yml` and nowhere else.** The generated
router puts the bearer scope into the request context for exactly the operations the document
secures, and the verifying middleware skips anything it does not find there. `/healthz` is
unprotected because the document says `security: []` on it, not because a handler checks a path.
An operation the document forgets to secure is served without an identity and every one of its
own rules still passes.

Identity itself is a bearer token from the [auth emulator](../ops/auth-emulator.md); the service
holds no credential of its own and issues nothing. Who may see what, once verified, is
[claim tenancy](../concepts/claim-tenancy.md), and state lives in
[the claim ledger](../concepts/claim-ledger.md) and nowhere else.

The journeys that stitch these routes together are [file a claim](../flows/file-a-claim.md) and
[decide a claim](../flows/decide-a-claim.md).

## Endpoints

### get-health

- does:
  - answers `200` with `{"status": "ok"}` as soon as the process is serving, reading no ledger and asking for no identity.
- code: app/api/service.go
- verify: http_status(200, path="/healthz")
- verify: json_path("status", equals="ok")
- route: `GET /healthz`
- parent: [Claims API](#claims-api)
- request:
  - method: `GET`
  - path: `/healthz`
  - body: none
- response:
  - status: `200`
  - media: `application/json`
  - body: `{"status": "ok"}`

### submit-claim

- does:
  - writes an acceptable claim to the ledger at version `1` with status `Submitted`, attributes it to the calling holder, and answers `201` with the stored record.
- code: app/api/submit.go
- verify: http_status(201, path="/api/claims")
- verify: json_path("claim.status", equals="Submitted")
- verify: json_path("claim.version", equals="1")
- auth: requires a bearer token minted by the configured Firebase project. A request with no
  `Authorization` header, or one carrying a token issued for any other project, is refused `401`
  and writes nothing — a well-formed JWT is not a verified one.
- verify: http_status(401, path="/api/claims")
- auth: a token past its expiry is refused `401` on the same terms as a missing one, so a session
  that was legitimate an hour ago does not keep filing claims.
- verify: http_status(401, path="/api/claims")
- consistency: the stored claim comes back under exactly the field names `openapi.yml` declares —
  `policy_number`, `holder_uid`, `incident_date`, `amount_cents` — because the response is a
  conversion into the generated type rather than an object built by hand beside it.
- verify: json_path("claim.amount_cents", absent=false)
- verify: json_path("claim.holder_uid", absent=false)
- errors: `422` with an `errors` object keyed by field name for every rule the submission is
  refused by — a blank policy number, an incident date that is not a calendar date, an amount that
  is not a positive number of cents, and a blank description.
- verify: http_status(422, path="/api/claims")
- verify: json_path("errors.incident_date", absent=false)
- verify: json_path("errors.amount_cents", absent=false)
- errors: `409 Duplicate Claim` when this holder already has a claim on the same policy number for
  the same incident date, leaving the ledger as it was. Two *different* holders filing on one
  policy for one day are two claims and not a duplicate.
- verify: http_status(409, title="Duplicate Claim", path="/api/claims")
- verify: count(subject="claims", equals=1)
- errors: a refusal is a `Problem` — a `title` naming the refusal and a `detail` describing the
  request. Nothing taken out of the rejected credential appears in either, on any path.
- verify: http_status(401, title="Unauthorized", path="/api/claims")
- persistence: an accepted claim is written through the ledger before the response that announces
  it, and is still on file after the service restarts.
- verify: persists(subject="claim cl-1001")
- route: `POST /api/claims`
- parent: [Claims API](#claims-api)
- refs: [claim ledger](../concepts/claim-ledger.md)
- request:
  - method: `POST`
  - path: `/api/claims`
  - body: `{"policy_number": str, "incident_date": str, "amount_cents": int, "description": str}`
- response:
  - status: `201`
  - media: `application/json`
  - body: `{"claim": {…}}`
  - errors: `401 Unauthorized`, `422` field errors, `409 Duplicate Claim`

### list-claims

- does:
  - returns the claims the caller is entitled to read, each with its `id`, `status` and `version`, so a register can be rendered and a decision prepared without a second request.
- code: app/api/list.go
- verify: http_status(200, path="/api/claims")
- verify: json_path("claims[0].version", absent=false)
- verify: json_path("claims[0].status", matches="Submitted|Approved|Denied")
- authorization: a holder reads only the claims whose `holder_uid` is the subject of their own
  token. The list is scoped by the verified identity rather than by a query parameter, so there is
  no way to ask for someone else's.
- verify: count(subject="claims", equals=1)
- verify: json_path("claims[0].holder_uid", absent=false)
- authorization: an adjuster reads every claim on file, whoever filed it.
- verify: count(subject="claims", equals=2)
- route: `GET /api/claims`
- parent: [Claims API](#claims-api)
- refs: [claim tenancy](../concepts/claim-tenancy.md)
- request:
  - method: `GET`
  - path: `/api/claims`
  - body: none
- response:
  - status: `200`
  - media: `application/json`
  - body: `{"claims": [{"id": str, "policy_number": str, "holder_uid": str, "incident_date": str, "amount_cents": int, "description": str, "status": str, "version": int, "decision_note"?: str}, …]}`
  - errors: `401 Unauthorized`

### get-claim

- does:
  - returns the one claim the id names, with the version a decision has to quote.
- code: app/api/get.go
- verify: http_status(200, path="/api/claims/cl-1001")
- verify: json_path("claim.id", equals="cl-1001")
- authorization: `403 Not Your Claim` when the claim is on file and belongs to another holder.
  The refusal is decided after the lookup, so an id that exists and an id that does not answer
  differently only to whoever is entitled to the difference.
- verify: http_status(403, title="Not Your Claim", path="/api/claims/cl-1002")
- errors: `404 No Such Claim` for an id that is not on the books.
- verify: http_status(404, title="No Such Claim", path="/api/claims/cl-9999")
- route: `GET /api/claims/{id}`
- parent: [Claims API](#claims-api)
- refs: [claim tenancy](../concepts/claim-tenancy.md)
- request:
  - method: `GET`
  - path: `/api/claims/{id}`
  - path variables: `id` — the claim's own identifier, such as `cl-1001`.
  - body: none
- response:
  - status: `200`
  - media: `application/json`
  - body: `{"claim": {…}}`
  - errors: `401 Unauthorized`, `403 Not Your Claim`, `404 No Such Claim`

### decide-claim

- does:
  - moves the named claim to `Approved` or `Denied`, keeps the adjuster's note on the record, increments its version, and answers `200` with the stored claim.
- code: app/api/decide.go
- verify: http_status(200, path="/api/claims/cl-1001/decision")
- verify: json_path("claim.status", equals="Approved")
- verify: json_path("claim.version", equals="2")
- authorization: `403 Adjusters Only` unless the token carries the `adjuster` role. The role is
  read before the claim is looked up, so a holder learns nothing about a claim they may not decide.
- verify: http_status(403, title="Adjusters Only", path="/api/claims/cl-1001/decision")
- concurrency: refuses a decision quoting a version other than the claim's current one with
  `409 Stale Decision`, so an adjuster who read the claim, went away and came back does not
  overwrite the decision that landed meanwhile.
- verify: conflict_on_stale(subject="claim cl-1001", token="version")
- verify: http_status(409, title="Stale Decision", path="/api/claims/cl-1001/decision")
- persistence: a decision is written through the ledger before the response that announces it, and
  the claim is still `Approved`, at the version the decision returned, after the service restarts.
- verify: persists(subject="claim cl-1001")
- errors: `422` with `errors.decision` for a decision outside `approve`/`deny`, and
  `errors.version` when no positive integer version is quoted.
- verify: http_status(422, path="/api/claims/cl-1001/decision")
- verify: json_path("errors.decision", absent=false)
- errors: `404 No Such Claim` for an id that is not on the books.
- verify: http_status(404, title="No Such Claim", path="/api/claims/cl-9999/decision")
- route: `POST /api/claims/{id}/decision`
- parent: [Claims API](#claims-api)
- refs: [claim ledger](../concepts/claim-ledger.md)
- request:
  - method: `POST`
  - path: `/api/claims/{id}/decision`
  - path variables: `id` — the claim's own identifier.
  - body: `{"decision": "approve"|"deny", "version": int, "note"?: str}`
- response:
  - status: `200`
  - media: `application/json`
  - body: `{"claim": {…}}`
  - errors: `401 Unauthorized`, `403 Adjusters Only`, `404 No Such Claim`, `409 Stale Decision`, `422` field errors

### reset-claims

- does:
  - empties the ledger — every claim dropped, numbering back to `cl-1001` — and answers `204` with no body.
- code: app/api/reset.go
- verify: http_status(204, path="/api/claims")
- verify: count(subject="claims", equals=0)
- authorization: `403 Adjusters Only` unless the token carries the `adjuster` role, so the one
  destructive route is the one route whose role gate is provable from both sides.
- verify: http_status(403, title="Adjusters Only", path="/api/claims")
- route: `DELETE /api/claims`
- parent: [Claims API](#claims-api)
- refs: [claim ledger](../concepts/claim-ledger.md)
- request:
  - method: `DELETE`
  - path: `/api/claims`
  - body: none
- response:
  - status: `204`
  - media: none
  - body: empty

A claim number is spent the moment it is issued and nothing returns it, and one holder may file
only once per policy per incident date. Anything that drives this service more than once — a QA
rehearsal, the scored run after it, a re-run following a repair — therefore collides with its own
first pass on a `409` rather than on whatever it was checking. Hence a route rather than a harness
lever: whoever empties the ledger does it through the documented surface, holding a token that says
they may.
