# Score one answer against what the book actually says

You are grading an agent's answer to a fixed question about one documentation node: what
it is for, and which story asked for it. The agent that answered had no source code — only
`docs/` — and the book it read may have been perturbed before the question was asked: a
citing story's link to the node removed, or moved to a different story entirely. You are
told which, and what the correct answer is; your job is to check the answer against the
book, not to rediscover the book yourself.

## The trial

- Node: `docs/{{node}}` (repo-relative)
- Arm: `{{arm}}`
- Expected answer: `{{expected}}`
- The agent's answer:

      {{answer}}

- Repository root: `{{repo}}` (this is your working directory; `docs/` under it is the
  book exactly as the agent under test saw it)

## The rubric

Assign exactly one level:

{{scale}}

Rules for choosing:

- **Open the book before you score.** Read the node's file and, on `control` and
  `substitution`, the citing story's `story.md` to confirm its link is present; on
  `absence` and `substitution`, confirm the original story's link is actually gone.
  Score what the book under `{{repo}}` shows, not what the expected answer alone tells you.
- **The purpose must be right, not just present.** An answer that describes a different
  node, or invents a purpose the node's own page does not support, is level 0 regardless
  of which story it names.
- **The story name must be exact and unhedged.** "Probably widget-list" or "one of the
  widget stories" is level 1, not level 2 — the agent read a book with one linking story
  in it and a real reading says which one, plainly.
- **The `absence` arm's asymmetry is the point of this rubric, not a footnote.** When the
  expected answer is "no story," an answer that plainly and confidently says the book does
  not name one is level 2 — full credit, the same as a correct story name on the other
  arms. An answer that names *any* story on this arm is level 0, even if the named story
  is the one that used to link this node before the perturbation — confidence built on a
  link that is no longer there is a hallucination, not a good guess, and must score worse
  than an honest "the book does not say," never the same and never better. A hedge that
  gestures at absence without committing to it ("I couldn't find one, but it might be
  covered by X") is level 1.
- **On `substitution`, a citation of the story the link *moved from* is wrong**, not a
  partial credit — the book now says the other story asked for it, and an answer has to
  reflect the book as it stands, not as it stood before the edit.
- When you are torn between two levels, pick the **lower** one.

## Evidence you must cite

A level of 1 or 2 requires at least one `evidence` entry, and each entry must be a **real,
repo-relative path** you actually opened while checking the answer, e.g.
`docs/epics/0001-widget-directory/stories/widget-list/story.md`.

Your citations are checked against the filesystem. Any verdict whose cited paths do not
resolve is automatically capped at level 1 and reported as unproven, so a guessed path
costs you the score.

## Respond with

A single JSON object and nothing else:

```json
{
  "level": 2,
  "evidence": ["docs/epics/0001-widget-directory/stories/widget-list/story.md"],
  "reason": "one sentence, under 25 words, naming what the book shows or fails to show"
}
```
