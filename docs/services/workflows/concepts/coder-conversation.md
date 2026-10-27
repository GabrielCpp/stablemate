---
type: concept
slug: coder-conversation
title: Coder conversation lifecycle
---
# Coder conversation lifecycle

The Coder lanes use a story-derived conversation key to carry implementation context between
development, review application, and QA repair turns. A lane derives the key from the story slug
instead of accepting a session identifier, so a handoff can resume only the conversation in its
own run directory; a standalone lane starts cold when that chain is absent. The dev flow also keeps
each phase brief on disk with a ledger of the conversation each phase last ran on, so a phase that
continues on the same conversation reads a short note instead of its brief. Turn counts and recycling belong to
the owning flow.

- code: `workflows/src/workhorse_workflows/coder/shared/conversation.py::__all__` @ee9075d1870c
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
- code: `workflows/src/workhorse_workflows/coder/shared/conversation.py::story_chain` @ee9075d1870c
- tests: `workflows/tests/coder/test_session_chains.py::test_every_lane_names_the_same_conversation_without_being_handed_anything`

### backbone
- sig: `backbone(flow: Workflow) -> str`
- does: reads the story slug from the flow context
- verify: json_path(path="$.story_slug", equals="acme-story")
- does: returns the story conversation key used by the flow's primary turns
- verify: count(subject="flow backbone conversation keys", equals=1)
- returns: the `story:<ctx.story_slug>` key
- verify: json_path(path="$.chain", matches="^story:[^:]+$")
- code: `workflows/src/workhorse_workflows/coder/shared/conversation.py::backbone` @ee9075d1870c
- tests: `workflows/tests/coder/test_session_chains.py::test_every_lane_names_the_same_conversation_without_being_handed_anything`

### brief_dir
- sig: `brief_dir(state_dir: Path, work_id: str) -> Path`
- does: names the directory a work item's phase briefs and their ledger are kept in
- verify: json_path(path="$.path", matches=".+/briefs/[^/]+$")
- returns: `<state_dir>/briefs/<work_id>`, with each `/` in the id written as `__`
- verify: json_path(path="$.path", matches="__")
- code: `workflows/src/workhorse_workflows/coder/shared/conversation.py::brief_dir` @ee9075d1870c
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_later_turn_of_a_phase_on_the_same_conversation_sends_only_the_follow_up_note`

### brief_ledger
- sig: `brief_ledger(state_dir: Path, work_id: str) -> dict[str, str]`
- does: reads which conversation id each phase's last turn ran on
- verify: json_path(path="$.ledger.review", equals="session-1")
- returns: the phase-to-conversation map, or an empty map when the ledger is missing, unreadable or not a map
- verify: json_path(path="$.ledger", equals="{}")
- code: `workflows/src/workhorse_workflows/coder/shared/conversation.py::brief_ledger` @ee9075d1870c
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_later_turn_of_a_phase_on_the_same_conversation_sends_only_the_follow_up_note`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_conversation_other_than_the_briefed_one_opens_with_the_full_brief_again`

### record_brief
- sig: `record_brief(state_dir: Path, work_id: str, phase: str, session: str) -> None`
- does: records that the phase's last turn ran on the given conversation, keeping every other phase's entry
- verify: json_path(path="$.ledger.build", equals="session-1")
- code: `workflows/src/workhorse_workflows/coder/shared/conversation.py::record_brief` @ee9075d1870c
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_later_turn_of_a_phase_on_the_same_conversation_sends_only_the_follow_up_note`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_conversation_other_than_the_briefed_one_opens_with_the_full_brief_again`

### reset_briefs
- sig: `reset_briefs(state_dir: Path, work_id: str) -> None`
- does: removes the work item's briefs and ledger, so each phase opens with its full brief again
- verify: removed(subject="the work item's brief directory")
- code: `workflows/src/workhorse_workflows/coder/shared/conversation.py::reset_briefs` @ee9075d1870c

### needs_brief
- sig: `needs_brief(ledger: dict[str, str], phase: str, session: str) -> bool`
- does: decides whether a phase opens with its full brief or with the follow-up note
- verify: json_path(path="$.needs_brief", equals=true)
- returns: true when the story has no conversation yet or the phase last ran on a different one, false otherwise
- verify: json_path(path="$.needs_brief", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/conversation.py::needs_brief` @ee9075d1870c
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_later_turn_of_a_phase_on_the_same_conversation_sends_only_the_follow_up_note`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_conversation_other_than_the_briefed_one_opens_with_the_full_brief_again`
