### `relation-without-subject` — a relation bullet names no subject to relate

A relation key (`persistence:`, `emits:`, `idempotency:`, and their kin) is a claim
*about something* — a record, an event, a lock — and this bullet leads with a verb
phrase or a vague "the data" instead of naming that something. A relation with no
subject cannot be followed: ostler cannot join it to the other nodes that share the
subject, and a reader cannot tell which record's lifecycle just gained a step.

The subject has an exact machine shape, and only that shape counts: **one lowercase
identifier** (letters, digits, `.`, `_`, `-`), then an em dash with a space on either
side, then the claim.

```
- persistence: payout-record — the confirmed payout is written through the ledger
```

`Payout Record — …`, `the payout record's status — …`, or a sentence with no em-dash
head are all prose to the parser — the warn stands however clearly they seem to name
the thing. The head is narrow on purpose, so an ordinary sentence cannot claim a
subject by accident.

The subject itself is in the code, not in your head:

1. Open the node's `code:` target and read what the cited symbol actually touches —
   the table or model it writes, the event type it publishes, the mutex or row lock it
   takes. That concrete thing is the subject.
2. **Name it as a slug and lead with it.** If the book documents that subject as its
   own node (a concept, a format), use that node's slug verbatim — the join works by
   equality, so two nodes relate only when they spell the subject identically.
3. If the code touches **more than one** subject under the bullet's verb, that is more
   than one relation — split it, one subject per bullet.

If reading the source shows the relation does not happen at all — the symbol never
writes, emits or locks anything of the kind — the bullet is a false claim: delete it and
say so in your report. Do not invent a plausible subject to make the warn go away; a
relation resolved to the wrong record misleads every reader who follows it, which is
worse than the unresolved one you started with.
