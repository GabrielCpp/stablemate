---
name: service-book
description: "The standing rule for a repository that keeps a service book under services/: the book is read before the code for any what, why or how-do-I-reach-it question, through `ostler book search`, `explain` and `decisions` rather than grep, and a story is not done until the book states its behaviour, the decisions it settled are files beside the book, `ostler book check` passes and the book plays green on the story's code. A service that has no book yet gets one, written with the ostler-book skill."
---

## The book comes first

Each service has a book under `services/<repo>/<name>/` in the artifacts folder, or
`services/<name>/` in a repository that keeps its book (`book.home: repo`). Below,
`<module>` is `services.<repo>.<name>` or `services.<name>`. The book's Python
states what every endpoint, screen and command does, which rule refuses a call, and
which journeys a user lives through. Its `decisions/` folder says why. Read the book
before the code whenever the question is *what* something does, *why* it is so, or
*how a user reaches it*:

```bash
ostler book search <term> [--service <module>] [--kind rule|endpoint|interaction|action|journey|screen|decision|company|team|product|question|event|outside]
ostler book explain <module> <ClassName>       # everything the book says of one element
ostler book decisions <module> [--story <id>]  # each decision and the story behind it
ostler book pages [--level company|team|product]      # the pages above every service, one line each
```

A grep over source that starts before a search over the book gets it wrong wherever
the code has a legacy twin. Read the code to learn *how it is implemented*. A story
writer and an implementer both read the decisions a story touches before they write.

Four books hold the rules: service, product, team and company. Agents write service
and product pages. People write team and company pages. When two disagree the order
of authority is company, team, product, service decision, story. Report a conflict
and settle neither side.

## A story is done when the book plays it

The story's delta lands in the book in the same change as the code. Finished means
all of:

- Every element the story changed states the new current behaviour.
- Every assumption or tradeoff settled for the story is a file under the
  book's `decisions/`, or a line in the decision that already covers it.
- `ostler book check <module> --app <code repo root>` passes.
- `ostler book run <module>` is green on the story's code.

A service with no book gets a book first, from the okf-book workflow
(`workhorse-okf-book run python_book`) or by hand. The `ostler-book` skill carries
where the book lives, how its branch lands, the format and the bar.
