---
type: flow
slug: settle-a-storys-markdown-answers
title: Settle a story's markdown answers
---
# Settle a story's markdown answers

- start: a story's spec directory holds a markdown Answer list, and a caller already runs
  Python rather than shelling out to `ostler`
- steps:
  - [settle-review-answers](../standalone-programs.md#settle-review-answers)
- end: the caller gets back which filed findings are fixed, which are declined and why, which
  are still open, and one error per heading that answers none of them
- verify: json_path(path="fixed[0]", equals="F1")
- verify: json_path(path="open[0]", equals="F3")
- fixture: [answer settlement scratch repo](../fixtures/answer-settlement-scratch-repo.md)
- detail: [The Ostler facade and book utilities](../concepts/the-ostler-facade-and-book-utilities.md)
