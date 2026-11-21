story: none
date: 2026-11-21
elements: DryRunCoder
sources: workflows/src/workhorse_workflows/coder/book_qa/flow.py::BookQa, workflows/src/workhorse_workflows/coder/main/flow.py::Coder

The QA of a story a service book covers has four steps. The selection matches the story's diff against the book. The
stack copy comes up. The workflow plays what the selection picked. Then the end review, one agent turn, reads what
the plays left.

The review runs once, after every play passed and before the books are stamped verified. It reads the story's
acceptance criteria, functional and non-functional, numbered by the workflow. It reads `qa-plan.md`, the play
reports, the earlier evidence in the spec folder with its date and commit, and the repository's own tests. It also
reads the claims the book could not state. It may run one bounded check per item, never a whole dataset, a whole
book or production.

Each criterion gets one verdict: played, tested, recorded, checked, unobserved or unmet. Only unmet returns the story
to its developer, and then no book is stamped. Unobserved passes the story, and the workflow records it in
`qa-review.md` and `book-qa.json` for an operator to read. A review that gives no verdict for a criterion gets one
more turn, then the operator is asked.

The review has `review_minutes`, 20 unless the launch says otherwise. A review cut at that mark keeps its
conversation, and the lane asks the operator.

The coder enters the scenario QA only when no service of the story has an executable book. A story whose books
judged it goes from the review to the commit, and a leftover after it is proven again by the books.
