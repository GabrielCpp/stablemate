---
type: concept
slug: coder-dev-phase-turns
title: Coder dev phase turns
---
# Coder dev phase turns

The dev owner works one story in three phases on one conversation: plan, build and review. Each
phase is its own turn with its own brief, so each turn reads only the procedure it runs. The
plan turn makes every design call on the strongest model. The build and review turns follow
that plan on a cheaper model, and they put each design call they still meet to an `advisor`
delegate on the strongest model. A turn that continues a phase on the same conversation reads a
short note instead of the brief again. The brief stays on disk, so a turn that lost it to a
compaction reads it back. The rules that hold for the whole story travel once per conversation,
in the brief that opened it. A later phase on the same conversation names that brief's path
instead of repeating them. The review's own procedures, the reviewer's brief and the answer
file's format, sit in files beside the review brief, and the brief names their paths.

- code: `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev._turn` @fe195e40d574
- code: `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev._power` @fe195e40d574
- code: `workflows/src/workhorse_workflows/coder/shared/counsel.py::__all__` @b3beecb6b7d6
- rule: the plan, build and review phases run in that order, each as its own turn, on the story's one conversation
- rule: the plan turn runs on the `max` power tier, because every design call the story needs is made there
- rule: the build and review turns run on the `high` power tier only when the turn is offered an `advisor` delegate, and on `max` otherwise, so a cheaper owner never makes a design call alone
- rule: a story QA sent back starts at the review phase, because its plan and build already exist
- rule: every repair lap the checks send back lands in the review phase, never in build
- rule: an operator answer to a block returns to the phase that raised it
- rule: a phase opens with its full brief when the story's conversation is new or is not the one that phase last ran on, and with the short follow-up note otherwise
- rule: the full brief of each phase is written to disk before its turn, and the follow-up note names that file, so a turn that no longer holds the brief reads it again
- rule: the story's standing rules (its standards and branch, its scope and when to block, its status line, its commit footers, the services it changes and the follow-up it works) go only into the brief that opened the conversation, and every later phase brief on that conversation names the opening brief's path instead
- rule: the opening brief is the earliest phase briefed on the story's current conversation, so the brief it names always carries the full rules
- rule: a conversation the engine starts again opens with its phase's full brief and the full rules, and that full brief replaces the phase's brief on disk, so a later phase on the new conversation names a brief that carries them
- rule: the review turn's reviewer brief and answer-file format are rendered with the turn's own values and written beside the review brief before the turn, and the review brief names both paths instead of carrying their text
- rule: those procedure files ship in the workflows package, not in the base library, because one package dispatches them and its behaviour must not depend on an optional install
- rule: when an advisor is offered, a build departure from the plan with no advice is sent back to the build as a repair lap
- rule: when an advisor is offered, a declined review finding with no consult on file is reopened and sent back to the review as a repair lap
- rule: the advisor reads the paths it is handed and answers one question, and it never edits a file
- rule: a review turn's result lists only what a reviewer it ran in that turn reported, and a finding filed before the turn is answered in the answer file and never listed again, because the flow files every listed finding as a new one and merges the older open finding of the same cause into it, which leaves the answer the turn wrote attached to a finding that is no longer open
- prefers: the follow-up note over a full brief on a continued phase, because the conversation already holds the brief and resending it costs a full prompt per lap
- prefers: a pointer to the opening brief over repeating the story's rules in each phase brief, because the conversation already holds them and the pointer keeps each brief near one screen of reading
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_fresh_story_runs_plan_build_and_review_in_that_order`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_failed_check_reenters_review_and_not_build`
- tests: `workflows/tests/coder/dev/test_flow.py::test_an_operator_answer_on_a_build_block_returns_to_build`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_departure_without_advice_sends_the_build_back_when_an_advisor_is_offered`
- tests: `workflows/tests/coder/dev/test_flow.py::test_without_an_advisor_a_departure_passes_and_every_phase_runs_at_max`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_decline_with_no_consult_is_reopened_and_named_when_an_advisor_is_offered`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_decline_with_a_consult_on_file_stays_declined`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_later_turn_of_a_phase_on_the_same_conversation_sends_only_the_follow_up_note`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_conversation_other_than_the_briefed_one_opens_with_the_full_brief_again`
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_plan_turn_on_a_fresh_conversation_carries_the_full_rules`
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_build_turn_on_the_plans_conversation_points_at_the_opening_brief`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_rebrief_renders_the_full_rules_and_rewrites_the_brief_on_disk`
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_first_review_turn_writes_the_reviewer_files_beside_its_brief`
- tests: `workflows/tests/coder/test_status_line_ownership.py::test_a_primed_brief_points_at_the_opening_brief_instead`
- detail: [coder development flow](../flows/coder-dev.md)
- detail: [coder dev package](coder-dev-package.md)
- detail: [coder conversation lifecycle](coder-conversation.md)
- detail: [agent backends](../../workhorse/concepts/agent-backends.md)

## Methods

### counsel_path
- sig: `counsel_path(state_dir: Path, work_id: str) -> Path`
- does: names the file a work item's advisor consults are kept in
- verify: json_path(path="$.path", matches=".+/counsel/[^/]+\\.json$")
- returns: `<state_dir>/counsel/<work_id>.json`, with each `/` in the id written as `__`
- verify: json_path(path="$.path", matches="__")
- code: `workflows/src/workhorse_workflows/coder/shared/counsel.py::counsel_path` @b3beecb6b7d6
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_decline_with_no_consult_is_reopened_and_named_when_an_advisor_is_offered`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_decline_with_a_consult_on_file_stays_declined`

### record_consults
- sig: `record_consults(state_dir: Path, work_id: str, consults: list[Consult]) -> None`
- does: keeps each consult under its finding id, a later consult on the same finding replacing the earlier one
- verify: json_path(path="$.consults.review-1\\.1.question", equals="example question")
- does: writes nothing when the review reported no consult
- verify: count(subject="counsel files written for an empty list", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/counsel.py::record_consults` @b3beecb6b7d6
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_decline_with_no_consult_is_reopened_and_named_when_an_advisor_is_offered`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_decline_with_a_consult_on_file_stays_declined`

### consulted
- sig: `consulted(state_dir: Path, work_id: str) -> set[str]`
- does: lists the finding ids with a consult on file, which the settlement checks every decline against
- verify: count(subject="consulted finding ids", equals=1)
- returns: the set of finding ids, empty when the file is missing or unreadable
- verify: json_path(path="$.consulted", equals="[]")
- code: `workflows/src/workhorse_workflows/coder/shared/counsel.py::consulted` @b3beecb6b7d6
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_decline_with_no_consult_is_reopened_and_named_when_an_advisor_is_offered`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_decline_with_a_consult_on_file_stays_declined`
