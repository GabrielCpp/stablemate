---
type: flow
slug: compile-a-web-journey-plan
title: Compile a web journey plan
---
# Compile a web journey plan

- start: a screen's interaction and the state it leads to both changed production code on a
  `driver: web` surface
- steps:
  - [ostler qa context](../qa.md#ostler-qa-context-web-journey)
  - [ostler qa compile plan](../qa.md#ostler-qa-compile-plan-web-journey)
- end: the compiled plan holds a Playwright locator for the interaction's own component and a
  settle call for the state it walks into
- verify: exit_status(code=0)
- fixture: [qa web journey repo](../fixtures/qa-web-journey-repo.md)
