story: none
date: 2026-11-21
elements: DryRunCoder
sources: workflows/src/workhorse_workflows/coder/book_qa/flow.py::BookQa

A recorded pass with no finding is replayed without the seat, because its calls are the exam after a developer fix.

A recorded finding is never replayed. A replay cannot tell a fixed defect from a standing one, because the defect is declared known in the book and the replay stays green either way. It sent the same finding back to the developer on every visit.

The seat judges each earlier finding again against the running app. The record is rewritten from what it reports, so a finding the app now meets leaves the record and one it still fails stays.
