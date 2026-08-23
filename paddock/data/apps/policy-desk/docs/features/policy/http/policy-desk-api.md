---
type: server
slug: policy-desk-api
title: Policy desk API
---
# Policy desk API

- code: app/api/service.go
- code: app/api/main.go
- code: app/web/src/routes.tsx
- code: app/web/src/api.ts
- code: app/web/src/main.tsx
- code: app/web/index.html
- code: app/web/src/styles.css
- openapi: none; the service is seven hand-routed paths over `net/http` and publishes no schema.

The policy desk API is the whole of the product's machine surface: the register, the four writes a
[policy](../concepts/policy.md) can take, and a reset. It answers JSON on `/api/…`, answers
`/healthz` for whatever is waiting on it to come up, and serves the client bundle on every other
path — which is what makes [a policy's detail screen](../gui/screens/policy-detail.md) a working
deep link rather than a route that only exists once you are already in the app.

The bundle is not served under `/api/`, so a path in that space that no endpoint below claims is a
`404` rather than a document. An unimplemented endpoint that answers `200` with HTML reads, to
anything checking a status, as an implemented one.

Every rule a write is refused by is decided in [`Validate`](../concepts/policy.md#validate) and
returned as one message per field; the route translates that map into a `422` and decides nothing.
Identity conflicts and version conflicts are the two refusals the route decides itself, because both
are questions about the ledger rather than about the input.

State lives in the [policy ledger](../concepts/policy-ledger.md) and nowhere else — no request is
served out of process memory, which is what lets a created policy be observed after a restart rather
than merely after a write.

The journeys that stitch these routes together are
[create a policy](../flows/create-policy.md) and [edit a policy](../flows/edit-policy.md).

## Endpoints

### get-health

- does:
  - answers `200` with `{"status": "ok"}` as soon as the process is serving, reading no ledger.
- verify: http_status(200, path="/healthz")
- verify: json_path("status", equals="ok")
- code: app/api/service.go
- route: `GET /healthz`
- parent: [Policy desk API](#policy-desk-api)
- request:
  - method: `GET`
  - path: `/healthz`
  - body: none
- response:
  - status: `200`
  - media: `application/json`
  - body: `{"status": "ok"}`

### get-policies

- does:
  - returns every policy on the books, ordered by policy number, whatever status it is in.
- verify: http_status(200, path="/api/policies")
- verify: json_path("policies[0].id", equals="pn-1001")
- does:
  - gives each policy its `id`, `policy_number`, `holder_email`, `coverage_type`, term, `premium`, `status` and `version`, so the register can be rendered and an edit prepared without a second request.
- verify: json_path("policies[0].version", absent=false)
- verify: json_path("policies[0].status", matches="Draft|Cancelled")
- code: app/api/list.go
- route: `GET /api/policies`
- parent: [Policy desk API](#policy-desk-api)
- refs: [policy](../concepts/policy.md)
- request:
  - method: `GET`
  - path: `/api/policies`
  - body: none
- response:
  - status: `200`
  - media: `application/json`
  - body: `{"policies": [{"id": str, "policy_number": str, "holder_email": str, "coverage_type": str, "vehicle_vin"?: str, "property_address"?: str, "start_date": str, "end_date": str, "premium": number, "status": str, "version": int}, …]}`

### post-policies

- does:
  - writes an acceptable policy to the ledger at version `1` with status `Draft`, and answers `201` with the stored record — including the `id` derived from its policy number, which is the address the caller is expected to go to next.
- verify: http_status(201, path="/api/policies")
- verify: json_path("policy.status", equals="Draft")
- verify: json_path("policy.version", equals="1")
- verify: json_path("policy.id", equals="pn-1001")
- errors: `422` with an `errors` object keyed by field name for every rule
  [`Validate`](../concepts/policy.md#validate) decides — a blank policy number, a malformed holder
  email, a coverage type outside the enum, a missing VIN on auto coverage, a missing address on home
  coverage, an umbrella policy with no underlying policy for the holder, a start date in the past,
  an end date that is not after the start date, and a premium outside its coverage type's band.
- verify: http_status(422, path="/api/policies")
- verify: json_path("errors.vehicle_vin", absent=false)
- verify: json_path("errors.end_date", absent=false)
- verify: json_path("errors.coverage_type", absent=false)
- verify: json_path("errors.start_date", absent=false)
- verify: json_path("errors.premium", absent=false)
- errors: `409 Duplicate Policy Number` when the policy number is already on the books, leaving
  the ledger as it was.
- verify: http_status(409, title="Duplicate Policy Number", path="/api/policies")
- verify: count(subject="policies", equals=1)
- code: app/api/create.go
- persistence: policy-record — an accepted policy is written through the ledger before the response is sent, and is
  still on the books after the service restarts.
- verify: persists(subject="policy pn-1001")
- route: `POST /api/policies`
- parent: [Policy desk API](#policy-desk-api)
- refs: [policy](../concepts/policy.md)
- request:
  - method: `POST`
  - path: `/api/policies`
  - body: `{"policy_number": str, "holder_email": str, "coverage_type": str, "vehicle_vin"?: str, "property_address"?: str, "start_date": str, "end_date": str, "premium": number}`
- response:
  - status: `201`
  - media: `application/json`
  - body: `{"policy": {…}}`
  - errors: `422` field errors, `409 Duplicate Policy Number`

### get-policy

- does:
  - returns the one policy the id names, with the version an edit has to quote.
- verify: http_status(200, path="/api/policies/pn-1001")
- verify: json_path("policy.policy_number", equals="PN-1001")
- errors: `404 Unknown Policy` for an id that is not on the books.
- verify: http_status(404, title="Unknown Policy", path="/api/policies/missing")
- code: app/api/service.go
- route: `GET /api/policies/{id}`
- parent: [Policy desk API](#policy-desk-api)
- refs: [policy](../concepts/policy.md)
- request:
  - method: `GET`
  - path: `/api/policies/{id}`
  - path variables: `id` — the slug of the policy number, such as `pn-1001`.
  - body: none
- response:
  - status: `200`
  - media: `application/json`
  - body: `{"policy": {…}}`
  - errors: `404 Unknown Policy`

### put-policy

- does:
  - applies an acceptable edit to the named policy, increments its version, and answers `200` with the stored record.
- verify: http_status(200, path="/api/policies/pn-1001")
- verify: json_path("policy.version", equals="2")
- does:
  - touches the edited policy and no other — every other record keeps its fields, its status and its version.
- verify: unchanged(subject="policy pn-1002", except_fields=[])
- verify: keys_unchanged(subject="policies")
- errors: `400 Version Required` when the body carries no integer `version`, so an edit that simply
  omits the token is refused rather than treated as a fresh write.
- verify: http_status(400, title="Version Required", path="/api/policies/pn-1001")
- errors: `422` with the same field errors creation uses, except that `policy_number` is neither
  sent nor checked and `start_date` may be in the past.
- verify: http_status(422, path="/api/policies/pn-1001")
- verify: json_path("errors.premium", absent=false)
- errors: `404 Unknown Policy` for an id that is not on the books.
- verify: http_status(404, title="Unknown Policy", path="/api/policies/missing")
- code: app/api/update.go
- concurrency: policy-record — refuses a request quoting a version other than the policy's current one with
  `409 Stale Policy`, so an editor who opened the form, went away, and came back with the number
  they were given does not overwrite the edit that landed meanwhile.
- verify: conflict_on_stale(subject="policy pn-1001", token="version")
- verify: http_status(409, title="Stale Policy", path="/api/policies/pn-1001")
- route: `PUT /api/policies/{id}`
- parent: [Policy desk API](#policy-desk-api)
- refs: [policy](../concepts/policy.md)
- request:
  - method: `PUT`
  - path: `/api/policies/{id}`
  - path variables: `id` — the slug of the policy number.
  - body: `{"holder_email": str, "coverage_type": str, "vehicle_vin"?: str, "property_address"?: str, "start_date": str, "end_date": str, "premium": number, "version": int}`
- response:
  - status: `200`
  - media: `application/json`
  - body: `{"policy": {…}}`
  - errors: `400 Version Required`, `409 Stale Policy`, `422` field errors, `404 Unknown Policy`

### post-policy-cancel

- does:
  - moves the named policy to status `Cancelled`, increments its version, and answers `200` with the stored record.
- verify: http_status(200, path="/api/policies/pn-1001/cancel")
- verify: json_path("policy.status", equals="Cancelled")
- does:
  - keeps the cancelled policy on the books rather than dropping it: `GET /api/policies` still lists it, with status `Cancelled`, so the register keeps its shape as policies are cancelled.
- errors: `422` with `errors.confirm` when the body's `confirm` is not the policy's own number, so a
  cancellation is typed out rather than clicked through.
- verify: http_status(422, path="/api/policies/pn-1001/cancel")
- verify: json_path("errors.confirm", absent=false)
- errors: `400 Version Required` when the body carries no integer `version`.
- errors: `409 Stale Policy` when the quoted version is not the policy's current one.
- verify: http_status(409, title="Stale Policy", path="/api/policies/pn-1001/cancel")
- errors: `404 Unknown Policy` for an id that is not on the books.
- code: app/api/cancel.go
- route: `POST /api/policies/{id}/cancel`
- parent: [Policy desk API](#policy-desk-api)
- refs: [policy](../concepts/policy.md)
- request:
  - method: `POST`
  - path: `/api/policies/{id}/cancel`
  - path variables: `id` — the slug of the policy number.
  - body: `{"version": int, "confirm": str}`
- response:
  - status: `200`
  - media: `application/json`
  - body: `{"policy": {…}}`
  - errors: `422` `errors.confirm`, `400 Version Required`, `409 Stale Policy`, `404 Unknown Policy`

### delete-policies

- does:
  - empties the books — every policy dropped — and answers `204` with no body.
- verify: http_status(204, path="/api/policies")
- verify: count(subject="policies", equals=0)
- does:
  - is idempotent: resetting books that are already empty answers `204` and changes nothing.
- verify: http_status(204, path="/api/policies")
- verify: count(subject="policies", equals=0)
- code: app/api/service.go
- route: `DELETE /api/policies`
- parent: [Policy desk API](#policy-desk-api)
- refs: [policy ledger](../concepts/policy-ledger.md)
- request:
  - method: `DELETE`
  - path: `/api/policies`
  - body: none
- response:
  - status: `204`
  - media: none
  - body: empty

A policy number is unique across the whole book and there is no second book, so every creation
spends an identity nothing else returns. That is fine for a desk and wrong for anything that drives
the product repeatedly — a QA rehearsal, the scored execution after it, a re-run following a repair
— which would otherwise fail its second pass on a duplicate policy number rather than on anything it
was checking. Hence a route rather than a harness lever: whoever empties the books does it through
the documented surface, and the reset is as observable as the writes it undoes.
