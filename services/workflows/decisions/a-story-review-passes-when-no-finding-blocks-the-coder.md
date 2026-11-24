story: none
date: 2026-11-24
elements: DryRunAuthor
sources: workflows/src/workhorse_workflows/author/pm/flow.py::PMReview, workflows/src/workhorse_workflows/author/draft/flow.py::DraftLoop

A review of a story passes when no finding blocks the coder. Every finding carries a weight, `blocking` or `note`, and a finding with no weight is blocking. An angle fails only on a blocking finding. A passed angle may list notes.

A blocking finding says a coder who builds from the story as written would build the wrong behaviour, would take a product or UX decision the story leaves open, or would meet a contradiction with the book, the epic or the mockup. Anything else is a note. The review passes when every angle passed, and its notes keep every finding, blocking or not, with each note line marked `(note)`.

A pass with notes ends the draft without a rework or a second review. The draft loop logs the notes with the subject.

The reviewer never targets a story's `## Dependencies` section, which belongs to the story split, or its `## Fixtures` section, which belongs to the coder. The writer is told to leave both alone. A defect repairable only there is repaired in Context or the acceptance criteria, or it is not a finding.

One authored milestone of 42 stories showed why. None of 44 fresh product-manager reviews passed, because one finding on any of five angles failed the review and findings had no weight. 42 of 71 re-reviews passed. Every story paid at least two reviews and one rework. 15 third laps came from findings that asked the writer to edit a section it may not touch.
