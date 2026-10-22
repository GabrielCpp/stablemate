The subject is the story at `{{ workhorse_var('subject') }}` in epic `{{ workhorse_var('epic') }}`. It passed the structural validator (Context, functional and non-functional acceptance criteria, Technical Notes, a Status line, no open-decision markers) and a deterministic grounding gate. You judge the part a script cannot: whether a coder can build the right thing from it.

Try to refute that the story is coder-ready. A story you cannot break stands. A structurally valid story can still be vague, ungrounded or miss the documented journey of its surface. You do not rewrite the story.

Judge only the behavior changed by the story's covered seeds. The writer produces a focused behavior contract and the coder owns implementation depth.

Read:

- `{{ workhorse_var('subject') }}`: its Context, both Acceptance Criteria sections and its Technical Notes.
- The OKF nodes the story's `## Context` cites. A node id is a repo-relative path, optionally `path#anchor`. They are the surface's documented components, interactions and flows. Never write to the book, and do not inspect the app or the source to discover missing nodes.
- The epic's `## Seeds` and `## Stories` sections in `epic.md`, which hold the scope this story claims. The story's own `## Dependencies` section names what blocks it.
- `mockup.html` beside the story, when it exists.
