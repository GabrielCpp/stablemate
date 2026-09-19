### `empty-required-section` — a required heading exists but carries no prose

The heading the node's type requires is present, so `missing-required-section` is not what
fired — this is the section that was scaffolded and then never written. The heading alone
satisfies nothing: it exists precisely so something is said under it, and nothing has been.

**The remedy is to write the section**, not to touch the heading:

1. Read the node's `code:` target (and any other grounded bullets) to learn what belongs
   under this heading — the commands a `cli` exposes, the endpoints a `server` serves, the
   steps a `runbook` walks through. Never invent content the source does not support.
2. Write it as prose or a list directly under the heading, the way a filled section of this
   type reads elsewhere in the corpus. A `### <id>` sub-heading with nothing beneath it does
   not count as content — the check that fired here treats a body made only of sub-headings
   as still empty, because a reader opening the section to learn something finds the same
   nothing a machine does.

**Deleting the heading is not a fix.** It only exchanges this finding for
`missing-required-section` — the same missing content, reported by its sibling code instead.
If the source genuinely settles nothing to write here, leave the heading and the finding
standing, and say in `doc_status` what is missing and why.
