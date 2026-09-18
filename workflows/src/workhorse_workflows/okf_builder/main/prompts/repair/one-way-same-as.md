### `one-way-same-as` — a `same-as:` claim declared on one side only

A node's `same-as:` names another node as the *same documented thing*, written a second
time — and the target does not name it back. Sameness is symmetric: a reader who arrives
at the target still sees two separate things, which is the exact divergence `same-as:`
exists to close. The claim is incomplete until both occurrences carry it.

First confirm the claim itself is true before completing it. Open both nodes and check
whether they really are one documented thing rendered or reached in more than one place —
the same nav region embedded on two screens, the same webhook handler documented from two
call sites — not two implementations that happen to look alike or a narrower/broader pair
(that is `extends:`, not `same-as:`).

- **If they are the same thing**, add the reciprocal bullet on the target node, pointing
  back at the node that declared it:
  ```markdown
  - same-as: [<declaring node's title>](<path back to it>)
  ```
  The finding's `suggestion` already gives you the exact link to write. Write it on the
  target node named in the finding, not anywhere else — the claim is per edge, not a
  family-wide broadcast, so a reciprocated chain (A↔B, B↔C, C↔D) is written one pair at a
  time and never demands that every member also name every other member.

- **If they are not the same thing** — a rename you are second-guessing, or a link that
  was never true — delete the original `same-as:` bullet instead of inventing the
  reciprocal one. A `same-as:` written to make the finding go away, rather than because
  the two nodes genuinely are one documented thing, tells the QA obligation packet that
  two separate things are one, and a change to either stops being owed against both —
  which is worse than the open finding you started with.

Do not "fix" this by relating the two nodes some other way (`extends:`, `parent:`,
`detail:`) unless that is what the source evidence actually supports — those keys mean
something narrower than "this is the same thing", and swapping one in to silence the
finding plants a claim nobody made.
