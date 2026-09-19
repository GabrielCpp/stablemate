### `prose-buried-bullet` — a numbered list item is prose, and what nests under it is invisible

A `1. …` item in a ladder, a procedure, or a decision list is running text — it was never a
candidate bullet key, however much it may look like one when it ends in a sentence that happens
to contain a colon. Nesting a bullet under it buries that bullet exactly as an undeclared
`- request:` container would, and for the same mechanical reason: nothing that is not a declared
key gets a grammar, so everything under it folds into a flattened string nothing reads as the
node's own claims.

```markdown
1. A cap signal is classified as a scheduled-reset cap before a timeout, so the message never
   claims a wait that never happened.
   - consistency: A cap signal is classified as a scheduled-reset cap before `timed_out`.
   - verify: omits(subject="cap failure message", text="Timeout waiting for result")
```

The `consistency:` claim and its `verify:` check are both inside the numbered item's own
subtree here — neither reaches the node's top-level bullets, so neither mints an obligation nor
gets checked. Fix it by pulling both out, unindented, to the node's own bullet list:

```markdown
1. A cap signal is classified as a scheduled-reset cap before a timeout, so the message never
   claims a wait that never happened.
- consistency: A cap signal is classified as a scheduled-reset cap before `timed_out`.
- verify: omits(subject="cap failure message", text="Timeout waiting for result")
```

Leave the numbered item's own prose exactly as it was — the defect is only in what got filed
beneath it, never in the sentence itself.

**One finding per buried container, not one per buried child.** A single ladder item can bury
more than one claim or check at once; the finding names every buried child in the same
container together, because promoting only one of them still leaves the rest exactly as
invisible as before — the finding is not cleared until none of the named children are still
nested under that item.

**This fires only where something gradeable is actually buried.** A numbered item that nests an
aside, a cross-reference, or a definition with no `SHARED_NORMATIVE_KEYS` name (`consistency`,
`persistence`, `emits`, `consumes`, `concurrency`, `idempotency`, …) and no `verify:` check
underneath it is not this finding — an ordinary nested clarification buries nothing the grammar
was ever going to grade, so it stays silent.

**This is not `misnested-bullet`.** That code's undeclared container is spelled *like* a bullet
key the node type simply never declared (`- request:`, `- response:` on the wrong type) — a
plausible key an author might reasonably have thought was recognized. A numbered list item's
text is never that: it is a sentence, not a candidate spelling, so the repair is never "declare
this key" — it is "this was never a key; move the buried bullet up to where the node's own
grammar can see it."
