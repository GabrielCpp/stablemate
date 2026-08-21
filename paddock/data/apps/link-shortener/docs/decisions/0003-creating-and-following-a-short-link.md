# Creating and following a short link

**Status:** decided
**Applies to:** [link-create], [link-follow] — the api's two public operations

## The question

What does a caller send to create a short link, what comes back, and what happens when
somebody opens the link that came back?

## The ruling

**Creating.** `POST /links`, with a JSON body `{"url": "<the long URL>"}`. On success the
answer is `201 Created` with a JSON body carrying both the key and the absolute URL a
person can share:

```json
{"key": "<key>", "short_url": "http://localhost:18081/<key>"}
```

**Following.** `GET /<key>`, answered with `302 Found` and a `Location` header holding the
URL the link was created from.

## Why

Both halves of the creation response are load-bearing: the key is what the service is
about, and the absolute URL is what makes the thing shareable without the caller having to
know where the service lives. A redirect rather than a rendered page because [link-follow]
says the person *arrives at* the destination rather than reads it — and the port in
`short_url` is the backlog's operating constraint, which is a property of the benchmark's
environment rather than of the product.
