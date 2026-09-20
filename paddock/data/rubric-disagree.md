# Score one agent's attempt to say which one is wrong: the app, or the book

You are grading an agent's attempt to compare globex's web-app widget directory screen,
driven live in a browser, against what `docs/features/web-app/gui/screens/widget-list.md`
says about that same screen — using a browser MCP, its own reading of the book, and
nothing else it was told directly. On some trials the app's own source was edited so what
it renders no longer matches the book; on others the book's own prose was edited so it
states something the app does not do; on the rest, nothing was touched and the two agree.
You are told which arm this trial is and what the correct answer is; your job is to check
the agent's account against the book and the trial tree, not to rediscover the disagreement
yourself.

The one fact every arm turns on is the `new-widget-link` component's label — the text on
the link from the widget directory to the add-a-widget form. The book states it twice
(the component's own `- name:` bullet and the `open-new-widget` interaction's `- name:`
bullet), both citing the same `- code:` bullet, `app/web-app/static/index.html`
@ebed722d64ce. That citation's digest is the one fact in the trial that only ever answers
for the app, never the book: on `app-wrong` the app file changed and the digest no longer
matches it; on `book-wrong` the app file is untouched and the digest still matches it; on
`agree` both the text and the digest line up.

## The trial

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

- **Open the book and the app file before you score.** Read
  `docs/features/web-app/gui/screens/widget-list.md`'s `new-widget-link` component and
  `open-new-widget` interaction, and read `app/web-app/static/index.html`'s anchor text,
  to confirm what each actually states and renders under `{{repo}}`. Score what the trial
  tree shows, not what the expected answer alone tells you.
- **The verdict has three possible shapes, and only one is correct per arm.** "They
  agree" is correct only on `agree`. "The app is wrong" is correct only on `app-wrong`.
  "The book is wrong" is correct only on `book-wrong`. An agent that names the wrong side,
  or that reports a disagreement on `agree`, or agreement on either wrong arm, is level 0
  regardless of how well-argued its account otherwise reads.
- **The text mismatch alone is not enough for level 2 — the digest check is the point of
  this rubric.** On `app-wrong` and `book-wrong` the *same* text disagreement is
  observable ("Add a widget" vs. "Create a widget"), and a browser alone cannot tell you
  which side moved — only the `- code:` bullet's digest against the app file's contents
  can. A level-2 account must explicitly say it checked (or state the outcome of
  checking) whether `app/web-app/static/index.html`'s contents still match the
  `@ebed722d64ce` digest `widget-list.md`'s `- code:` bullet carries, and use that as part
  of how it knows which side is wrong. An account that only reports the text mismatch and
  guesses, asserts, or assumes which side is at fault without mentioning the digest — even
  if it happens to guess the correct side — is level 1, not level 2. On `agree`, level 2
  likewise expects the account to note that the digest matches, not just that the text
  does; an account that only notes the text matching is level 1.
- **A hedge is level 1, not level 2.** "The link text looks the same as the book states,
  I think they agree" without checking the digest is a hedge — level 1 if it happens to
  land on the correct verdict, level 0 if it does not.
- When you are torn between two levels, pick the **lower** one.

## Evidence you must cite

A level of 1 or 2 requires at least one `evidence` entry, and each entry must be a **real,
repo-relative path** you actually opened while checking the account, e.g.
`docs/features/web-app/gui/screens/widget-list.md` or
`app/web-app/static/index.html`.

Your citations are checked against the filesystem. Any verdict whose cited paths do not
resolve is automatically capped at level 1 and reported as unproven, so a guessed path
costs you the score.

## Respond with

A single JSON object and nothing else:

```json
{
  "level": 2,
  "evidence": ["docs/features/web-app/gui/screens/widget-list.md", "app/web-app/static/index.html"],
  "reason": "one sentence, under 25 words, naming what the book, the app, and the digest show"
}
```
