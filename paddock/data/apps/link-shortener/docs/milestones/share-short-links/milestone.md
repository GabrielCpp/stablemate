---
type: milestone
title: Share short links
status: approved
---

# Share short links

## Outcome

Anyone can turn a long URL into a short link and hand that short link to someone else, who
arrives at the original page by opening it. A short link that was never created says so
instead of sending the visitor somewhere wrong or failing.

The product is one public HTTP API and nothing else. There is no sign-in and no web page:
a short link is a public URL, and keeping it that way is what holds this milestone to three
journeys. This is the smoke milestone of the benchmark, so the whole release must be
recognisable from the api alone.

## Release Boundary

This is one milestone with one gate: the api answers all three journeys at
`http://localhost:18081` and `GET /healthz` reports it ready. Creating, following and
refusing an unknown key must coexist at cutover, because a short link that can be created
but not followed is not a short link.

The first story proves the one end-to-end path: a long URL goes in, a short link comes
out, and opening that short link redirects to the long URL. Later stories widen that path
to destination admission and the missing-key answer.

## User Journeys

### Create a short link from a long URL

- services: api

A person calling the api submits a long URL and gets back a short link they can share.
The call is `POST /links` with a JSON body naming the URL. On success the api answers
`201 Created` with the key and the absolute short URL, so the caller shares it without
assembling anything. A destination that is not an absolute `http` or `https` URL with a
host is refused with `400 Bad Request` and a JSON body that names the reason. Submitting
the same destination twice yields two distinct keys, each answering `201 Created`.

### Follow a short link to its original URL

- services: api

A person opens a short link and arrives at the URL it was created from. `GET /<key>` for a
key that exists answers `302 Found` with a `Location` header holding the original URL. The
person arrives at the destination rather than reading it. A created link keeps working
after the request that created it has ended, because the ledger is a JSON file on disk.

### An uncreated short link says it does not exist

- services: api

A person who opens a short link that was never created is told it does not exist, rather
than being sent somewhere wrong or seeing a crash. `GET /<key>` for an unknown key answers
`404 Not Found` with the JSON body `{"title": "Not Found"}`. Because links never expire and
are never deleted, this is the only non-redirect answer a key can have.

## Architecture Decisions

Every product decision this milestone rests on is a standing record under
`docs/decisions/`, and the auto-resolver of every lane reads it there. The grill record in
[grills/product.md](grills/product.md) is a transcript that cites them, not a source.

- [Restart survival is code review's obligation](../../decisions/0001-restart-survival-is-code-reviews-obligation.md):
  the QA runner cannot cross a process boundary, so durability is proven by reading the
  code, and persistence to the ledger is what QA checks.
- [The api is the only surface](../../decisions/0002-the-api-is-the-only-surface.md): a
  round that implements the three journeys on the api has implemented them completely.
- [Creating and following a short link](../../decisions/0003-creating-and-following-a-short-link.md):
  `POST /links`, the two response fields, and the `302 Found` redirect.
- [Accepted destinations](../../decisions/0004-accepted-destinations.md): absolute `http`
  or `https` with a host, everything else a `400`.
- [Links are durable and never expire](../../decisions/0005-links-are-durable-and-never-expire.md):
  a JSON file ledger, no expiry, no deletion.
- [Repeated destinations get distinct keys](../../decisions/0006-repeated-destinations-get-distinct-keys.md):
  every success allocates a new key and answers `201 Created`.
- [An uncreated key is a 404](../../decisions/0007-an-uncreated-key-is-a-404.md): the
  status and the body shape of the missing-key answer.

## Constraints

- The api is a Go service, the only surface, and the only writer of stored data.
- The api listens on port 18081, not the Go default 8080. The benchmark owns 18080 to
  18099 and nothing else, and each app gets its own port so two runs cannot collide. A run
  whose service cannot bind spends its whole budget failing to start.
- The api serves `GET /healthz`, which answers 200 once the api can serve requests. QA
  brings the api up and waits on that route before it runs anything, because every other
  route answers 2xx only for data that already exists.
- QA drives the api at `http://localhost:18081`, and `short_url` is the key resolved
  against that origin.

## Acceptance

The milestone is complete when, against a freshly started api at `http://localhost:18081`:

- `GET /healthz` answers 200.
- `POST /links` with a valid URL answers `201 Created` with `key` and `short_url`, and the
  on-disk ledger holds the new key and its destination.
- `POST /links` with a relative path, a missing `url`, or a `javascript:` scheme answers
  `400 Bad Request` with a `title`.
- `GET /<key>` for a created key answers `302 Found` with `Location` set to the original
  URL.
- `GET /<key>` for a key that was never created answers `404 Not Found` with
  `{"title": "Not Found"}`.
- Posting the same URL twice yields two different keys, both `201 Created`.

## Non-Goals

- No web page, mobile screen, or sign-in of any kind.
- No expiry, deletion, or editing of a short link, and so no expired-key or deleted-key
  answer to define.
- No choice of key scheme: random, counted or hashed is the implementing lane's call, as
  long as a key is never handed out twice.
- No click counting, analytics or custom aliases.
