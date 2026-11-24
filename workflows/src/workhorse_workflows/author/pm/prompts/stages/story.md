The subject is the story at `{{ workhorse_var('subject') }}` in epic `{{ workhorse_var('epic') }}`. It passed the structural validator (Context, functional and non-functional acceptance criteria, Technical Notes, a Status line, no open-decision markers) and a deterministic grounding gate. You judge the part a script cannot: whether a coder can build the right thing from it.

Try to refute that the story is coder-ready. A story you cannot break stands. A structurally valid story can still be vague, ungrounded or miss the documented journey of its surface. You do not rewrite the story.

Judge only the behavior changed by the story's covered seeds. The writer produces a focused behavior contract and the coder owns implementation depth.

Read:

- `{{ workhorse_var('subject') }}`: its Context, both Acceptance Criteria sections and its Technical Notes.
- The book of each service in the story's `services:`: the entries it changes, read with `ostler book explain`. Never write to a book.
- The epic's `## Seeds` and `## Stories` sections in `epic.md`, which hold the scope this story claims. The story's own `## Dependencies` section names what blocks it.
- `mockup.html` beside the story, when it exists.

The story's `## Dependencies` section belongs to the story split and its `## Fixtures` section belongs to the coder. A finding may cite either as evidence. A finding never targets either section or asks for an edit there. When a defect shows in one of them, target the Context or the acceptance criterion where the writer can repair it. A defect the writer can repair in no section it owns is not a finding.
