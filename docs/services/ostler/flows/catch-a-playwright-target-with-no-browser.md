---
type: flow
slug: catch-a-playwright-target-with-no-browser
title: Catch a playwright target with no browser
---
# Catch a playwright target with no browser

- start: a plan declares a target whose driver is `playwright`, and the sandbox a run executes
  in has no browser for ostler to open
- steps:
  - [ostler qa run](../qa.md#ostler-qa-run-playwright-target)
- end: the run fails before the scenario's own body ever decides anything, because opening the
  browser is itself the dispatch a `driver="playwright"` target buys — there is no separate step
  where a scenario author could have caught this first
- verify: exit_status(code=1)
- fixture: [qa scratch repo](../fixtures/qa-scratch-repo.md)
- fixture: [qa browser scratch plan](../fixtures/qa-browser-scratch-plan.md)
- detail: [Running and reporting a QA run](../concepts/running-and-reporting-a-qa-run.md)
