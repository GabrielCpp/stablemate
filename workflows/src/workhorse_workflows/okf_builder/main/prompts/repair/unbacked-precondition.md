### `unbacked-precondition` — the consumer states the state; the producer never claimed it

A `fixture:` bullet on this node carries prose after an em dash —
`- fixture: seeded-acme — an account exists` — and the book fixture node it names declares no
`provides:` at all.

That sentence is not decoration. `ostler qa compile-plan` copies it verbatim into the compiled
scenario's `preconditions=[...]`, so it ships as a stated fact about what the arrangement leaves
behind. But it is written by the node that *uses* the arrangement, about work the node that
*performs* it never claimed — and with no `provides:` on the fixture, nothing in the repo can
hold it to leaving that state behind, in doctor or at run time.

To repair each one:

1. **Fix it on the producer, not the consumer.** Open the fixture node the bullet names
   (`docs/features/<surface>/fixtures/<name>.md`) and add a `provides:` bullet with one child
   per fact it leaves behind, in the grammar's shape:

   ```markdown
   - provides:
     - holder-a — a claim holder, `holder-a@example.com`
     - adjuster — `adjuster@example.com`, carrying the adjuster role claim
   ```

2. **Read the fixture's own steps to write them, not the consumer's sentence.** The consumer's
   prose is one caller's paraphrase of what it needed; `provides:` is what the last step
   actually leaves in place, and callers that phrased it differently are all held to this one
   list. If the steps do not support a fact the sentence claims, the defect is the sentence.

3. **One key per fact, and the key is what gets referenced.** `@<fixture>.<key>` on another
   node resolves against exactly these names, so a key that names nothing a caller could read
   back is prose in the wrong place — put it in the file's body paragraph instead.

4. **Do not clear the finding by deleting the em-dash prose.** The precondition is real; what
   is missing is the fixture's claim to establish it. Deleting the sentence removes the only
   written record of why the scenario needs the arrangement, and the compiled plan then states
   no precondition at all.

A fixture that genuinely cannot say what state it leaves behind cannot be held to leaving it,
and is not a fixture — it is a command. The same rule is why the hand-written `qa: {fixtures:}`
tier refuses an entry with no `provides:`, and why `ostler qa fixtures migrate` reports
`status="incomplete"` instead of success.
