### `deprecation-without-successor` — a deprecation that names no replacement

The concept's `deprecates:` resolves to a real node, but the concept carries no `prefers:`
and no `rule:` — so all it tells a reader is "not this one". A deprecation with no successor
reads as "delete this", which is usually wrong: the deprecated path typically survives
precisely because some caller still legitimately needs it.

Repair from the evidence that made the deprecation true in the first place:

- Read the cited code for what superseded it — the replacement the deprecation annotation
  or comment names, the implementation the migrated call sites moved to. Link it with
  `- prefers: [<winning node>](<path>)`, or, when the answer is conditional, state it as
  `- rule:` prose ("reach for X unless …").
- List in the body what still legitimately uses the deprecated path, and why — that list
  is what separates "superseded" from "delete this".
- If the source names no successor at all — the thing was abandoned, not replaced — say
  exactly that in `rule:` prose. **Do not invent a winner**; a `prefers:` link nobody's
  code supports is a selection rule nobody made.
