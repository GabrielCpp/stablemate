story: none
date: 2026-11-21
elements: DryRunCoder
sources: workflows/src/workhorse_workflows/coder/shared/provenance.py::story_change, workflows/src/workhorse_workflows/coder/book_qa/nodes.py::stamp_books_verified

A story's change is its own commits plus the uncommitted work, when a commit carries its trailer.
It is the range from the base when no commit carries it, or when the story's commits are the whole range.
The range is then the same change, read exactly.
The checks, the selection, the covered books, the clone check, the sentinel gate and the stamp all read it this way.
On a shared trunk, the range ran four services' gates for a one-service story.
It also made the seat write book pointers for code other stories wrote.
The stamp writes no verified commit while other commits leave code unnamed.
