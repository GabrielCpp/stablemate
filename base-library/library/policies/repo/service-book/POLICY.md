---
name: service-book
description: "The standing rule for a repository that keeps a service book under services/: the book is read before the code for any what, why or how-do-I-reach-it question, through `ostler book search`, `explain` and `decisions` rather than grep, and a story is not done until the book states its behaviour, the decisions it settled are files beside the book, `ostler book check` passes and the book plays green on the story's code. A service that has no book yet gets one, written with the ostler-book skill."
---

## The book comes first

Each service has a book under `services/<name>/` under the book root: the repository
root in a monorepo, the artifacts folder in a multi-repo workspace. The book is
the current spec of the service. Its Python states what every endpoint, screen
and command does, which rule refuses a call, and which journeys a user lives
through. Ostler plays it against the running app. Its `decisions/` folder holds,
in markdown, why a behaviour is so and which story settled it.

Read the book before the code whenever the question is *what* something does,
*why* it is so, or *how a user reaches it*:

```bash
ostler book search <term> [--service services.<name>] [--kind rule|endpoint|interaction|action|journey|screen|decision|question]
ostler book explain services.<name> <ClassName>       # everything the book says of one element
ostler book decisions services.<name> [--story <id>]  # each decision and the story behind it
```

Read the code to learn *how it is implemented*. A grep over source that starts
before a search over the book re-derives what is already written down, and gets
it wrong wherever the code has a legacy twin the book would have steered you
away from. A story writer and an implementer both read the decisions a story
touches before they write.

## A story is done when the book plays it

A story is a delta. The book is the whole. The story is finished when the delta
is in the book in the same change as the code. In a multi-repo workspace that
change is two commits: the book's in the artifacts folder, the code's in its
repository. Finished means all of:

- Every record, rule, action, endpoint, screen and journey the story changed
  states the new current behaviour. Restructure the book when the story needs
  it. The structure a first pass chose is not a contract.
- Every assumption or tradeoff settled for the story, at the start or along the
  way, is a file under `services/<name>/decisions/`, or a line added to the
  decision that already covers it. A decision that lives only in a chat or a
  story file is lost to the next reader.
- Every `source=` pointer names code that exists:
  `ostler book check services.<name> --app <code repo root>` passes. A pointer into
  another repository is `repo://<member>/<path>`.
- `ostler book run services.<name>` is green on the story's code. A claim no
  call and no screen can observe is checked by the story's QA and stays out of
  the book.

Write the book with the `ostler-book` skill. It carries the format, the order of
work and the bar for each element.

## A service with no book yet

A service with no `services/<name>/service.py` has no book. Write one from its
source with the okf-book workflow, `workhorse-okf-book run python_book`, or by
hand with the `ostler-book` skill. The book is the only form of spec this
repository keeps.
