### `unknown-entry-property` — an entry carries a key its own key does not admit

A key like `provides:` or `flags:` holds a nested list of **things that have claims**, not a
nested list of claims. Each direct child is one value:

```markdown
- provides:
  - count — the number of widgets the directory holds
    - from: [seed-it](#seed-it)
    - read: json `.widgets | length`
```

`count — …` is the value; `from:` and `read:` are properties *of that value*. This finding says
one of those properties is a key the owning key does not admit — so nothing reads it, and a
reader cannot tell it apart from a fact the book forgot to state.

To repair each one:

1. **Read the key's own page** under `references/node-types/` and the property list in the
   message's suggestion. That list is the whole vocabulary; a key that declares none is never
   reported here, so the presence of this finding means the vocabulary is written down and this
   property is not in it.

2. **Spell the property the key names.** Most of these are a near-miss: a synonym (`source:`
   for `from:`), a plural, or the property of a neighbouring key written on the wrong entry.
   Move the fact to the key that owns it, under the spelling that key uses.

3. **Prose belongs in the headline or the body.** A child that is a sentence rather than a
   `key: value` is not a property at all. Fold it into the entry's own headline after the em
   dash, or into the node's body paragraph — both are read by a person, and neither is silently
   dropped the way an unadmitted key is.

4. **Do not delete the property to clear the finding.** It was written because someone knew
   something; losing it costs more than the finding. If the fact is real and the key admits no
   place for it, leave it and say so in the report — widening the vocabulary is a grammar
   decision, not a repair.
