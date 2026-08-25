### `relation-without-subject` — a relation bullet names no subject to relate

A relation key (`updates:`, `emits:`, `locks:`, and their kin) is a claim *about
something* — a record, an event, a lock — and this bullet leads with a verb phrase or a
vague "the data" instead of naming that something. A relation with no subject cannot be
followed: ostler cannot resolve it to the node that owns the subject, and a reader
cannot tell which record's lifecycle just gained a step.

The subject is in the code, not in your head:

1. Open the node's `code:` target and read what the cited symbol actually touches —
   the table or model it writes, the event type it publishes, the mutex or row lock it
   takes. That concrete thing, by the name the book already uses for it, is the subject.
2. **Rewrite the bullet to lead with it**: "`updates: the payout record's status …`",
   not "`updates: status after processing`". If the book documents that subject as its
   own node (a concept, a format), spell it the way that node does so the relation
   resolves to it.
3. If the code touches **more than one** subject under the bullet's verb, that is more
   than one relation — split it, one subject per bullet.

If reading the source shows the relation does not happen at all — the symbol never
writes, emits or locks anything of the kind — the bullet is a false claim: delete it and
say so in your report. Do not invent a plausible subject to make the warn go away; a
relation resolved to the wrong record misleads every reader who follows it, which is
worse than the unresolved one you started with.
