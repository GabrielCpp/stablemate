---
type: format
slug: book-qa-record
title: Book QA record
---
# Book QA record

The memory of one story's book pass. A passed check writes it, and a later visit of the lane for the
same story reads it, replays the calls and spends no seat turn unless that play disagrees. Its
meaning is in the [coder book qa package](../concepts/coder-book-qa-package.md) and the
[coder book QA flow](../flows/coder-book-qa.md).

- file: `book-qa.json` in the story's spec directory
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/book_qa.py::BookQaRecord` @245f6bf44ff0
- code: `workflows/src/workhorse_workflows/coder/book_qa/nodes.py::write_book_record` @309e7a3456e6
- code: `workflows/src/workhorse_workflows/coder/book_qa/nodes.py::read_book_record` @09e8b1009c6f
- detail: [coder book qa package](../concepts/coder-book-qa-package.md)
- detail: [coder book QA flow](../flows/coder-book-qa.md)
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_green_pass_plays_the_named_calls_records_them_and_lands_the_book`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_second_visit_replays_the_recorded_calls_with_no_seat`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_green_replay_over_a_recorded_finding_sends_it_back_again`

The file is JSON, indented by two spaces, with a trailing newline. It omits any key that holds its
default. A story with no file has an empty record, and an empty `services` list means no first visit
has passed.

## Fields

### services

- type: list of objects, each with `service` and `calls`
- default: empty list
- required: false
- semantics: for each covered service, the calls a passed check played, by the names the book gives them
- verify: json_path(path="$.services[0].service", equals="app")
- semantics: a second visit plays exactly these calls
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/book_qa.py::BookQaRecord.services` @97b65ee8ad1c

### findings

- type: list of `QaFinding`
- default: empty list
- required: false
- semantics: the findings the passed check stood on
- semantics: a green replay over them returns them again as a `refix`, because each declared defect still holds
- verify: json_path(path="$.findings[0].issue", equals="the link answers 200 where the story says 404")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/book_qa.py::BookQaRecord.findings` @97b65ee8ad1c
