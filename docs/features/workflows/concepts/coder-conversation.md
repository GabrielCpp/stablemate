---
type: concept
slug: coder-conversation
title: Coder conversation lifecycle
---
# Coder conversation lifecycle

The Coder lanes use a story-derived conversation key to carry implementation context between
development, review application, and QA repair turns. A lane derives the key from the story slug
instead of accepting a session identifier, so a handoff can resume only the conversation in its
own run directory; a standalone lane starts cold when that chain is absent. Turn counts and recycling belong to
the owning flow.

- code: `workflows/src/workhorse_workflows/coder/shared/conversation.py::__all__` @6b1880f7b0e9
- detail: [coder shared library](coder-shared-library.md)

## Methods

### story_chain
- sig: `story_chain(slug: str) -> str`
- does: derives the shared conversation key from the story slug alone
- verify: json_path(path="$.chain", matches="^story:.+")
- does: gives every Coder lane the same key for the same story
- verify: count(subject="lanes sharing one story conversation key", equals=1)
- returns: `story:<slug>`
- verify: json_path(path="$.chain", matches="^story:[^:]+$")
- code: `workflows/src/workhorse_workflows/coder/shared/conversation.py::story_chain` @6b1880f7b0e9
- tests: `workflows/tests/coder/test_session_chains.py::test_every_lane_names_the_same_conversation_without_being_handed_anything`

### backbone
- sig: `backbone(flow: Workflow) -> str`
- does: reads the story slug from the flow context
- verify: json_path(path="$.story_slug", equals="acme-story")
- does: returns the story conversation key used by the flow's primary turns
- verify: count(subject="flow backbone conversation keys", equals=1)
- returns: the `story:<ctx.story_slug>` key
- verify: json_path(path="$.chain", matches="^story:[^:]+$")
- code: `workflows/src/workhorse_workflows/coder/shared/conversation.py::backbone` @6b1880f7b0e9
- tests: `workflows/tests/coder/test_session_chains.py::test_every_lane_names_the_same_conversation_without_being_handed_anything`
