Judge whether the stories deliver the whole epic, at a size a coder can build and QA can assess.

- Completeness: every part of the epic's stated scope and acceptance is reflected in some story, not only every seed id tagged mechanically. Name the scope described in `epic.md` that no story delivers.
- Granularity: no story is so coarse that it cannot be implemented and assessed on its own (the "restore everything" story). Recommend the split.
- The opposite defect: a story with no concrete deliverable, whose work is only "verify already-built X matches" with nothing it changes or creates. That belongs as acceptance on the story that builds X. Recommend the merge.
- Assessability: each story is scoped so that acceptance and a QA method can be written for it, and names a concrete deliverable on a nameable surface. Judge the scope (title and the seeds it covers), not the body. A story scoped as "improve the experience" is untestable whatever is written into it later.
- Deferral ownership: nothing the stories put out of scope is left unowned. The deterministic gate sees only edges that exist. You see scope the stories describe as somebody else's, such as "the export flow is handled elsewhere" or "auth is out of scope here", with no sibling story or milestone-backed epic that owns it. An orphaned surface is the blank-screen failure. Name it so the split gives it an owner.
