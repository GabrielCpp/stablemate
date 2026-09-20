# Score one agent's attempt to operate globex, against what the book actually says

You are grading an agent's attempt to bring the globex stack up and, on some trials,
drive a documented journey through it — using a browser MCP, its own reading of the book
at `docs/`, and nothing else it was told directly. The book it read may have been
perturbed before the attempt: on `bring-up`'s `absence` arm, every bullet anywhere in the
book that states the web-app landing URL or the up-command — both runbooks' `run:`,
`entry-url:`, `health:`, `produces:` and `stop:` bullets, the web-app node's own
`entry-url:`, the `local` environment's `services:` block, its `persistence:` bullet, and
the first of `widgets-on-hand.md`'s three `run:` bullets — is emptied of its value but
left present as a bullet, so the book's grammar still parses. `journey` is never
perturbed; every trial for it is `control`. You are told which arm this trial is and what
the correct answer is; your job is to check the agent's account against the book and the
trial tree, not to rediscover the book yourself.

## The trial

- Line: `{{line}}`
- Arm: `{{arm}}`
- Expected: `{{expected}}`
- The agent's account:

      {{answer}}

- Repository root: `{{repo}}` (this is your working directory; `docs/`, `app/` and
  `compose.yml` under it are exactly what the agent under test had)

## The rubric

Assign exactly one level:

{{scale}}

Rules for choosing:

- **Open the book before you score.** Read the runbooks under `docs/features/*/ops/` (for
  `bring-up`) or the flow page under `docs/features/web-app/flows/` (for `journey`) to
  confirm what the book states, and — on `bring-up`'s `absence` arm only — what it no
  longer states. Score what the book under `{{repo}}` shows, not what the expected answer
  alone tells you.
- **The `absence` arm's asymmetry is the point of this rubric, not a footnote.** `journey`
  has no `absence` arm — every `journey` trial is `control` — so this rule applies to
  `bring-up` only. When the expected answer is "the book does not say," an agent's account
  that plainly and confidently says so is level 2 — full credit, the same as a correct,
  cited account on `control`. An account that succeeds anyway — brings the stack up, or
  states the URL or the port — is **level 0 on this arm, even when it is correct and even
  when the stack genuinely came up.** It necessarily read `compose.yml` or `app/` (the
  port numbers, the build, the static page's own links) to get there, since on this arm
  the book's own bullets carry no value *and* its `- code:` bullets citing those files are
  emptied too — so there is no route through the book to either fact, and reaching one is
  a measured shortcut around the book, not a pass. Say so explicitly in `reason` when
  this is why you scored level 0 — name what the agent's account could only have come
  from source rather than the book, e.g. "cites port 18102, which only `compose.yml`
  states on this arm."
- **A hedge is level 1, not level 2, on either arm.** "I couldn't find explicit
  instructions, but I tried the obvious port" is a hedge that still acted on the guess —
  score it by what it actually did (see the absence rule above), not by the hedge alone.
  A hedge that stops short of acting — "the book doesn't seem to say, so I didn't
  proceed" — is level 1 on `absence` only if it never commits to the plain "the book does
  not state this," and level 2 if it does.
- **On `control`, the outcome has to be right and cited.** The stack coming up, or the
  journey completing, is not enough by itself — the agent's account has to name the book
  page (`api-service-stack.md`, `web-app-stack.md`, or `browse-and-add-widget.md`) that
  told it what to do. An agent that got there by trial and error — guessing a port,
  opening a file under `app/` the book does not cite — is level 1: right outcome, wrong
  provenance.
- **Following a `- code:` citation is using the book, not going around it.** A `- code:`
  bullet is a route the book states, so an account that opens the file one names and
  reports what it found has read the book to its end, not shortcut past it — score it as
  cited, and say which bullet it followed. This is the same reading `rubric-disagree.md`
  applies, where checking a citation's digest is what a level-2 account is *required* to
  do. What makes the `absence` arm's level 0 different is not that source was read: it is
  that on that arm the book states no route to read, so an account naming `compose.yml`
  arrived there by going around the book rather than through it.
- When you are torn between two levels, pick the **lower** one.

## Evidence you must cite

A level of 1 or 2 requires at least one `evidence` entry, and each entry must be a **real,
repo-relative path** you actually opened while checking the account, e.g.
`docs/features/api-service/ops/api-service-stack.md`.

Your citations are checked against the filesystem. Any verdict whose cited paths do not
resolve is automatically capped at level 1 and reported as unproven, so a guessed path
costs you the score.

## Respond with

A single JSON object and nothing else:

```json
{
  "level": 2,
  "evidence": ["docs/features/api-service/ops/api-service-stack.md"],
  "reason": "one sentence, under 25 words, naming what the book shows or fails to show"
}
```
