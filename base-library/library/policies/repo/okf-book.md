---
name: okf-book
description: "The standing rule for a repository that carries an OKF book under docs/services/: the book is read before the code for any what, why or how-do-I-reach-it question, through `ostler search` and `ostler trace` rather than grep, and a story is not done until its delta is merged into the book, its citations restamped, the decisions it settled recorded as concept nodes, and `ostler doctor` raises nothing new on the pages it touched."
---

## The book comes first

This repository carries an OKF book under `docs/services/`. It is the current
spec of every service here: what each screen, command and endpoint does, the
concepts behind them, how a user reaches a surface, and which of two similar
things to use. It is indexed, so its size is no reason to skip it.

Read the book before the code whenever the question is *what* something is,
*why* it exists, or *how a user reaches it*:

```bash
ostler search <term> [--type concept|flow|endpoint|screen|command]
ostler trace <id|slug|path>     # walk the graph from a node
ostler reach <screen>           # the documented click-path
```

Read the code to learn *how it is implemented*. A grep over source that starts
before a search over the book re-derives what is already written down, and gets
it wrong wherever the code has a legacy twin the book would have steered you
away from.

## A story is done when the book says so

A story is a delta. The book is the whole. The story is not finished until the
delta is merged into the book in the same change as the code, which means all of:

- Every node whose behaviour changed describes the new current reality
  completely. Never "this story added X".
- Every file a `code:` bullet cites and the change touched is restamped:
  `ostler stamp --node <id>`.
- Every assumption or tradeoff settled for the story, at the start or along the
  way, is a `concept` node with a `rule:` bullet, or a `rule:` added to the
  concept that already covers it. A decision that lives only in a chat or a
  story file is lost to the next reader.
- `ostler doctor` raises no finding on a page the change touched that was not
  there before the change.

Author through `ostler scaffold`, `ostler fmt` and `ostler doctor`, never by
hand-writing frontmatter or a `docs/services/` path. The `ostler-okf` skill
carries the per-type bar and the merge procedure.
