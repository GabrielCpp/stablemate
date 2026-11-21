story: none
date: 2026-11-21
elements: DryRunCoder
sources: workflows/src/workhorse_workflows/coder/shared/resolution.py::resolver_args, workflows/src/workhorse_workflows/coder/book_qa/prompts/qa-review.md

A rule above any one service lives in `business/<slug>.md` beside `services/`, and the coder's turns read it before they judge or write. The spec turn and the dev turns read every page under `business/` with the decisions of each covered service, and use its words. The book turn and the end review search the pages and the decisions by kind for the main nouns of the story. A criterion that contradicts a page is reported as such, never silently judged.

The operator's resolver treats the pages and the decisions as standing decisions, ahead of the story. A question a page settles is not escalated and is not decided against the page. When the operator's answer states a rule that outlives the story, the resolver writes it as a business page in the same turn, with `sources: operator` and the date. An answer that explains one element becomes a line in that service's decision.
