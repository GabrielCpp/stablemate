STATUS: ANSWERED

## Questions from the agent

Run /link-shortener-grill to grill this backlog before it is split into epics.

The backlog defines a public, API-only Go link shortener: creating a short link, following it, and reporting an unknown short link. The API port is settled at `18081`; there is no sign-in or web surface. No epics or milestones exist, and the OKF graph has no flows or orphans; `ostler doctor` reports no findings.

1. ❓ **Q1** — **Link creation contract**: What HTTP endpoint, request shape, success response, and success status expose `[link-create]`?
2. ❓ **Q2** — **Short-link identity**: What form does the returned short link take, and how are its identifiers allocated or handled when they collide?
3. ❓ **Q3** — **URL admission**: Which submitted URL forms and schemes are accepted, and what response is returned for input outside that policy?
4. ❓ **Q4** — **Link lifetime**: Must a created short link remain resolvable after an API restart, and are expiration or deletion behaviors in scope?
5. ❓ **Q5** — **Follow behavior**: Which redirect behavior and HTTP status represent `[link-follow]` when a short link exists?
6. ❓ **Q6** — **Missing-link response**: What HTTP status and response representation tell a caller that an uncreated short link does not exist?

## Answers from the operator

Each answer below is a standing decision, already recorded under `docs/decisions/`. The
citation on each is where it is written down — this gate is not where any of it was
decided, and nothing new is decided here.

**A1 — Link creation contract.** `POST /links`, with a JSON body `{"url": "<the long URL>"}`.
On success the API answers `201 Created` with a JSON body carrying both the key and the
absolute shareable URL:

```json
{"key": "<key>", "short_url": "http://localhost:18081/<key>"}
```

*Cited: `docs/decisions/0003-creating-and-following-a-short-link.md`.*

**A2 — Short-link identity.** The response carries two forms of the same thing: `key`, the
opaque identifier, and `short_url`, that key resolved against the API's own origin
(`http://localhost:18081/<key>`) so it can be shared without the caller assembling it.

On allocation: **every successful `POST /links` allocates a distinct new key**, including
for a destination that was submitted before, and the status is always `201 Created`. It
follows that a key identifies exactly one destination — `GET /<key>` has one answer, and
[link-missing] is defined as "this key was never created", which is only meaningful if a
key is never handed out twice. So an allocation that would reuse a key already in the
ledger must not be recorded; the API allocates until it has an unused one.

*How* keys are generated — random, counted, hashed, how long — is not a product decision
and I am not making one at this gate. Any scheme satisfying the above is acceptable, and
choosing it is the implementing lane's work.

*Cited: `docs/decisions/0006-repeated-destinations-get-distinct-keys.md` for the
distinct-key rule and the always-201 status; `0003` for the two response fields; `0007` for
what a never-created key answers.*

**A3 — URL admission.** A destination is valid when it is an absolute URL with an `http` or
`https` scheme and a non-empty host. Everything else — a relative path, a missing or empty
`url` field, a `javascript:` or `file:` scheme, a malformed URL — is refused with
`400 Bad Request` and a JSON body `{"title": "..."}` naming the reason. The scheme
restriction is a product decision, not a detail: a public redirector that will emit any
scheme is a redirect gadget, and the whole point of a short link is that it gets shared.

*Cited: `docs/decisions/0004-accepted-destinations.md`.*

**A4 — Link lifetime.** A created short link works indefinitely. There is no expiry and no
deletion — neither is in scope, and because nothing expires there is no expired-key
response to define: a key either was created and redirects, or was never created and is the
[link-missing] 404.

The implementation is durable: the ledger is a JSON file on disk, not state held in the
memory of the process that wrote it. **The acceptance criterion is that a created link is
persisted to that on-disk ledger** — after a successful `POST /links`, the ledger contains
the new key and its destination.

Restart survival is a *consequence* of that durability, and it is **not** an acceptance
criterion here: the QA runner fixes a scenario's lifecycle at `start → scenarios → stop`
and gives a scenario no way to cross a process boundary, so a criterion demanding one could
only be discharged by substituting a test suite for runtime evidence — which the QA rules
correctly forbid. Reading that the repository loads its ledger from the file at
construction is **code review's** obligation, not QA's.

*Cited: `docs/decisions/0005-links-are-durable-and-never-expire.md` and
`0001-restart-survival-is-code-reviews-obligation.md`.*

**A5 — Follow behavior.** `GET /<key>` for a key that exists answers `302 Found` with a
`Location` header holding the original URL. A redirect rather than a body, because
[link-follow] says the person *arrives at* the destination rather than reads it.

*Cited: `docs/decisions/0003-creating-and-following-a-short-link.md`.*

**A6 — Missing-link response.** `GET /<key>` for a key that was never created answers
`404 Not Found` with a JSON body `{"title": "Not Found"}`. Not a redirect and not a 500 —
[link-missing] names both of those as the outcomes it exists to rule out.

*Cited: `docs/decisions/0007-an-uncreated-key-is-a-404.md`.*

**Scope, since the split will need it.** The api is the only surface. A round that
implements the three bullets on the api has implemented them completely — there is no web
page and no mobile app to be missing, and nothing here should be read as implying one.

*Cited: `docs/decisions/0002-the-api-is-the-only-surface.md`.*
