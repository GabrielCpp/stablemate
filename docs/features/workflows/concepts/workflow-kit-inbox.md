---
type: concept
slug: workflow-kit-inbox
title: Workflow kit run inbox
---
# Workflow kit run inbox

The workflow kit provides the shared polling contract used by author and coder loop heads.
It reads the run-scoped inbox, handles at most one outstanding message per poll, and replies to
that message before returning it so the same operator note cannot trigger another rework pass.
The inbox file name and message storage format belong to Workhorse's inbox adapter rather than
this workflow package. The author loop acknowledges a consumed note as `folded into a story
rework`; the coder review loop acknowledges it as `folded into a rework pass`.

- code: `workflows/src/workhorse_workflows/kit/inbox.py::poll_run_inbox`
- tests: `workflows/tests/author/test_workflow.py::test_an_operator_note_dropped_mid_run_reworks_the_story_once`
- tests: `workflows/tests/coder/review/test_flow.py::test_dropped_feedback_buys_exactly_one_rework_pass`

## Methods

### poll_run_inbox

- sig: `poll_run_inbox(run_dir: str, *, reply_text: str) -> tuple[str, str] | None`
- does: returns `None` without polling when `run_dir` is empty
- verify: count(subject="empty run-directory poll results", equals=1)
- does: returns `None` when the run inbox has no outstanding messages
- verify: count(subject="empty inbox poll results", equals=1)
- does: resolves the inbox path by appending the adapter-provided inbox filename to `run_dir`
- verify: count(subject="run-scoped inbox paths", equals=1)
- does: asks the Workhorse inbox adapter for outstanding messages at the resolved path
- verify: count(subject="outstanding inbox polls", equals=1)
- does: selects the first outstanding message, which is the oldest message in adapter order
- verify: count(subject="selected oldest outstanding messages", equals=1)
- does: replies to the selected message id with `reply_text` and a current UTC ISO timestamp
- verify: removed(subject="oldest outstanding inbox message")
- does: reads the selected message body and returns it together with its normalized scope
- verify: count(subject="returned inbox message and scope pair", equals=1)
- does: preserves `story` and `epic` scopes and maps every missing or other scope value to `story`
- verify: count(subject="normalized inbox scope values", equals=2)
- returns: the selected message as `(body, scope)` after acknowledging it
- verify: count(subject="returned inbox message pairs", equals=1)
- returns: `None` when no message is available
- verify: count(subject="no-message return values", equals=1)
- code: `workflows/src/workhorse_workflows/kit/inbox.py::poll_run_inbox`
- tests: `workflows/tests/author/test_workflow.py::test_an_operator_note_dropped_mid_run_reworks_the_story_once`
- tests: `workflows/tests/coder/review/test_flow.py::test_dropped_feedback_buys_exactly_one_rework_pass`
