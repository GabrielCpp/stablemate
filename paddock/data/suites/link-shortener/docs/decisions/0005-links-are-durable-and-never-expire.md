# A short link is durable and never expires

**Status:** decided
**Applies to:** [link-create], [link-follow], the storage design, and the QA plan's criteria

## The question

How long does a created short link keep working, and where does it live in the meantime?
Is there an expiry, a deletion path, and is the ledger allowed to be the memory of the
process that wrote it?

## The ruling

A created short link works indefinitely. There is **no expiry and no deletion** — neither
is in scope, and because nothing expires there is no expired-key response to define: a key
either was created and redirects, or was never created and is the [link-missing] 404.

The implementation is **durable**. The ledger is a JSON file on disk, not in-process state.

The acceptance criterion is that a created link is **persisted to that on-disk ledger**:
after a successful `POST /links`, the ledger contains the new key and its destination. That
is the evidence QA is asked for — the file — and it is provable against the running product.

## Why

[link-follow] promises a person *arrives at* the destination. A promise that lapses when a
process ends is a smaller promise than the bullet makes, so durability is part of the
product rather than an implementation preference.

Expiry and deletion are excluded for the opposite reason: each drags in a response the
three bullets never ask for (what an expired key answers, what a deleted key answers) and a
lifecycle nobody has specified. Ruling them out here is what keeps the backlog at three
bullets.

What QA is asked to *prove* about durability is narrower than durability itself, and
[[0001-restart-survival-is-code-reviews-obligation]] says why and who carries the rest.
