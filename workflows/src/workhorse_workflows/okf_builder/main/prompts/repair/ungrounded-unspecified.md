### `ungrounded-unspecified` — a resolved-by-design claim with nothing that resolved it

An `unspecified:` bullet says the book looked at this behaviour and *decided* to leave it
open — which downstream consumers trust: QA treats it as resolved-by-design, not as a gap to
invent coverage for. That trust rests entirely on the citation, and this bullet has none that
resolves: no markdown link, or a link whose target file does not exist.

The rule is the resolver's own: a decision may be recorded only when you can quote the thing
that already settles it — a record under `docs/decisions/`, a convention in `AGENTS.md` or an
installed skill, an acceptance criterion in the story's own spec. An `unspecified:` bullet is
exactly such a recording, so it carries the same burden.

- If the settling record exists, link it: `- unspecified: retry cadence is deliberately
  unfixed — [decision](../../decisions/0007-retry-cadence.md)`. A dead link is repaired by
  finding where the record moved, never by unlinking the claim.
- If no record exists, **the bullet is deleted, not decorated**. Writing a decision record
  to back it is making the decision, and that is the operator's call, not a repair. What the
  book does not know is simply absent from it; an `unspecified:` without a source invents a
  ruling nobody made.
