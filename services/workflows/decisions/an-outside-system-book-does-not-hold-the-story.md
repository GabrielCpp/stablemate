story: none
date: 2026-11-24
elements: DryRunCoder
sources: workflows/src/workhorse_workflows/coder/book_qa/flow.py::BookQa

Book QA selects no play for a book that describes an outside system. The story's QA turn plays that system against the
stack, and a play against the live system after shipping shows whether the stack still holds. A story that changes a
shared part of such a book owes those paths to the scheduled whole play, and the QA plan lists them. The plays gate
does not count them, so a story that edits an outside-system book is not sent back for plays it can never select.
