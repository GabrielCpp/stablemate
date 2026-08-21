# A repeated destination gets a distinct new key

**Status:** decided
**Applies to:** [link-create] — the response to a `POST /links` for a destination seen before

## The question

Two `POST /links` calls carry the same long URL. Does the second return the key the first
allocated, or a new one? And what status does it answer with?

## The ruling

Every successful `POST /links` allocates a **distinct new key**, including for a destination
submitted before. Both keys redirect to that destination. The status is always
`201 Created` — there is no second success status for "you already had one".

A key therefore identifies exactly one destination and is never handed out twice. An
allocation that would collide with a key already in the ledger is not recorded; the api
allocates until it holds an unused one. *How* keys are generated — random, counted, hashed,
and how long they are — is not settled here and is the implementing lane's to choose.

## Why

`201 Created` asserts a resource was created. Returning a pre-existing key would make that
assertion false, or force a second success status onto a three-bullet fixture.

Reuse would also drag in two rules nobody has written: canonicalisation (are
`http://x.com/a` and `http://x.com/a/` the same destination?) and concurrency (two
simultaneous posts of the same URL). The epic's Non-Goals already exclude a
duplicate-submission policy, and this is what excluding it means in the response.

Uniqueness is not a separate decision so much as what makes the other two work:
[[0003-creating-and-following-a-short-link]] gives `GET /<key>` one answer, and
[[0007-an-uncreated-key-is-a-404]] defines a 404 as "this key was never created" — both
are only meaningful if a key belongs to one creation.
