---
type: flow
slug: walkthrough-web
title: Web walkthrough flow
---
# Web walkthrough flow

The standalone web walkthrough reads a service's OKF book, starts the documented application and
shared CDP browser, walks one pending journey or screen per agent turn, records discoveries, and
reaps the processes on every terminal path. It is also handed a complete book by the main
OKF-builder machine.

- start: the service book is available and its graph contains at least one screen surface
- verify: count(subject="web walkthrough screen-surface gate", equals=1)
- steps:
  - [setup](../concepts/okf-builder-web-walkthrough.md#setup)
  - [start](../concepts/okf-builder-web-walkthrough.md#start)
  - [pick](../concepts/okf-builder-web-walkthrough.md#pick)
  - [walk](../concepts/okf-builder-web-walkthrough.md#walk)
  - [mark](../concepts/okf-builder-web-walkthrough.md#mark)
  - [checkpoint](../concepts/okf-builder-web-walkthrough.md#checkpoint)
  - [finish](../concepts/okf-builder-web-walkthrough.md#_finish)
- end: the walkthrough has either confirmed the book clean or left pending findings, and every app and browser process started by this run has been reaped
- verify: count(subject="web walkthrough process teardowns", equals=1)
- detail: [OKF-builder web walkthrough](../concepts/okf-builder-web-walkthrough.md)
- tests: `workflows/tests/okf_builder/test_workflow.py::test_an_empty_book_is_filled_top_down_from_the_code_s_surfaces`
