# link-shortener — decision sheet

The product decisions the backlog deliberately does not make. The backlog is written at
the level of observable behaviour ("a person arrives at the destination"), which is the
right level for a *benchmark input* — it leaves the design work to the author lane. But
the author lane's grill gate is human by construction: it parks and waits for an operator
to settle exactly these questions before epics are split. An unattended round therefore
never gets past it, and an attended one is answered by whoever is watching, differently
each time — so two rounds of the same task are not measuring the same product.

This sheet is that operator, frozen. `_greenfield.py` injects it at the gate, records the
injection in the round's ledger, and reports the sha it applied.

It is written as a **contract**, not as replies to the questions a particular round's
grill happened to ask. Question wording drifts between rounds; what the author lane folds
into the backlog is settled decisions, so decisions are what this file holds. A round
whose grill asks something this sheet does not settle stays **parked** and is reported
parked — that is a finding about this file (extend it, and note the capture), never a
guess made at gate time.

These decisions were first given by hand, at the gate, on the `conda` round. They are
reproduced here verbatim so that round and every later one describe the same product.

## Creation contract

`POST /links` with a JSON body `{"url": "<the long URL>"}`.

On success, `201 Created` with a JSON body carrying both the short link's key and the
absolute URL a person can share:

```json
{"key": "<key>", "short_url": "http://localhost:18081/<key>"}
```

Following a short link is `GET /<key>`, answered with `302 Found` and a `Location` header
holding the original URL — a redirect, because [link-follow] says the person *arrives at*
the destination rather than reads it.

## Accepted destinations

A destination is valid when it is an absolute URL with an `http` or `https` scheme and a
non-empty host.

Everything else — a relative path, a missing or empty `url` field, a `javascript:` or
`file:` scheme, a malformed URL — is refused with `400 Bad Request` and a JSON body
`{"title": "..."}` naming the reason.

The scheme restriction is part of the decision rather than an implementation detail: a
public redirector that will emit any scheme is a redirect gadget, and [link-create] says
the short link is meant to be shared.

## Missing link

`GET /<key>` for a key that was never created answers `404 Not Found` with a JSON body
`{"title": "Not Found"}`.

Not a redirect and not a 500 — [link-missing] names both of those as the outcomes it
exists to rule out.
