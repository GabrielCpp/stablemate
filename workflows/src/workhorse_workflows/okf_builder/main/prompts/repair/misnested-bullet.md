### `misnested-bullet` — a bullet key is nested under a record, where it states something else

A **record** key holds one thing with named properties: its direct children are that thing's
`- name: value` properties, not claims of the node. `response:` on an endpoint is the one such
key today.

```markdown
- response:
  - media: `application/json`
  - body: `{"claim": {"id": str, "status": str}}`
```

This fires when one of those children is spelled like a bullet key the node type itself
declares. `- status: 200` written under `- response:` reads as a property of the response, and
the endpoint's own `status:` — the claim a scenario is held to, the one that mints an
obligation — is then absent from the node. Both readings are grammatical and only one is what
the author meant, which is why the nesting is reported rather than resolved in favour of
either.

Fix it by promoting the bullet, keeping its value:

```markdown
- response:
  - media: `application/json`
- status: 200 with the claim in the body
```

Mind where it lands. `fmt` orders bullets by the type's canonical order, and a `verify:`,
`fixture:` or `arrange:` binds to the nearest claim **above** it — so a promoted `status:`
placed below an existing arm's grounding steals that grounding from the claim it was written
for. Promote it into its canonical position and leave every attached bullet under the claim it
already had.

**This is not `unknown-entry-property`.** That code is about an `entries:`-shaped key
(`provides:`, `flags:`), whose children are *things that have claims* rather than the
properties of one thing, and it fires on a property outside a vocabulary the key declared. This
one fires on a record child whose spelling collides with the node's own grammar, and its remedy
is to move the bullet out, never to rename it.

**A child of any other spelling is not this finding.** A child that falls outside the record
key's own declared property vocabulary — a `- schema:` under `- response:` — is
`unknown-record-property`, not this one; a record key that declares no vocabulary at all is
unchecked either way. Do not delete such a child to clear a finding it did not cause.

## The same collision under a key the node type never declared

This also fires when the *parent* key itself is not one the node type declares — `- request:`
on an `endpoint`, say, which `endpoint` never wrote a `BulletKey` for:

```markdown
- request:
  - method: `GET`
  - path: `/api/accounts`
```

`method:` and `path:` are `endpoint`'s own bullet keys, so nesting them under an undeclared
`request:` buries them the same way nesting them under a declared record would — except here
there is no declared grammar for `request:` at all, so the child is not merely misplaced, it is
invisible: nothing reads `meta["request"]` as a source of the node's `method:`/`path:` claims.
Fix it the same way, by promoting each buried child to a top-level bullet of the node:

```markdown
- method: `GET`
- path: `/api/accounts`
```

Drop the parent when promoting empties it. Nothing will tell you if you leave it: `- request:`
declares nothing on any type, so it is the author's own vocabulary as far as `unknown-bullet`
is concerned, and an empty container buries no child for this check to find. It reads as prose
that happens to end in a colon, which is the one thing it is not.

One finding per buried child, so a parent burying two keys reports twice and each is cleared
by its own promotion. Clearing one does not clear the other.

**Do not confuse this with a numbered-list item.** The check only reads a parent key that is
itself spelled like a bullet key (lowercase, digits, hyphens); a numbered-list "key" that is
really a sentence of prose never qualifies, so it is never this finding and the promote remedy
is never the right one for it.
