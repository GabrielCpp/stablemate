### `unknown-record-property` — a record's child carries a property its own key does not admit

A **record** key holds one thing with named properties: its direct children are that thing's
`- name: value` properties, not claims of the node. `response:` on an endpoint is the one such
key today, and it admits exactly `media:`, `body:`, `notes:` and `field:`.

```markdown
- response:
  - media: `application/json`
  - body: `{"claim": {"id": str, "status": str}}`
  - field: `id`; type string; required
  - field: `status`; type string; required
```

`field:` is the one property written more than once — one bullet per member of the body — and
repeating it is the shape, not a duplicate.

This fires when one of those children is spelled like neither a bullet key of the node type
(that reading is `misnested-bullet`, not this one) nor one of the properties the record key
itself admits. `- schema: AccountList` written under `- response:` is none of those four, so
nothing reads it, and a reader cannot tell it apart from a fact the book forgot to state.

To repair each one:

1. **Read the key's own page** under `references/node-types/` and the property list in the
   message's suggestion. That list is the whole vocabulary; a record key that declares none is
   never reported here, so the presence of this finding means the vocabulary is written down
   and this property is not in it.

2. **Spell the property the key names.** Most of these are a near-miss: a synonym (`content:`
   for `body:`), or a fact that belongs on the record but under the wrong name.

3. **Move the fact to the key that owns it, if it isn't the record's to hold.** A schema
   reference belongs beside `consumes:` or the node's own body paragraph, not invented as a
   further property of `response:` — widening the vocabulary is a grammar decision, not a repair
   this fragment authorizes.

4. **Do not delete the property to clear the finding.** It was written because someone knew
   something; losing it costs more than the finding. If the fact is real and the key admits no
   place for it, leave it and say so in the report.

**This is not `misnested-bullet`.** That code fires on a record child whose spelling collides
with a bullet key the node type itself declares (`- status:` under `- response:`, colliding
with the endpoint's own `status:`), and its remedy is to promote the bullet out, never to
rename it. This one fires on a child that collides with nothing in the node's own grammar and
simply isn't in the record key's admitted vocabulary — the two never both fire on the same
child.
