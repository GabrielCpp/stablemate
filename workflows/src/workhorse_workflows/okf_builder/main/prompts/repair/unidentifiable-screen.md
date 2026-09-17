### `unidentifiable-screen` — nothing can say which page the scenario ended on

A scenario that ends on a screen photographs it and hands the picture to `ostler vet`, which
files every placement verdict under the screen the book named. The only thing a reader of a
rendered page has to go on to say *which* screen it is looking at is that screen's `route:`,
compared against the URL the browser is showing. This screen's `route:` cannot be compared: it
names a family of pages (`/links/:id/edit`, `/policies/{id}`), or the file states none, or the
file states two and neither one can be the answer.

So no vet is compiled. Grading the page anyway would produce a full set of verdicts about a
correspondence nobody established — every one of them a pass or a fail concerning a screen the
book may not describe, which is worse than no verdict at all.

The repair is on the screen node, and which one is a question about the screen:

- **The file documents one screen and its route is parameterised.** That is not a defect in
  itself — a screen genuinely at `/policies/{id}` is one screen — but a vet needs a page it can
  identify. Give the journey a concrete end: point the flow's `end:` (or the check's
  `locator=`) at a screen whose `route:` is a literal path, or split the parameterised screen so
  the state the journey actually ends in has its own documented address.
- **The file documents two screens.** Split it. Each screen is its own `.md` under
  `docs/features/<surface>/gui/screens/`, with one `route:` bullet. Two `route:` values in one
  file is two destinations wearing one identity, and everything downstream — reachability, the
  navigation walk, the vet — has to guess which one it is holding.
- **The file states no `route:` at all.** Add one. `route:` is required on every `screen`, and a
  screen with no address is not something a walk can arrive at or a reader can recognise.

Do not repair this by deleting the flow's `verify:` or by pointing the check at a different
screen than the journey ends on. The check's subject is where the claim is observed; moving it
somewhere convenient files the evidence under the wrong book.
