---
type: concept
slug: author-story-author-subflow
title: Author story-author subflow
---
# Author story-author subflow

The `story_author` package is the directly invokable Author subflow for one explicitly selected
story. It resolves and scaffolds that story, optionally designs a story-local mockup, delegates
story writing turns, validates structure and feature-book grounding, hands the story to the
[PM review](author-pm-review.md), and handles feedback, bounded rework, and PM answers. A passing
run records a [PM receipt](../formats/pm-receipt.md) beside the story. It does not select another story, create a branch, or commit changes. The parent
Author dispatcher hands it one epic/story pair and resumes planning after the returned completion
value; it does not let this subflow choose a different queued item.

The workflow inputs are `epic`, `story`, optional `feedback_dir`, and an optional `note` that
carries an earlier answer into the writer's prompt. Preparation always trims the epic and story
slugs, resolves the story only inside that epic, and performs the idempotent missing-section
scaffold before any agent turn. Writing and rework are retried through the structural and
grounding checks and the PM review. A story gets at most three reworks and at most two PM answers
to the writer's questions. Exhausting either budget returns a `blocked` completion, and the Author
flow keeps the story's row blocked for the completion gate.

The [author workflow composition root](author-workflow-composition-root.md) registers the flow and
its package-local blueprint. Its state-machine contract is the [author story-author flow](../flows/author-story-author.md).
The three agent-facing templates are specified in [author story-author prompt contracts](author-story-author-prompt-contracts.md).

- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor` @2336f43d893e
- code: `workflows/src/workhorse_workflows/author/story_author/nodes/_blueprint.py::blueprint` @941c0efdf281
- tests: `workflows/tests/author/story_author/test_flow.py::test_flow_prepares_explicit_story_before_authoring_without_git_side_effects`
- tests: `workflows/tests/author/story_author/test_flow.py::test_a_story_with_a_ui_service_and_no_mockup_ends_blocked_before_it_is_written`
- detail: [author story-author prompt contracts](author-story-author-prompt-contracts.md)
- detail: [author PM review](author-pm-review.md)
- detail: [author PM gap answer](author-pm-gap-answer.md)

## Methods

### blueprint
- sig: `Blueprint("author-story-author") -> Blueprint`
- does: provides the registration target for deterministic story-author nodes
- returns: returns a blueprint named `author-story-author`
- verify: json_path(path="$.name", equals="author-story-author")
- code: `workflows/src/workhorse_workflows/author/story_author/nodes/_blueprint.py::blueprint` @941c0efdf281

### setup
- sig: `setup() -> Config`
- does: loads author configuration in `story-author` mode
- verify: count(subject="story-author configuration loads", equals=1)
- returns: returns the resolved author configuration to the flow context
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.setup` @2336f43d893e

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with the selected story and epic
- verify: json_path(path="$.progress", equals="authoring one story")
- returns: returns the selected story, parent epic, and progress text `authoring one story`
- verify: json_path(path="$.work_id", equals="CASE-1234")
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.labels` @2336f43d893e

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: adds the `story_author.reworks` and `story_author.answers` counters to run labels
- returns: returns the base story labels combined with counter labels
- verify: json_path(path="$.story_author.reworks", equals="example reworks")
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.state_labels` @2336f43d893e

### _abs
- sig: `_abs(relative: str) -> Path`
- does: resolves a repository-relative artifact path beneath the workflow repository root
- verify: json_path(path="$.resolved_path", equals="docs/stories/acme-story/story.md")
- returns: returns the joined absolute path without changing the supplied relative path
- verify: json_path(path="$.relative_path", equals="docs/stories/acme-story/story.md")
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor._abs` @2336f43d893e

### _args
- sig: `_args(target: StoryTarget, mockup: str, **extra: str) -> dict[str, str]`
- does: builds the prompt arguments every writer turn shares, including the PM ledger path
- verify: json_path(path="$.ledger", matches="grills/pm\\.md$")
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor._args` @2336f43d893e

### _blocked
- sig: `_blocked(target: StoryTarget, mockup: str, notes: str, reworks: int, answers: int) -> Done`
- does: returns a `StoryAuthorDone` with `status: blocked` that carries the notes and both counters
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor._blocked` @2336f43d893e

### start
- sig: `start() -> Continue`
- does: resolves and prepares the explicitly selected epic/story target
- verify: count(subject="prepared story-author targets", equals=1)
- does: routes to mockup design when the story requires a mockup
- verify: count(subject="story-author mockup gate decisions", equals=1)
- does: routes directly to story writing when no mockup is required
- verify: count(subject="story-author direct-write starts", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.start` @2336f43d893e

### design_mockup
- sig: `design_mockup(target: StoryTarget) -> Continue | Done`
- does: asks the high-power design agent for a story-local mockup
- verify: count(subject="story-author mockup turns", equals=1)
- returns: carries the returned mockup reference into story writing, or ends the run as `blocked` with the reason when the mockup failed or is missing
- verify: json_path(path="$.mockup", equals="example mockup")
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.design_mockup` @2336f43d893e

### write_story
- sig: `write_story(target: StoryTarget, mockup: str = "", reworks: int = 0, answers: int = 0, note: str = "", prior: str = "") -> Continue | Done`
- does: asks the high-power writing agent to author the selected story
- verify: count(subject="story-author writing turns", equals=1)
- does: routes a blocked writing result to the PM while fewer than two answers were used
- verify: count(subject="story-author blocked-write PM questions", equals=1)
- does: sends a non-blocked writing result to story checks
- verify: count(subject="story-author write-to-check continuations", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.write_story` @2336f43d893e

### check_story
- sig: `check_story(target: StoryTarget, mockup: str = "", reworks: int = 0, answers: int = 0, prior: str = "") -> Continue | Done`
- does: validates the story document structure
- verify: count(subject="story-author structure validations", equals=1)
- does: routes a failed structure validation through bounded story rework
- verify: count(subject="story-author structure-failure routes", equals=1)
- does: validates story grounding against the parent epic and feature book
- verify: count(subject="story-author grounding validations", equals=1)
- does: routes failed grounding through bounded story rework
- verify: count(subject="story-author grounding-failure routes", equals=1)
- does: sends a valid, grounded story to the PM review
- verify: count(subject="story-author PM review handoffs", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.check_story` @2336f43d893e

### review
- sig: `review(target: StoryTarget, mockup: str = "", reworks: int = 0, answers: int = 0, prior: str = "") -> Continue | Done`
- does: hands the story to the PM review at the `story` stage with the previous findings
- verify: count(subject="story-author PM review turns", equals=1)
- does: routes a passing review to feedback polling
- verify: count(subject="story-author passing review continuations", equals=1)
- does: routes findings to story rework while fewer than three reworks were used
- verify: count(subject="story-author review reworks", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.review` @2336f43d893e

### rework_story
- sig: `rework_story(target: StoryTarget, notes: str, mockup: str = "", reworks: int = 0, answers: int = 0, note: str = "", prior: str = "") -> Continue | Done`
- does: records the failed attempt in the story's attempts ledger
- verify: persists(subject="the story attempts ledger")
- does: asks the rework agent to revise the story using validation or review notes
- verify: count(subject="story-author rework turns", equals=1)
- does: resumes story checks with an incremented rework counter
- verify: count(subject="story-author rework continuations", equals=1)
- does: routes a blocked rework result to the PM while fewer than two answers were used
- verify: count(subject="story-author blocked-rework PM questions", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.rework_story` @2336f43d893e

### _rework
- sig: `_rework(result: object, notes: str, target: StoryTarget, mockup: str, reworks: int, answers: int, prior: str) -> Continue | Done`
- does: sends findings to story rework while the rework count is below three
- verify: count(subject="story-author bounded reworks", equals=1)
- does: returns a blocked completion when three reworks are complete
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor._rework` @2336f43d893e

### _ask
- sig: `_ask(question: str, phase: str, target: StoryTarget, mockup: str, notes: str, reworks: int, answers: int, prior: str) -> Continue | Done`
- does: routes a writer's question to `ask_pm` while fewer than two answers were used
- verify: count(subject="story-author PM question routes", equals=1)
- does: returns a blocked completion carrying the question once the answer budget is spent
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor._ask` @2336f43d893e

### ask_pm
- sig: `ask_pm(question: str, phase: str, target: StoryTarget, mockup: str = "", notes: str = "", reworks: int = 0, answers: int = 0, prior: str = "") -> Continue`
- does: hands the writer's question to the PM gap answer
- verify: count(subject="story-author PM answers", equals=1)
- does: resumes writing or rework, by phase, with the answer as the note and the answer counter incremented
- verify: json_path(path="$.answers", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.ask_pm` @2336f43d893e

### story_feedback
- sig: `story_feedback(target: StoryTarget, mockup: str = "", reworks: int = 0, answers: int = 0) -> Continue | Done`
- does: polls the configured feedback directory, or the current run directory when none is configured
- verify: count(subject="story-author feedback polls", equals=1)
- does: applies an available feedback message through the rework agent
- verify: count(subject="story-author feedback reworks", equals=1)
- does: returns the authored story result when no feedback is present
- verify: json_path(path="$.status", equals="authored")
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.story_feedback` @2336f43d893e
- emits: [story-author-done](../formats/story-author-done.md)

### apply_feedback
- sig: `apply_feedback(target: StoryTarget, notes: str, mockup: str = "", reworks: int = 0, answers: int = 0) -> Continue`
- does: asks the rework agent to apply operator feedback to the selected story
- verify: count(subject="story-author feedback application turns", equals=1)
- does: resumes structural and grounding checks without changing the answer count
- verify: count(subject="story-author feedback check continuations", equals=1)
- code: `workflows/src/workhorse_workflows/author/story_author/flow.py::StoryAuthor.apply_feedback` @2336f43d893e

## Nodes

### prepare_story
- sig: `prepare_story(logger: logging.Logger, epic: str = "", story: str = "", repo_dir: str = "") -> StoryTarget`
- consistency: story-target — rejects blank epic or story inputs
- raises: raises `WorkflowFailed` stating that explicit non-empty `epic` and `story` inputs are required
- verify: count(subject="blank story-author target failures", equals=1)
- does: resolves the named story only within the requested epic through Ostler
- raises: raises `WorkflowFailed` naming the missing story and epic
- verify: count(subject="cross-epic story-author target failures", equals=1)
- does: completes missing story sections through Ostler's idempotent scaffold operation
- verify: count(subject="story-author missing-section scaffolds", equals=1)
- returns: returns normalized epic, story, epic directory, story directory, and story document paths
- verify: json_path(path="$.story_path", matches="/story\\.md$")
- emits: [story-author-target](../formats/story-author-target.md)
- code: `workflows/src/workhorse_workflows/author/story_author/nodes/story.py::prepare_story` @4864c255c805
