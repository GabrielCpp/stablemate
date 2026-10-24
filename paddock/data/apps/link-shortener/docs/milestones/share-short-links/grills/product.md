# Product grill

The one operator turn the author lane reserves for a human, held once against the
link-shortener milestone and recorded here. Every answer is a standing decision under
`docs/decisions/`, and the citation on each is where it is written down. This record is a
transcript, not a source: nothing is decided here.

## Questions from the agent

The milestone defines a public, API-only Go link shortener: creating a short link,
following it, and reporting an unknown short link. The api port is settled at `18081`, and
there is no sign-in or web surface.

1. **Link creation contract**: what HTTP endpoint, request shape, success response, and
   success status expose creating a short link?
2. **Short-link identity**: what form does the returned short link take, and how are its
   identifiers allocated or handled when they collide?
3. **URL admission**: which submitted URL forms and schemes are accepted, and what response
   is returned for input outside that policy?
4. **Link lifetime**: must a created short link remain resolvable after an api restart, and
   are expiration or deletion behaviours in scope?
5. **Follow behaviour**: which redirect behaviour and HTTP status represent following a
   short link that exists?
6. **Missing-link response**: what HTTP status and response representation tell a caller
   that an uncreated short link does not exist?

## Answers from the operator

**A1, link creation contract.** `POST /links`, with a JSON body `{"url": "<the long URL>"}`.
On success the api answers `201 Created` with a JSON body carrying both the key and the
absolute shareable URL:

```json
{"key": "<key>", "short_url": "http://localhost:18081/<key>"}
```

Cited: `docs/decisions/0003-creating-and-following-a-short-link.md`.

**A2, short-link identity.** The response carries two forms of the same thing: `key`, the
opaque identifier, and `short_url`, that key resolved against the api's own origin so it
can be shared without the caller assembling it.

On allocation: every successful `POST /links` allocates a distinct new key, including for
a destination that was submitted before, and the status is always `201 Created`. A key
identifies exactly one destination, so an allocation that would reuse a key already in the
ledger must not be recorded, and the api allocates until it has an unused one.

How keys are generated is not a product decision. Any scheme satisfying the above is
acceptable, and choosing it is the implementing lane's work.

Cited: `docs/decisions/0006-repeated-destinations-get-distinct-keys.md` for the distinct-key
rule and the always-201 status, `0003` for the two response fields, `0007` for what a
never-created key answers.

**A3, URL admission.** A destination is valid when it is an absolute URL with an `http` or
`https` scheme and a non-empty host. Everything else, a relative path, a missing or empty
`url` field, a `javascript:` or `file:` scheme, a malformed URL, is refused with
`400 Bad Request` and a JSON body `{"title": "..."}` naming the reason. A public redirector
that will emit any scheme is a redirect gadget, and the whole point of a short link is that
it gets shared.

Cited: `docs/decisions/0004-accepted-destinations.md`.

**A4, link lifetime.** A created short link works indefinitely. There is no expiry and no
deletion, so there is no expired-key response to define: a key either was created and
redirects, or was never created and is the 404.

The ledger is a JSON file on disk, not state held in the memory of the process that wrote
it. The acceptance criterion is that a created link is persisted to that on-disk ledger.
Restart survival is a consequence of that durability and is not an acceptance criterion:
the QA runner fixes a scenario's lifecycle at start, scenarios, stop, and gives a scenario
no way to cross a process boundary. Reading that the repository loads its ledger from the
file at construction is code review's obligation, not QA's.

Cited: `docs/decisions/0005-links-are-durable-and-never-expire.md` and
`0001-restart-survival-is-code-reviews-obligation.md`.

**A5, follow behaviour.** `GET /<key>` for a key that exists answers `302 Found` with a
`Location` header holding the original URL. A redirect rather than a body, because the
person arrives at the destination rather than reads it.

Cited: `docs/decisions/0003-creating-and-following-a-short-link.md`.

**A6, missing-link response.** `GET /<key>` for a key that was never created answers
`404 Not Found` with a JSON body `{"title": "Not Found"}`. Not a redirect and not a 500.

Cited: `docs/decisions/0007-an-uncreated-key-is-a-404.md`.

**Scope.** The api is the only surface. A round that implements the three journeys on the
api has implemented them completely.

Cited: `docs/decisions/0002-the-api-is-the-only-surface.md`.
