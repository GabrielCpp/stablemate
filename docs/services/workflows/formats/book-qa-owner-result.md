---
type: format
slug: book-qa-owner-result
title: Book QA owner result
---
# Book QA owner result

The verdict the book seat reports on its story, rendered by `qa-book.md`. The flow plays the calls the
seat names and gates these claims before it believes them.

- file: none — agent reply and checkpoint value
- config: `BookQaOwnerResult` agent-turn output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/book_qa.py::BookQaOwnerResult` @1a67f68b46f2
- detail: [coder book QA flow](../flows/coder-book-qa.md)
- detail: [coder book qa package](../concepts/coder-book-qa-package.md)

## Fields

### status

- type: literal `passed`, `findings`, or `blocked`
- required: true
- semantics: `passed` when every claim a call can show is stated by the book and the targeted run of the touched calls exits 0 with nothing for the developer to fix
- verify: json_path(path="$.status", equals="passed")
- semantics: `findings` when the app does not do what a claim says, with each such claim one entry in `findings`
- verify: json_path(path="$.status", equals="findings")
- semantics: a `findings` reply that lists no finding goes back to the seat
- semantics: `blocked` only when the base run was red or the environment was not healthy, and the seat repairs nothing there
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/book_qa.py::BookQaOwnerResult.status` @cea015dcbd7e

### notes

- type: `str`
- default: empty string
- required: false
- semantics: what the seat played and edited
- semantics: the claims no call can show, with the reason for each
- semantics: on `blocked`, the output that stopped the seat
- verify: json_path(path="$.notes", equals="Played three calls and brought the book up to the story.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/book_qa.py::BookQaOwnerResult.notes` @cea015dcbd7e

### findings

- type: list of `QaFinding`
- default: empty list
- required: false
- semantics: one entry per claim of the story the app does not meet, with the claim in the story's words, the call, and the answer the app gave
- verify: json_path(path="$.findings[0].target", equals="services/app")
- semantics: empty on `passed` and on `blocked`
- verify: json_path(path="$.findings", equals="[]")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/book_qa.py::BookQaOwnerResult.findings` @cea015dcbd7e

### calls

- type: list of `ServiceCalls`, each with a `service` name and a `calls` list of the book's call names
- default: empty list
- required: false
- semantics: the calls the seat played, per covered service, which are exactly the calls the flow plays
- semantics: a call left out is never judged
- verify: json_path(path="$.calls[0].service", equals="app")
- semantics: at least one call is named for every covered service, or the flow sends the seat back before any play
- verify: json_path(path="$.calls[0].calls[0]", equals="create-link")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/book_qa.py::BookQaOwnerResult.calls` @cea015dcbd7e
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/book_qa.py::ServiceCalls` @5a9ef6a7352e

### unreached

- type: list of `str`
- default: empty list
- required: false
- semantics: the story's claims the seat could not state in the book, one per entry, in the story's words
- semantics: a claim the seat stated and played is not listed
- semantics: the scenario QA reads the list and still covers each claim by a scenario or reports it out of reach, because the book judged nothing about it
- verify: json_path(path="$.unreached[0]", equals="no request reaches the report service")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/book_qa.py::BookQaOwnerResult.unreached` @cea015dcbd7e
